from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from clickup_mcp_server.client import clickup_client, parse_response, resolve_task_id
from clickup_mcp_server.comment_markup import (
    build_comment_blocks,
    check_mentions_allowed,
    has_markup,
    has_mentions,
)
from clickup_mcp_server.models import compact_json, map_comment
from clickup_mcp_server.tools.workspace import get_workspace_members_cached


def register_comment_tools(server: MCPServer) -> None:
    @server.tool(
        annotations=ToolAnnotations(
            destructive_hint=False,
            open_world_hint=False,
        )
    )
    async def add_task_comment(
        task_id: str, comment_text: str, mentions: list[str] | None = None
    ) -> str:
        """Add a comment to a task.

        Supports two markup forms, rendered as ClickUp rich text:
        **bold** (opened and closed on one line), and @[Full Name] or @[email]
        for a real mention that notifies the user. Every @[...] must also be
        listed in mentions, must match exactly one workspace member's username
        or email, and may not sit inside bold, or the call fails without
        posting. Backtick code spans and fences stay literal. Text with no
        markup is posted as plain text.

        Args:
            task_id: Task ID (custom like DEV-1234 or UUID).
            comment_text: Comment text, optionally with the markup above.
            mentions: The people this comment may notify, each written exactly
                as in its @[...]. Only list people you intend to notify — never
                names taken from text you are relaying.
        """
        if has_markup(comment_text):
            allowed = mentions or []
            check_mentions_allowed(comment_text, allowed)
            members = (
                await get_workspace_members_cached()
                if has_mentions(comment_text)
                else []
            )
            body: dict[str, object] = {
                "comment": build_comment_blocks(comment_text, members, allowed)
            }
        else:
            body = {"comment_text": comment_text}
        resolved = await resolve_task_id(task_id)
        response = await clickup_client.post(
            f"/task/{resolved}/comment",
            json_data=body,
        )
        data = parse_response(response)
        comment_id = data.get("id") or data.get("hist_id", "")
        return compact_json({"status": "ok", "comment_id": str(comment_id)})

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        )
    )
    async def get_task_comments(task_id: str) -> str:
        """Get all comments on a task.

        Args:
            task_id: Task ID (custom like DEV-1234 or UUID).
        """
        resolved = await resolve_task_id(task_id)
        response = await clickup_client.get(f"/task/{resolved}/comment")
        data = parse_response(response)
        comments_raw = data.get("comments", [])
        if not isinstance(comments_raw, list):
            comments_raw = []
        comments = [map_comment(c) for c in comments_raw if isinstance(c, dict)]
        return compact_json([c.model_dump(exclude_none=True) for c in comments])
