"""In-process cancellation signals for active runs.

Runs execute in the API process during this milestone; a module-level event per
run lets the cancel endpoint interrupt the model/tool wait without a shared
message broker. Before durable workers are introduced, the registry is rebuilt
from persisted state on startup, and any run left ``running`` after a restart
is marked failed by the recovery sweep.
"""

from __future__ import annotations

import asyncio
import uuid

_events: dict[uuid.UUID, asyncio.Event] = {}


def register(run_id: uuid.UUID) -> asyncio.Event:
    event = asyncio.Event()
    _events[run_id] = event
    return event


def request_cancellation(run_id: uuid.UUID) -> bool:
    """Signal a run to stop. Returns whether a live execution was found."""
    event = _events.get(run_id)
    if event is None:
        return False
    event.set()
    return True


def clear(run_id: uuid.UUID) -> None:
    _events.pop(run_id, None)


def active_runs() -> list[uuid.UUID]:
    return list(_events)


__all__ = ["active_runs", "clear", "register", "request_cancellation"]
