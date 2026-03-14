import asyncio
import json

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from clickup_mcp_server.client import (
    clickup_client,
    parse_response,
    resolve_task_id,
)
from clickup_mcp_server.config import TEAM_LABELS, settings
from clickup_mcp_server.models import UserInfo

_user_task: asyncio.Task[UserInfo] | None = None


async def _fetch_current_user() -> UserInfo:
    response = await clickup_client.get("/user")
    data = parse_response(response)
    user = data.get("user", {})
    if not isinstance(user, dict):
        raise RuntimeError("Unexpected /user response format")
    return UserInfo(
        id=int(user["id"]),  # type: ignore[arg-type]
        username=str(user.get("username", "")),
        email=str(user.get("email", "")),
    )


async def get_current_user_cached() -> UserInfo:
    global _user_task
    if _user_task is None:
        _user_task = asyncio.create_task(_fetch_current_user())
    try:
        return await _user_task
    except Exception:
        _user_task = None
        raise


def register_workspace_tools(server: FastMCP) -> None:
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_current_user() -> str:
        """Get the current authenticated user's info (ID, username, email).

        Cached per session. Use the ID for assignee operations.
        """
        user = await get_current_user_cached()
        return user.model_dump_json(indent=2)

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=True,
        )
    )
    async def get_workspace_hierarchy(
        space_id: str | None = None,
        max_depth: int = 2,
    ) -> str:
        """Browse the workspace folder/list hierarchy.

        Returns folders and lists in the given space. Use this to discover list IDs
        for creating tasks or browsing backlogs.

        Args:
            space_id: Space to browse. Defaults to the configured DEVELOPMENT_SPACE_ID.
            max_depth: How deep to recurse (1=folders only, 2=folders+lists, 3=+sublists).
        """
        sid = space_id or settings.development_space_id
        if not sid:
            return json.dumps(
                {"error": "No space_id provided and DEVELOPMENT_SPACE_ID is not configured."}
            )
        response = await clickup_client.get(f"/space/{sid}/folder")
        data = parse_response(response)

        result: list[dict[str, object]] = []
        folders_raw = data.get("folders", [])
        if not isinstance(folders_raw, list):
            return json.dumps([])
        for folder in folders_raw:
            if not isinstance(folder, dict):
                continue
            folder_entry: dict[str, object] = {
                "id": folder["id"],
                "name": folder["name"],
                "type": "folder",
            }
            if max_depth >= 2:
                lists = []
                for lst in folder.get("lists", []):
                    if not isinstance(lst, dict):
                        continue
                    list_entry: dict[str, object] = {
                        "id": lst["id"],
                        "name": lst["name"],
                    }
                    lists.append(list_entry)
                folder_entry["lists"] = lists
            result.append(folder_entry)

        return json.dumps(result, indent=2)

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def task_url(task_id: str) -> str:
        """Get the ClickUp URL for a task. Accepts custom IDs (DEV-1234) or UUIDs.

        Args:
            task_id: Task ID (custom like DEV-1234 or UUID).
        """
        resolved = await resolve_task_id(task_id)
        return f"https://app.clickup.com/t/{resolved}"

    @server.tool(
        annotations=ToolAnnotations(
            destructiveHint=False,
            openWorldHint=False,
        )
    )
    async def add_tag_to_task(task_id: str, tag_name: str) -> str:
        """Add a tag to a task.

        Args:
            task_id: Task ID (custom like DEV-1234 or UUID).
            tag_name: Tag name to add.
        """
        resolved = await resolve_task_id(task_id)
        response = await clickup_client.post(f"/task/{resolved}/tag/{tag_name}")
        parse_response(response)
        return json.dumps({"status": "ok", "task_id": task_id, "tag": tag_name})

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        )
    )
    async def list_teams() -> str:
        """List available Component/Team labels and their IDs.

        Use team names (lowercase) when creating or updating tasks with a team parameter.
        Returns the configured CLICKUP_TEAM_LABELS mapping, or an empty object if not configured.
        """
        return json.dumps(TEAM_LABELS, indent=2)
