"""Synthetic CRM ORM mappings.

Every record is workspace-scoped and carries ``is_demo`` so demo rows can be
identified (and excluded from live analytics later) instead of being silently
mixed with real data.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CUSTOMER_STATUSES = ("active", "prospect", "churned")
DEAL_STAGES = ("prospecting", "qualified", "proposal", "negotiation", "won", "lost")
CONTACT_CHANNELS = ("email", "call", "meeting", "note")


class CrmCompany(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "crm_companies"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="crm_companies_name_unique"),
        Index("ix_crm_companies_workspace_id", "workspace_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CrmCustomer(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "crm_customers"
    __table_args__ = (
        CheckConstraint(f"status IN {CUSTOMER_STATUSES}", name="crm_customers_status_valid"),
        Index("ix_crm_customers_workspace_id", "workspace_id"),
        Index("ix_crm_customers_company_id", "company_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CrmDeal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crm_deals"
    __table_args__ = (
        CheckConstraint(f"stage IN {DEAL_STAGES}", name="crm_deals_stage_valid"),
        CheckConstraint("probability BETWEEN 0 AND 100", name="crm_deals_probability_valid"),
        CheckConstraint("amount >= 0", name="crm_deals_amount_valid"),
        Index("ix_crm_deals_workspace_last_contact", "workspace_id", "last_contacted_at"),
        Index("ix_crm_deals_workspace_stage", "workspace_id", "stage"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crm_customers.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="prospecting")
    probability: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    owner_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CrmContact(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "crm_contacts"
    __table_args__ = (
        CheckConstraint(f"channel IN {CONTACT_CHANNELS}", name="crm_contacts_channel_valid"),
        Index("ix_crm_contacts_workspace_contacted", "workspace_id", "contacted_at"),
        Index("ix_crm_contacts_deal_id", "deal_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crm_customers.id", ondelete="CASCADE"), nullable=False
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_deals.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    contacted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FollowupDraft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An isolated internal draft. Creating one never sends anything."""

    __tablename__ = "followup_drafts"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'discarded')", name="followup_drafts_status_valid"),
        Index("ix_followup_drafts_workspace_created", "workspace_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crm_customers.id", ondelete="CASCADE"), nullable=False
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_deals.id", ondelete="SET NULL"), nullable=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="email")
    subject: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )


__all__ = [
    "CONTACT_CHANNELS",
    "CUSTOMER_STATUSES",
    "DEAL_STAGES",
    "CrmCompany",
    "CrmContact",
    "CrmCustomer",
    "CrmDeal",
    "FollowupDraft",
]
