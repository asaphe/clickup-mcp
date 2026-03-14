def get_tool_text(result: tuple[list[object], object]) -> str:
    """Extract text from FastMCP call_tool result tuple."""
    content_list = result[0]
    return content_list[0].text  # type: ignore[union-attr]
