"""Explicit synthetic CRM demonstration dataset.

The data is fictional, stored in the same tenant-scoped tables as real records,
and every row carries ``is_demo = true`` so it can be filtered out later. The
seed is never injected implicitly: a workspace member must call the explicit
demo endpoint, and the action is audited.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CrmCompany, CrmContact, CrmCustomer, CrmDeal


@dataclass(slots=True)
class DemoSeedResult:
    created: bool
    companies: int
    customers: int
    deals: int
    contacts: int


_COMPANIES = (
    ("Aurika Logistics", "Logistics", 420),
    ("Meridian Health", "Healthcare", 860),
    ("Sundara Foods", "Food processing", 310),
    ("Kestrel Design", "Design studio", 45),
    ("Nimbus Retail", "Retail", 1200),
)

_CUSTOMERS = (
    ("Priya Nair", "priya.nair@aurika.example", "VP Operations", "Aurika Logistics", "active"),
    ("Arjun Mehta", "arjun.mehta@aurika.example", "Finance Director", "Aurika Logistics", "active"),
    ("Leela Rao", "leela.rao@meridian.example", "Head of Analytics", "Meridian Health", "active"),
    (
        "Rohan Kapoor",
        "rohan.kapoor@meridian.example",
        "Procurement Lead",
        "Meridian Health",
        "prospect",
    ),
    ("Meera Iyer", "meera.iyer@sundara.example", "COO", "Sundara Foods", "active"),
    ("Vikram Shah", "vikram.shah@kestrel.example", "Founder", "Kestrel Design", "prospect"),
    ("Ananya Das", "ananya.das@nimbus.example", "Category Director", "Nimbus Retail", "active"),
)

# (name, customer email, amount, stage, probability, days since last contact or None)
_DEALS = (
    ("Enterprise plan renewal", "priya.nair@aurika.example", 125000, "negotiation", 60, 21),
    ("Analytics add-on", "leela.rao@meridian.example", 78000, "proposal", 45, 18),
    ("Field sales rollout", "meera.iyer@sundara.example", 56500, "qualified", 35, None),
    ("Starter plan expansion", "vikram.shah@kestrel.example", 42000, "qualified", 30, 25),
    ("Support package", "arjun.mehta@aurika.example", 95000, "proposal", 50, 4),
    ("Annual renewal", "ananya.das@nimbus.example", 210000, "negotiation", 65, 35),
    ("Pilot programme", "rohan.kapoor@meridian.example", 65000, "prospecting", 20, 16),
    ("Enterprise rollout", "meera.iyer@sundara.example", 150000, "won", 100, 40),
    ("Legacy migration", "vikram.shah@kestrel.example", 30000, "lost", 0, 60),
    ("Regional expansion", "ananya.das@nimbus.example", 88000, "qualified", 40, 12),
    ("Onboarding package", "priya.nair@aurika.example", 51000, "proposal", 55, None),
    ("Data warehouse", "leela.rao@meridian.example", 175000, "negotiation", 60, 22),
)

_CONTACTS = (
    (
        "priya.nair@aurika.example",
        "Enterprise plan renewal",
        "email",
        "Sent renewal options and procurement timeline.",
        21,
    ),
    (
        "arjun.mehta@aurika.example",
        "Support package",
        "call",
        "Discussed support tiers; happy with premium SLA.",
        4,
    ),
    (
        "leela.rao@meridian.example",
        "Analytics add-on",
        "meeting",
        "Walked through dashboard use cases with the analytics team.",
        18,
    ),
    (
        "ananya.das@nimbus.example",
        "Regional expansion",
        "email",
        "Shared regional rollout plan; awaiting feedback.",
        12,
    ),
    (
        "meera.iyer@sundara.example",
        "Enterprise rollout",
        "call",
        "Rollout completed; closing the deal.",
        40,
    ),
)


async def seed_demo_crm(
    session: AsyncSession, *, workspace_id: uuid.UUID, actor_id: uuid.UUID | None
) -> DemoSeedResult:
    """Seed the fictional dataset once per workspace."""
    existing = int(
        await session.scalar(
            select(func.count())
            .select_from(CrmCustomer)
            .where(CrmCustomer.workspace_id == workspace_id, CrmCustomer.is_demo.is_(True))
        )
        or 0
    )
    if existing:
        counts = await demo_dataset_counts(session, workspace_id)
        return DemoSeedResult(
            created=False,
            companies=counts["companies"],
            customers=counts["customers"],
            deals=counts["deals"],
            contacts=counts["contacts"],
        )

    now = datetime.now(UTC)
    companies: dict[str, CrmCompany] = {}
    for name, industry, employees in _COMPANIES:
        company = CrmCompany(
            workspace_id=workspace_id,
            name=name,
            industry=industry,
            website=f"https://{name.split()[0].lower()}.example",
            employee_count=employees,
            is_demo=True,
        )
        session.add(company)
        companies[name] = company
    await session.flush()

    customers: dict[str, CrmCustomer] = {}
    for index, (name, email, title, company_name, status) in enumerate(_CUSTOMERS):
        customer = CrmCustomer(
            workspace_id=workspace_id,
            company_id=companies[company_name].id,
            name=name,
            email=email,
            phone=f"+91 90000 00{index + 10:03d}",
            title=title,
            status=status,
            is_demo=True,
        )
        session.add(customer)
        customers[email] = customer
    await session.flush()

    deals: dict[str, CrmDeal] = {}
    for name, email, amount, stage, probability, days in _DEALS:
        last_contacted = now - timedelta(days=days) if days is not None else None
        # Some open deals carry an overdue follow-up date to exercise reports.
        overdue = days is None or days >= 14
        deal = CrmDeal(
            workspace_id=workspace_id,
            customer_id=customers[email].id,
            name=name,
            amount=amount,
            currency="INR",
            stage=stage,
            probability=probability,
            owner_name="Demo Sales Team",
            last_contacted_at=last_contacted,
            next_follow_up_at=(now - timedelta(days=2)) if overdue else (now + timedelta(days=5)),
            is_demo=True,
        )
        session.add(deal)
        deals[name] = deal
    await session.flush()

    for email, deal_name, channel, summary, days in _CONTACTS:
        session.add(
            CrmContact(
                workspace_id=workspace_id,
                customer_id=customers[email].id,
                deal_id=deals[deal_name].id,
                channel=channel,
                summary=summary,
                contacted_at=now - timedelta(days=days),
                created_by=actor_id,
                is_demo=True,
            )
        )

    await session.flush()
    return DemoSeedResult(
        created=True,
        companies=len(_COMPANIES),
        customers=len(_CUSTOMERS),
        deals=len(_DEALS),
        contacts=len(_CONTACTS),
    )


async def demo_dataset_status(session: AsyncSession, workspace_id: uuid.UUID) -> dict[str, int]:
    customers = int(
        await session.scalar(
            select(func.count())
            .select_from(CrmCustomer)
            .where(CrmCustomer.workspace_id == workspace_id, CrmCustomer.is_demo.is_(True))
        )
        or 0
    )
    deals = int(
        await session.scalar(
            select(func.count())
            .select_from(CrmDeal)
            .where(CrmDeal.workspace_id == workspace_id, CrmDeal.is_demo.is_(True))
        )
        or 0
    )
    return {"customers": customers, "deals": deals}


async def demo_dataset_counts(session: AsyncSession, workspace_id: uuid.UUID) -> dict[str, int]:
    """Return per-entity demo row counts for one workspace."""
    counts: dict[str, int] = {}
    for key, model in (
        ("companies", CrmCompany),
        ("customers", CrmCustomer),
        ("deals", CrmDeal),
        ("contacts", CrmContact),
    ):
        counts[key] = int(
            await session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.workspace_id == workspace_id, model.is_demo.is_(True))
            )
            or 0
        )
    return counts


__all__ = [
    "DemoSeedResult",
    "demo_dataset_counts",
    "demo_dataset_status",
    "seed_demo_crm",
]
