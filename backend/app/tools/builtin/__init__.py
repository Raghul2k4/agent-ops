"""Register the built-in tool implementations on import."""

from app.tools.builtin.crm import BUILTIN_TOOLS, register


def register_builtin_tools() -> None:
    """Idempotently register every built-in tool."""
    register()


__all__ = ["BUILTIN_TOOLS", "register_builtin_tools"]
