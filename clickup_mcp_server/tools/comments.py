import json

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from clickup_mcp_server.client import clickup_client, parse_response, resolve_task_id
from clickup_mcp_server.models import map_comment


def register_comment_tools(server: FastMCP) -> None:
    @server.tool(
        annotations=ToolAnnotations(
            destructiveHint=False,
            openWorldHint=False,
        )
    )
    async def add_task_comment(task_id: str, comment_text: str) -> str:
        """Add a comment to a task.

        Args:
            task_id: Task ID (custom like DEV-1234 or UUID).
            comment_text: Comment text (plain text).
        """
        resolved = await resolve_task_id(task_id)
        response = await clickup_client.post(
            f"/task/{resolved}/comment",
            json_data={"comment_text": comment_text},
        )
        data = parse_response(response)
        comment_id = data.get("id") or data.get("hist_id", "")
        return json.dumps({"status": "ok", "comment_id": str(comment_id)})

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
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
        return json.dumps([c.model_dump() for c in comments], indent=2)
