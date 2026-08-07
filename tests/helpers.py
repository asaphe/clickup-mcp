from mcp.types import CallToolResult


def get_tool_text(result: CallToolResult) -> str:
    """Extract text from an MCPServer call_tool result."""
    return result.content[0].text  # type: ignore[union-attr]
