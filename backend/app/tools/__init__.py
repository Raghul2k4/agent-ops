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
from app.tools.executor import (
    PreparedToolCall,
    ToolExecution,
    execute_prepared,
    execute_tool,
    prepare_tool_call,
    provider_tool_specs,
)

register_builtin_tools()

__all__ = [
    "PreparedToolCall",
    "Tool",
    "ToolApprovalRequiredError",
    "ToolContext",
    "ToolExecution",
    "ToolInput",
    "ToolRegistry",
    "ToolSpec",
    "execute_prepared",
    "execute_tool",
    "prepare_tool_call",
    "provider_tool_specs",
    "registry",
]
