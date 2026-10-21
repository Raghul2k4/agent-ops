"""Agent lifecycle: draft, immutable versions, publish, rollback, duplicate.

A draft is edited in place on ``app.agents.draft_configuration``. Publishing
serialises that draft into a new ``app.agent_versions`` row; the migration's
trigger rejects any later update to a version, so run history stays truthful.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ConflictError,
    ResourceNotFound,
    ValidationError,
)
from app.core.permissions import Role
from app.core.security import hash_payload
from app.models.agents import Agent, AgentVersion
from app.models.identity import WorkspaceMember
from app.models.providers import ModelConfig, ModelProvider
from app.models.tools import AgentTool, ToolDefinition
from app.schemas.agents import (
    AgentConfiguration,
    AgentCreateRequest,
    ExecutionLimits,
    ModelParameters,
)
from app.services import tools as tool_service


@dataclass(frozen=True, slots=True)
class AgentTemplate:
    key: str
    name: str
    description: str
    category: str
    system_prompt: str
    tool_names: tuple[str, ...]
    parameters: ModelParameters


_GROUNDING_RULE = (
    "Only use facts returned by tools. If the requested information is not in the "
    "available data, say so explicitly instead of guessing or inventing details. "
    "Never claim an action was taken unless a tool result confirms it."
)

AGENT_TEMPLATES: tuple[AgentTemplate, ...] = (
    AgentTemplate(
        key="crm_research_assistant",
        name="CRM Research Assistant",
        description="Researches customers and deals before a conversation.",
        category="Sales",
        system_prompt=(
            "You are a CRM research assistant. Use the CRM tools to find customers "
            "and deals, then summarise verified facts. " + _GROUNDING_RULE
        ),
        tool_names=(
            "search_customers",
            "search_deals",
            "get_customer_summary",
            "get_deal_details",
        ),
        parameters=ModelParameters(temperature=0.1, max_output_tokens=1200),
    ),
    AgentTemplate(
        key="structured_data_extractor",
        name="Structured Data Extractor",
        description="Turns CRM queries into precise structured metrics.",
        category="Data",
        system_prompt=(
            "You extract structured CRM facts. Prefer calculate_metrics and "
            "search_deals over prose. State the exact numbers returned by tools. " + _GROUNDING_RULE
        ),
        tool_names=("search_deals", "calculate_metrics", "generate_sales_report"),
        parameters=ModelParameters(temperature=0.0, max_output_tokens=900),
    ),
    AgentTemplate(
        key="document_research_assistant",
        name="Document Research Assistant",
        description="Answers questions from workspace knowledge sources.",
        category="Knowledge",
        system_prompt=(
            "You answer questions from workspace documents. Always cite the source "
            "title and passage returned by search_knowledge. If no passage is "
            "returned, state that the answer is not available in the knowledge base. "
            + _GROUNDING_RULE
        ),
        tool_names=("search_knowledge", "search_customers"),
        parameters=ModelParameters(temperature=0.1, max_output_tokens=1500),
    ),
    AgentTemplate(
        key="customer_support_triage",
        name="Customer Support Triage",
        description="Classifies support requests and prepares internal follow-ups.",
        category="Support",
        system_prompt=(
            "You triage support requests. Identify the customer, summarise the issue "
            "from CRM data, and prepare an internal draft reply. Drafts are never "
            "sent automatically. " + _GROUNDING_RULE
        ),
        tool_names=("search_customers", "get_customer_summary", "create_followup_draft"),
        parameters=ModelParameters(temperature=0.2, max_output_tokens=1200),
    ),
    AgentTemplate(
        key="report_generator",
        name="Report Generator",
        description="Produces a sales report from persisted CRM aggregates.",
        category="Reporting",
        system_prompt=(
            "You produce concise sales reports. Call generate_sales_report and "
            "calculate_metrics, then report only the returned figures with their "
            "units. " + _GROUNDING_RULE
        ),
        tool_names=("generate_sales_report", "calculate_metrics"),
        parameters=ModelParameters(temperature=0.0, max_output_tokens=1600),
    ),
    AgentTemplate(
        key="tool_calling_assistant",
        name="Tool-Calling Assistant",
        description="General CRM assistant with the full read-only tool set.",
        category="General",
        system_prompt=(
            "You are a tool-calling CRM assistant. Select the most specific tool for "
            "the request and chain tools only when necessary. " + _GROUNDING_RULE
        ),
        tool_names=(
            "search_customers",
            "search_deals",
            "get_customer_summary",
            "get_deal_details",
            "calculate_metrics",
        ),
        parameters=ModelParameters(temperature=0.2, max_output_tokens=1400),
    ),
    AgentTemplate(
        key="evaluation_assistant",
        name="Evaluation Assistant",
        description="Computes deterministic CRM facts for evaluation cases.",
        category="Evaluation",
        system_prompt=(
            "You answer evaluation prompts with deterministic CRM values. Use tools, "
            "never memory. " + _GROUNDING_RULE
        ),
        tool_names=("calculate_metrics", "generate_sales_report", "search_deals"),
        parameters=ModelParameters(temperature=0.0, max_output_tokens=800),
    ),
    AgentTemplate(
        key="sales_followup_drafter",
        name="Sales Follow-Up Drafter",
        description="Finds stale deals and drafts personalised follow-ups for review.",
        category="Sales",
        system_prompt=(
            "You are a sales operations assistant. Find deals matching the requested "
            "criteria, review the customer data, and prepare internal follow-up drafts. "
            "Show every proposed action for human review before anything is sent. "
            + _GROUNDING_RULE
        ),
        tool_names=(
            "search_deals",
            "get_customer_summary",
            "get_deal_details",
            "create_followup_draft",
        ),
        parameters=ModelParameters(temperature=0.3, max_output_tokens=1600),
    ),
)

TEMPLATES_BY_KEY: dict[str, AgentTemplate] = {
    template.key: template for template in AGENT_TEMPLATES
}


async def member_role(
    session: AsyncSession, *, workspace_id: uuid.UUID, profile_id: uuid.UUID | None
) -> Role:
    """Resolve the caller's active role in a workspace.

    Non-members receive ``RESOURCE_NOT_FOUND`` so workspace existence is not
    leaked across tenants.
    """
    if profile_id is None:
        raise ResourceNotFound("Workspace not found.")
    role = await session.scalar(
        select(WorkspaceMember.role).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == profile_id,
            WorkspaceMember.status == "active",
        )
    )
    if role is None:
        raise ResourceNotFound("Workspace not found.")
    try:
        return Role(role)
    except ValueError as exc:  # pragma: no cover - database constraint protects this
        raise ResourceNotFound("Workspace not found.") from exc


async def _validate_provider_model(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    provider_id: uuid.UUID,
    model_config_id: uuid.UUID,
) -> tuple[ModelProvider, ModelConfig]:
    provider = await session.scalar(
        select(ModelProvider).where(
            ModelProvider.workspace_id == workspace_id,
            ModelProvider.id == provider_id,
        )
    )
    if provider is None:
        raise ValidationError("The selected provider does not exist in this workspace.")
    if provider.status == "disabled":
        raise ValidationError("The selected provider is disabled.")

    model = await session.scalar(
        select(ModelConfig).where(
            ModelConfig.workspace_id == workspace_id,
            ModelConfig.id == model_config_id,
            ModelConfig.provider_id == provider.id,
        )
    )
    if model is None:
        raise ValidationError("The selected model does not belong to that provider.")
    if not model.enabled:
        raise ValidationError("The selected model is disabled.")
    return provider, model


async def _resolve_tool_names(
    session: AsyncSession, *, workspace_id: uuid.UUID, tool_names: list[str]
) -> list[uuid.UUID]:
    await tool_service.ensure_builtin_definitions(session)
    if not tool_names:
        return []
    rows = (
        await session.scalars(
            select(ToolDefinition).where(
                ToolDefinition.name.in_(tool_names),
                ToolDefinition.enabled.is_(True),
                (ToolDefinition.workspace_id.is_(None))
                | (ToolDefinition.workspace_id == workspace_id),
            )
        )
    ).all()
    found = {row.name: row for row in rows}
    missing = sorted(set(tool_names) - set(found))
    if missing:
        raise ValidationError(
            "One or more selected tools are not available.",
            details={"tools": missing},
        )
    return [found[name].id for name in tool_names]


async def _validate_tool_ids(
    session: AsyncSession, *, workspace_id: uuid.UUID, tool_ids: list[uuid.UUID]
) -> None:
    if not tool_ids:
        return
    await tool_service.ensure_builtin_definitions(session)
    rows = (
        await session.scalars(select(ToolDefinition).where(ToolDefinition.id.in_(tool_ids)))
    ).all()
    found = {row.id for row in rows if row.enabled and row.workspace_id in (None, workspace_id)}
    missing = [str(tool_id) for tool_id in tool_ids if tool_id not in found]
    if missing:
        raise ValidationError(
            "One or more selected tools are not available in this workspace.",
            details={"tool_ids": missing},
        )


async def validate_configuration(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    configuration: AgentConfiguration,
) -> tuple[ModelProvider, ModelConfig]:
    provider, model = await _validate_provider_model(
        session,
        workspace_id=workspace_id,
        provider_id=configuration.provider_id,
        model_config_id=configuration.model_config_id,
    )
    await _validate_tool_ids(session, workspace_id=workspace_id, tool_ids=configuration.tool_ids)
    return provider, model


async def create_agent(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    payload: AgentCreateRequest,
) -> Agent:
    template = None
    if payload.template_key:
        template = TEMPLATES_BY_KEY.get(payload.template_key)
        if template is None:
            raise ValidationError("The requested agent template does not exist.")

    provider, model = await _validate_provider_model(
        session,
        workspace_id=workspace_id,
        provider_id=payload.provider_id,
        model_config_id=payload.model_config_id,
    )
    _ = provider

    tool_names = (
        payload.tool_names
        if payload.tool_names is not None
        else list(template.tool_names)
        if template
        else []
    )
    tool_ids = await _resolve_tool_names(session, workspace_id=workspace_id, tool_names=tool_names)

    configuration = AgentConfiguration(
        provider_id=payload.provider_id,
        model_config_id=payload.model_config_id,
        model_name=model.model_name,
        system_prompt=(
            payload.system_prompt
            or (template.system_prompt if template else "You are a helpful CRM assistant.")
        ),
        parameters=payload.parameters or (template.parameters if template else ModelParameters()),
        limits=payload.limits or ExecutionLimits(),
        tool_ids=tool_ids,
    )

    agent = Agent(
        workspace_id=workspace_id,
        name=payload.name,
        description=payload.description,
        status="draft",
        draft_configuration=configuration.model_dump(mode="json"),
        created_by=actor_id,
    )
    session.add(agent)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("An agent with that name already exists in this workspace.") from exc
    return agent


async def list_agents(session: AsyncSession, *, workspace_id: uuid.UUID) -> list[Agent]:
    rows = (
        await session.scalars(
            select(Agent)
            .where(Agent.workspace_id == workspace_id, Agent.status != "archived")
            .order_by(Agent.updated_at.desc())
        )
    ).all()
    return list(rows)


async def get_agent(
    session: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID
) -> Agent:
    agent = await session.scalar(
        select(Agent).where(Agent.workspace_id == workspace_id, Agent.id == agent_id)
    )
    if agent is None:
        raise ResourceNotFound("Agent not found.")
    return agent


async def get_agent_by_id(session: AsyncSession, *, agent_id: uuid.UUID) -> Agent:
    """Fetch an agent without a workspace filter.

    Callers must authorize against ``agent.workspace_id`` immediately; this
    helper exists so item routes do not need a redundant workspace parameter.
    """
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise ResourceNotFound("Agent not found.")
    return agent


async def update_agent(
    session: AsyncSession,
    *,
    agent: Agent,
    payload: Any,
) -> Agent:
    if payload.name is not None and payload.name != agent.name:
        agent.name = payload.name
    if payload.description is not None:
        agent.description = payload.description

    if payload.draft_configuration is not None:
        await validate_configuration(
            session,
            workspace_id=agent.workspace_id,
            configuration=payload.draft_configuration,
        )
        agent.draft_configuration = payload.draft_configuration.model_dump(mode="json")

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("An agent with that name already exists in this workspace.") from exc
    return agent


async def archive_agent(session: AsyncSession, *, agent: Agent) -> Agent:
    agent.status = "archived"
    await session.flush()
    return agent


async def delete_agent(session: AsyncSession, *, agent: Agent) -> None:
    """Delete an agent that has no run history; refuse otherwise."""
    await session.delete(agent)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "This agent has run history and cannot be deleted. Archive it instead."
        ) from exc


async def list_versions(session: AsyncSession, *, agent_id: uuid.UUID) -> list[AgentVersion]:
    rows = (
        await session.scalars(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.version_number.desc())
        )
    ).all()
    return list(rows)


async def current_version_numbers(
    session: AsyncSession, agents: list[Agent]
) -> dict[uuid.UUID, int]:
    ids = [
        agent.current_published_version_id for agent in agents if agent.current_published_version_id
    ]
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(AgentVersion.id, AgentVersion.version_number).where(AgentVersion.id.in_(ids))
        )
    ).all()
    return dict(rows)


async def publish_agent(
    session: AsyncSession,
    *,
    agent: Agent,
    actor_id: uuid.UUID | None,
    change_summary: str,
) -> AgentVersion:
    locked = await session.scalar(select(Agent).where(Agent.id == agent.id).with_for_update())
    if locked is None:
        raise ResourceNotFound("Agent not found.")
    if locked.status == "archived":
        raise ConflictError("Archived agents cannot be published.")

    configuration = AgentConfiguration.model_validate(locked.draft_configuration)
    await validate_configuration(
        session, workspace_id=locked.workspace_id, configuration=configuration
    )

    highest = await session.scalar(
        select(func.coalesce(func.max(AgentVersion.version_number), 0)).where(
            AgentVersion.agent_id == locked.id
        )
    )
    version = AgentVersion(
        workspace_id=locked.workspace_id,
        agent_id=locked.id,
        version_number=int(highest or 0) + 1,
        configuration=configuration.model_dump(mode="json"),
        configuration_hash=hash_payload(configuration.model_dump(mode="json")),
        change_summary=change_summary,
        created_by=actor_id,
    )
    session.add(version)
    await session.flush()

    for tool_id in configuration.tool_ids:
        session.add(
            AgentTool(
                workspace_id=locked.workspace_id,
                agent_version_id=version.id,
                tool_definition_id=tool_id,
            )
        )
    await session.flush()

    locked.current_published_version_id = version.id
    locked.status = "published"
    await session.flush()
    agent.current_published_version_id = version.id
    agent.status = "published"
    return version


async def rollback_agent(
    session: AsyncSession, *, agent: Agent, version_id: uuid.UUID
) -> AgentVersion:
    version = await session.scalar(
        select(AgentVersion).where(AgentVersion.id == version_id, AgentVersion.agent_id == agent.id)
    )
    if version is None:
        raise ResourceNotFound("Agent version not found.")
    agent.current_published_version_id = version.id
    agent.status = "published"
    agent.draft_configuration = version.configuration
    await session.flush()
    return version


async def duplicate_agent(
    session: AsyncSession, *, agent: Agent, actor_id: uuid.UUID | None, name: str
) -> Agent:
    duplicate = Agent(
        workspace_id=agent.workspace_id,
        name=name,
        description=agent.description,
        status="draft",
        draft_configuration=agent.draft_configuration,
        created_by=actor_id,
    )
    session.add(duplicate)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("An agent with that name already exists in this workspace.") from exc
    return duplicate


async def resolve_version(
    session: AsyncSession, *, agent: Agent, version_id: uuid.UUID | None
) -> AgentVersion:
    """Resolve the immutable version a run will execute."""
    target = version_id or agent.current_published_version_id
    if target is None:
        raise ConflictError(
            "Publish this agent before running it. Runs always reference an immutable version."
        )
    version = await session.scalar(
        select(AgentVersion).where(AgentVersion.id == target, AgentVersion.agent_id == agent.id)
    )
    if version is None:
        raise ResourceNotFound("Agent version not found.")
    return version


def template_read(template: AgentTemplate) -> dict[str, Any]:
    return {
        "key": template.key,
        "name": template.name,
        "description": template.description,
        "category": template.category,
        "system_prompt": template.system_prompt,
        "tool_names": list(template.tool_names),
        "parameters": template.parameters.model_dump(mode="json"),
    }


__all__ = [
    "AGENT_TEMPLATES",
    "TEMPLATES_BY_KEY",
    "AgentTemplate",
    "archive_agent",
    "create_agent",
    "current_version_numbers",
    "delete_agent",
    "duplicate_agent",
    "get_agent",
    "get_agent_by_id",
    "list_agents",
    "list_versions",
    "member_role",
    "publish_agent",
    "resolve_version",
    "rollback_agent",
    "template_read",
    "update_agent",
    "validate_configuration",
]
