"""Built-in CRM tools operating on the workspace's synthetic CRM dataset.

Every query is workspace-scoped. Tool arguments are strict Pydantic models;
unknown fields are rejected before execution. No tool sends external messages:
``create_followup_draft`` only stores an internal, reversible draft, and
``mark_deal_contacted`` changes a business record and therefore requires human
approval.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.models.crm import (
    CrmCompany,
    CrmContact,
    CrmCustomer,
    CrmDeal,
    FollowupDraft,
)
from app.tools.base import (
    Tool,
    ToolContext,
    ToolInput,
    ToolSpec,
    registry,
)


def _like(value: str) -> str:
    """Escape LIKE metacharacters in user-supplied search text."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Output contracts
# --------------------------------------------------------------------------- #
class CustomerSummary(_Out):
    customer_id: uuid.UUID
    name: str
    email: str
    title: str | None = None
    status: str
    company_id: uuid.UUID | None = None
    company_name: str | None = None


class DealSummary(_Out):
    deal_id: uuid.UUID
    name: str
    amount: float
    currency: str
    stage: str
    probability: int
    owner_name: str | None = None
    last_contacted_at: datetime | None = None
    next_follow_up_at: datetime | None = None
    customer_id: uuid.UUID
    customer_name: str
    customer_email: str
    company_name: str | None = None


class ContactSummary(_Out):
    contact_id: uuid.UUID
    channel: str
    summary: str
    contacted_at: datetime


class SearchCustomersInput(ToolInput):
    query: str | None = Field(default=None, max_length=120)
    status: Literal["active", "prospect", "churned"] | None = None
    limit: int = Field(default=10, ge=1, le=50)


class SearchCustomersOutput(_Out):
    customers: list[CustomerSummary]
    returned_count: int


class SearchDealsInput(ToolInput):
    min_amount: float | None = Field(default=None, ge=0)
    max_amount: float | None = Field(default=None, ge=0)
    stage: Literal["prospecting", "qualified", "proposal", "negotiation", "won", "lost"] | None = (
        None
    )
    not_contacted_since_days: int | None = Field(default=None, ge=1, le=3650)
    open_only: bool = True
    limit: int = Field(default=20, ge=1, le=50)


class SearchDealsOutput(_Out):
    deals: list[DealSummary]
    returned_count: int
    criteria: dict[str, Any]


class GetCustomerSummaryInput(ToolInput):
    customer_id: uuid.UUID


class GetCustomerSummaryOutput(_Out):
    customer: CustomerSummary
    deals: list[DealSummary]
    deal_count: int


class GetDealDetailsInput(ToolInput):
    deal_id: uuid.UUID


class GetDealDetailsOutput(_Out):
    deal: DealSummary
    customer: CustomerSummary
    recent_contacts: list[ContactSummary]


class CalculateMetricsInput(ToolInput):
    metric: Literal[
        "pipeline_value",
        "weighted_pipeline_value",
        "won_revenue",
        "win_rate",
        "average_deal_size",
        "open_deal_count",
    ]
    stage: Literal["prospecting", "qualified", "proposal", "negotiation", "won", "lost"] | None = (
        None
    )


class CalculateMetricsOutput(_Out):
    metric: str
    value: float | None
    sample_size: int
    note: str | None = None


class SearchKnowledgeInput(ToolInput):
    query: str = Field(min_length=2, max_length=200)
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeHit(_Out):
    document_id: uuid.UUID
    title: str
    snippet: str
    score: float


class SearchKnowledgeOutput(_Out):
    query: str
    results: list[KnowledgeHit]
    note: str | None = None


class CreateFollowupDraftInput(ToolInput):
    customer_id: uuid.UUID
    deal_id: uuid.UUID | None = None
    channel: Literal["email", "call", "note"] = "email"
    subject: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=4000)


class CreateFollowupDraftOutput(_Out):
    draft_id: uuid.UUID
    status: str
    customer_id: uuid.UUID
    deal_id: uuid.UUID | None = None
    note: str


class GenerateSalesReportInput(ToolInput):
    stage: Literal["prospecting", "qualified", "proposal", "negotiation", "won", "lost"] | None = (
        None
    )
    min_amount: float | None = Field(default=None, ge=0)


class StageTotals(_Out):
    stage: str
    deal_count: int
    total_amount: float


class ReportTotals(_Out):
    open_deal_count: int
    open_pipeline_value: float
    won_revenue: float
    overdue_followups: int


class GenerateSalesReportOutput(_Out):
    generated_at: datetime
    stage_breakdown: list[StageTotals]
    totals: ReportTotals


class MarkDealContactedInput(ToolInput):
    deal_id: uuid.UUID
    note: str = Field(min_length=3, max_length=1000)


class MarkDealContactedOutput(_Out):
    deal_id: uuid.UUID
    contact_id: uuid.UUID
    last_contacted_at: datetime
    note: str


# --------------------------------------------------------------------------- #
# Query helpers
# --------------------------------------------------------------------------- #
def _customer_summary(customer: CrmCustomer, company: CrmCompany | None) -> CustomerSummary:
    return CustomerSummary(
        customer_id=customer.id,
        name=customer.name,
        email=customer.email,
        title=customer.title,
        status=customer.status,
        company_id=customer.company_id,
        company_name=company.name if company else None,
    )


def _deal_summary(deal: CrmDeal, customer: CrmCustomer, company: CrmCompany | None) -> DealSummary:
    return DealSummary(
        deal_id=deal.id,
        name=deal.name,
        amount=float(deal.amount),
        currency=deal.currency,
        stage=deal.stage,
        probability=deal.probability,
        owner_name=deal.owner_name,
        last_contacted_at=deal.last_contacted_at,
        next_follow_up_at=deal.next_follow_up_at,
        customer_id=customer.id,
        customer_name=customer.name,
        customer_email=customer.email,
        company_name=company.name if company else None,
    )


def _deal_query() -> Any:
    return (
        select(CrmDeal, CrmCustomer, CrmCompany)
        .join(CrmCustomer, CrmDeal.customer_id == CrmCustomer.id)
        .outerjoin(CrmCompany, CrmCustomer.company_id == CrmCompany.id)
    )


async def _get_customer(
    session: AsyncSession, workspace_id: uuid.UUID, customer_id: uuid.UUID
) -> tuple[CrmCustomer, CrmCompany | None]:
    row = (
        await session.execute(
            select(CrmCustomer, CrmCompany)
            .outerjoin(CrmCompany, CrmCustomer.company_id == CrmCompany.id)
            .where(
                CrmCustomer.workspace_id == workspace_id,
                CrmCustomer.id == customer_id,
            )
        )
    ).first()
    if row is None:
        raise ValueError("Customer not found in this workspace.")
    return row[0], row[1]


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
class SearchCustomersTool:
    spec = ToolSpec(
        name="search_customers",
        description="Search customers by name, email or company in the workspace CRM.",
        input_model=SearchCustomersInput,
        output_model=SearchCustomersOutput,
        required_permissions=(Permission.RUN_READ,),
        timeout_seconds=15,
    )

    async def execute(self, context: ToolContext, arguments: BaseModel) -> BaseModel:
        args = SearchCustomersInput.model_validate(arguments)
        conditions = [CrmCustomer.workspace_id == context.workspace_id]
        if args.query:
            pattern = _like(args.query)
            conditions.append(
                or_(
                    CrmCustomer.name.ilike(pattern, escape="\\"),
                    CrmCustomer.email.ilike(pattern, escape="\\"),
                    CrmCompany.name.ilike(pattern, escape="\\"),
                )
            )
        if args.status:
            conditions.append(CrmCustomer.status == args.status)

        rows = (
            await context.session.execute(
                select(CrmCustomer, CrmCompany)
                .outerjoin(CrmCompany, CrmCustomer.company_id == CrmCompany.id)
                .where(*conditions)
                .order_by(CrmCustomer.name)
                .limit(args.limit)
            )
        ).all()
        customers = [_customer_summary(customer, company) for customer, company in rows]
        return SearchCustomersOutput(customers=customers, returned_count=len(customers))


class SearchDealsTool:
    spec = ToolSpec(
        name="search_deals",
        description=(
            "Search CRM deals by value, stage and last-contact recency. "
            "Deals never contacted count as not recently contacted."
        ),
        input_model=SearchDealsInput,
        output_model=SearchDealsOutput,
        required_permissions=(Permission.RUN_READ,),
        timeout_seconds=15,
    )

    async def execute(self, context: ToolContext, arguments: BaseModel) -> BaseModel:
        args = SearchDealsInput.model_validate(arguments)
        conditions = [CrmDeal.workspace_id == context.workspace_id]
        if args.min_amount is not None:
            conditions.append(CrmDeal.amount >= args.min_amount)
        if args.max_amount is not None:
            conditions.append(CrmDeal.amount <= args.max_amount)
        if args.stage:
            conditions.append(CrmDeal.stage == args.stage)
        if args.open_only:
            conditions.append(CrmDeal.stage.notin_(("won", "lost")))
        if args.not_contacted_since_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=args.not_contacted_since_days)
            conditions.append(
                or_(CrmDeal.last_contacted_at.is_(None), CrmDeal.last_contacted_at < cutoff)
            )

        rows = (
            await context.session.execute(
                _deal_query().where(*conditions).order_by(CrmDeal.amount.desc()).limit(args.limit)
            )
        ).all()
        deals = [_deal_summary(*row) for row in rows]
        return SearchDealsOutput(
            deals=deals,
            returned_count=len(deals),
            criteria={
                "min_amount": args.min_amount,
                "max_amount": args.max_amount,
                "stage": args.stage,
                "not_contacted_since_days": args.not_contacted_since_days,
                "open_only": args.open_only,
            },
        )


class GetCustomerSummaryTool:
    spec = ToolSpec(
        name="get_customer_summary",
        description="Return one customer with their company and deals.",
        input_model=GetCustomerSummaryInput,
        output_model=GetCustomerSummaryOutput,
        required_permissions=(Permission.RUN_READ,),
        timeout_seconds=15,
    )

    async def execute(self, context: ToolContext, arguments: BaseModel) -> BaseModel:
        args = GetCustomerSummaryInput.model_validate(arguments)
        try:
            customer, company = await _get_customer(
                context.session, context.workspace_id, args.customer_id
            )
        except ValueError as exc:
            raise LookupError(str(exc)) from exc

        rows = (
            await context.session.execute(
                _deal_query()
                .where(
                    CrmDeal.workspace_id == context.workspace_id,
                    CrmDeal.customer_id == args.customer_id,
                )
                .order_by(CrmDeal.amount.desc())
                .limit(20)
            )
        ).all()
        deals = [_deal_summary(*row) for row in rows]
        return GetCustomerSummaryOutput(
            customer=_customer_summary(customer, company),
            deals=deals,
            deal_count=len(deals),
        )


class GetDealDetailsTool:
    spec = ToolSpec(
        name="get_deal_details",
        description="Return one deal with its customer and recent contact history.",
        input_model=GetDealDetailsInput,
        output_model=GetDealDetailsOutput,
        required_permissions=(Permission.RUN_READ,),
        timeout_seconds=15,
    )

    async def execute(self, context: ToolContext, arguments: BaseModel) -> BaseModel:
        args = GetDealDetailsInput.model_validate(arguments)
        row = (
            await context.session.execute(
                _deal_query().where(
                    CrmDeal.workspace_id == context.workspace_id,
                    CrmDeal.id == args.deal_id,
                )
            )
        ).first()
        if row is None:
            raise LookupError("Deal not found in this workspace.")
        deal, customer, company = row

        contacts = (
            await context.session.execute(
                select(CrmContact)
                .where(
                    CrmContact.workspace_id == context.workspace_id,
                    CrmContact.deal_id == deal.id,
                )
                .order_by(CrmContact.contacted_at.desc())
                .limit(10)
            )
        ).scalars()
        return GetDealDetailsOutput(
            deal=_deal_summary(deal, customer, company),
            customer=_customer_summary(customer, company),
            recent_contacts=[
                ContactSummary(
                    contact_id=contact.id,
                    channel=contact.channel,
                    summary=contact.summary,
                    contacted_at=contact.contacted_at,
                )
                for contact in contacts
            ],
        )


class CalculateMetricsTool:
    spec = ToolSpec(
        name="calculate_metrics",
        description="Calculate one CRM metric from persisted deal rows.",
        input_model=CalculateMetricsInput,
        output_model=CalculateMetricsOutput,
        required_permissions=(Permission.RUN_READ,),
        timeout_seconds=15,
    )

    async def execute(self, context: ToolContext, arguments: BaseModel) -> BaseModel:
        args = CalculateMetricsInput.model_validate(arguments)
        session = context.session
        workspace = context.workspace_id

        if args.metric == "win_rate":
            counts = (
                await session.execute(
                    select(CrmDeal.stage, func.count())
                    .where(
                        CrmDeal.workspace_id == workspace,
                        CrmDeal.stage.in_(("won", "lost")),
                    )
                    .group_by(CrmDeal.stage)
                )
            ).all()
            by_stage = {stage: int(count) for stage, count in counts}
            closed = by_stage.get("won", 0) + by_stage.get("lost", 0)
            if closed == 0:
                return CalculateMetricsOutput(
                    metric=args.metric,
                    value=None,
                    sample_size=0,
                    note="No closed deals exist, so a win rate cannot be computed.",
                )
            return CalculateMetricsOutput(
                metric=args.metric,
                value=round(by_stage.get("won", 0) / closed * 100, 2),
                sample_size=closed,
            )

        conditions = [CrmDeal.workspace_id == workspace]
        if args.stage:
            conditions.append(CrmDeal.stage == args.stage)

        if args.metric in ("pipeline_value", "weighted_pipeline_value", "open_deal_count"):
            conditions.append(CrmDeal.stage.notin_(("won", "lost")))

        if args.metric == "won_revenue":
            conditions.append(CrmDeal.stage == "won")

        if args.metric == "weighted_pipeline_value":
            total = await session.scalar(
                select(
                    func.coalesce(func.sum(CrmDeal.amount * CrmDeal.probability / 100), 0)
                ).where(*conditions)
            )
        elif args.metric == "open_deal_count":
            total = await session.scalar(select(func.count()).where(*conditions))
        else:
            total = await session.scalar(
                select(func.coalesce(func.sum(CrmDeal.amount), 0)).where(*conditions)
            )

        sample_size = int(await session.scalar(select(func.count()).where(*conditions)) or 0)
        return CalculateMetricsOutput(
            metric=args.metric,
            value=round(float(total or 0), 2),
            sample_size=sample_size,
        )


class SearchKnowledgeTool:
    spec = ToolSpec(
        name="search_knowledge",
        description=(
            "Search workspace knowledge documents. Returns an explicit empty result "
            "until knowledge ingestion is configured."
        ),
        input_model=SearchKnowledgeInput,
        output_model=SearchKnowledgeOutput,
        required_permissions=(Permission.KNOWLEDGE_READ,),
        timeout_seconds=15,
        implementation_prefix="knowledge",
    )

    async def execute(self, context: ToolContext, arguments: BaseModel) -> BaseModel:
        args = SearchKnowledgeInput.model_validate(arguments)
        # Knowledge ingestion lands in a later milestone. Reporting an explicit
        # empty result is honest; fabricating passages would not be.
        return SearchKnowledgeOutput(
            query=args.query,
            results=[],
            note="No knowledge sources are configured in this workspace yet.",
        )


class CreateFollowupDraftTool:
    spec = ToolSpec(
        name="create_followup_draft",
        description=(
            "Create an internal follow-up draft for a customer. This never sends "
            "email or any external message."
        ),
        input_model=CreateFollowupDraftInput,
        output_model=CreateFollowupDraftOutput,
        risk_level="medium",
        required_permissions=(Permission.RUN_EXECUTE,),
        timeout_seconds=15,
        idempotent=False,
    )

    async def execute(self, context: ToolContext, arguments: BaseModel) -> BaseModel:
        args = CreateFollowupDraftInput.model_validate(arguments)
        try:
            await _get_customer(context.session, context.workspace_id, args.customer_id)
        except ValueError as exc:
            raise LookupError(str(exc)) from exc

        if args.deal_id is not None:
            deal = await context.session.scalar(
                select(CrmDeal).where(
                    CrmDeal.workspace_id == context.workspace_id,
                    CrmDeal.id == args.deal_id,
                    CrmDeal.customer_id == args.customer_id,
                )
            )
            if deal is None:
                raise LookupError("Deal not found for this customer in this workspace.")

        draft = FollowupDraft(
            workspace_id=context.workspace_id,
            customer_id=args.customer_id,
            deal_id=args.deal_id,
            run_id=context.run_id,
            channel=args.channel,
            subject=args.subject,
            body=args.body,
            status="draft",
            created_by=context.actor_id,
        )
        context.session.add(draft)
        await context.session.flush()
        return CreateFollowupDraftOutput(
            draft_id=draft.id,
            status=draft.status,
            customer_id=draft.customer_id,
            deal_id=draft.deal_id,
            note="Draft stored internally. Nothing was sent.",
        )


class GenerateSalesReportTool:
    spec = ToolSpec(
        name="generate_sales_report",
        description="Aggregate deal value by stage plus open-pipeline totals.",
        input_model=GenerateSalesReportInput,
        output_model=GenerateSalesReportOutput,
        required_permissions=(Permission.RUN_READ,),
        timeout_seconds=20,
    )

    async def execute(self, context: ToolContext, arguments: BaseModel) -> BaseModel:
        args = GenerateSalesReportInput.model_validate(arguments)
        conditions = [CrmDeal.workspace_id == context.workspace_id]
        if args.stage:
            conditions.append(CrmDeal.stage == args.stage)
        if args.min_amount is not None:
            conditions.append(CrmDeal.amount >= args.min_amount)

        rows = (
            await context.session.execute(
                select(CrmDeal.stage, func.count(), func.coalesce(func.sum(CrmDeal.amount), 0))
                .where(*conditions)
                .group_by(CrmDeal.stage)
                .order_by(CrmDeal.stage)
            )
        ).all()
        breakdown = [
            StageTotals(stage=stage, deal_count=int(count), total_amount=float(total))
            for stage, count, total in rows
        ]

        open_count = sum(item.deal_count for item in breakdown if item.stage not in ("won", "lost"))
        open_value = sum(
            item.total_amount for item in breakdown if item.stage not in ("won", "lost")
        )
        won_value = sum(item.total_amount for item in breakdown if item.stage == "won")
        overdue = int(
            await context.session.scalar(
                select(func.count()).where(
                    CrmDeal.workspace_id == context.workspace_id,
                    CrmDeal.stage.notin_(("won", "lost")),
                    CrmDeal.next_follow_up_at.is_not(None),
                    CrmDeal.next_follow_up_at < datetime.now(UTC),
                )
            )
            or 0
        )
        return GenerateSalesReportOutput(
            generated_at=datetime.now(UTC),
            stage_breakdown=breakdown,
            totals=ReportTotals(
                open_deal_count=open_count,
                open_pipeline_value=round(open_value, 2),
                won_revenue=round(won_value, 2),
                overdue_followups=overdue,
            ),
        )


class MarkDealContactedTool:
    spec = ToolSpec(
        name="mark_deal_contacted",
        description=(
            "Record that a deal was contacted. Changes a business record, so it "
            "requires explicit human approval."
        ),
        input_model=MarkDealContactedInput,
        output_model=MarkDealContactedOutput,
        risk_level="high",
        required_permissions=(Permission.RUN_EXECUTE,),
        requires_approval=True,
        timeout_seconds=15,
        idempotent=False,
    )

    async def execute(self, context: ToolContext, arguments: BaseModel) -> BaseModel:
        args = MarkDealContactedInput.model_validate(arguments)
        deal = await context.session.scalar(
            select(CrmDeal).where(
                CrmDeal.workspace_id == context.workspace_id,
                CrmDeal.id == args.deal_id,
            )
        )
        if deal is None:
            raise LookupError("Deal not found in this workspace.")

        now = datetime.now(UTC)
        deal.last_contacted_at = now
        contact = CrmContact(
            workspace_id=context.workspace_id,
            customer_id=deal.customer_id,
            deal_id=deal.id,
            channel="note",
            summary=args.note,
            contacted_at=now,
            created_by=context.actor_id,
        )
        context.session.add(contact)
        await context.session.flush()
        return MarkDealContactedOutput(
            deal_id=deal.id,
            contact_id=contact.id,
            last_contacted_at=now,
            note=args.note,
        )


BUILTIN_TOOLS: tuple[Tool, ...] = (
    SearchCustomersTool(),
    SearchDealsTool(),
    GetCustomerSummaryTool(),
    GetDealDetailsTool(),
    CalculateMetricsTool(),
    SearchKnowledgeTool(),
    CreateFollowupDraftTool(),
    GenerateSalesReportTool(),
    MarkDealContactedTool(),
)


def register() -> None:
    """Register every built-in tool exactly once."""
    existing = registry.by_name()
    for tool in BUILTIN_TOOLS:
        if tool.spec.name not in existing:
            registry.register(tool)


__all__ = ["BUILTIN_TOOLS", "register"]
