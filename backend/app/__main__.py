"""Run the API with ``python -m app``.

The Windows selector event loop is selected through uvicorn's loop-factory hook
(``app.loop``): psycopg's async driver refuses to run on the default
ProactorEventLoop. Deployed containers run Linux and use uvicorn's default.
"""

from __future__ import annotations

import sys

import uvicorn


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload="--reload" in sys.argv,
        log_level="info",
        loop="app.loop:selector_loop_factory" if sys.platform == "win32" else "auto",
    )


if __name__ == "__main__":
    main()
