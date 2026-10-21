"""Event-loop factory for the Windows development server.

psycopg's async driver refuses to run on the ``ProactorEventLoop`` that uvicorn
selects by default on Windows. When ``loop`` is an import string, uvicorn passes
the imported callable straight to ``asyncio.run(loop_factory=...)``, which calls
it with no arguments and expects a *loop instance*. ``--reload`` forwards the
same value to the subprocess, so a module is used instead of a flag.

Deployed containers run Linux, where uvicorn's default loop already works.
"""

from __future__ import annotations

import asyncio


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """Create a selector event loop (the only async loop psycopg supports here)."""
    return asyncio.SelectorEventLoop()


__all__ = ["selector_loop_factory"]
