"""Tool package: importing it registers the built-in tools."""

from app.tools.base import (
    Tool,
    ToolApprovalRequiredError,
    ToolContext,
    ToolInput,
    ToolRegistry,
    ToolSpec,
    registry,
)
from app.tools.builtin import register_builtin_tools
from app.tools.executor import ToolExecution, execute_tool, provider_tool_specs

register_builtin_tools()

__all__ = [
    "Tool",
    "ToolApprovalRequiredError",
    "ToolContext",
    "ToolExecution",
    "ToolInput",
    "ToolRegistry",
    "ToolSpec",
    "execute_tool",
    "provider_tool_specs",
    "registry",
]
