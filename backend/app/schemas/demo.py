"""Schemas for the explicit synthetic demonstration dataset."""

from __future__ import annotations

from pydantic import BaseModel


class DemoDatasetRead(BaseModel):
    """Whether the workspace has demo CRM rows, and how many."""

    seeded: bool
    customers: int
    deals: int


class DemoSeedResponse(DemoDatasetRead):
    """Result of an explicit demo-seed request."""

    created: bool
    companies: int
    contacts: int


__all__ = ["DemoDatasetRead", "DemoSeedResponse"]
