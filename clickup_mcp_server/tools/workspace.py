import asyncio

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from clickup_mcp_server.client import (
    clickup_client,
    encode_path_segment,
    parse_response,
    resolve_task_id,
    validate_space_id,
)
from clickup_mcp_server.config import TEAM_LABELS, settings
from clickup_mcp_server.models import TeamLabelsAudit, UserInfo, compact_json
from clickup_mcp_server.team_labels import fetch_team_options, get_team_labels

_user_task: asyncio.Task[UserInfo] | None = None


async def _fetch_current_user() -> UserInfo:
    response = await clickup_client.get("/user")
    data = parse_response(response)
    user = data.get("user", {})
    if not isinstance(user, dict):
        raise TypeError("Unexpected /user response format")
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
        return await asyncio.shield(_user_task)
    except Exception:
        _user_task = None
        raise


_members_task: asyncio.Task[list[UserInfo]] | None = None


async def _fetch_workspace_members() -> list[UserInfo]:
    response = await clickup_client.get("/team")
    data = parse_response(response)
    teams_raw = data.get("teams", [])
    if not isinstance(teams_raw, list):
        raise TypeError("Unexpected /team response format")
    for team in teams_raw:
        if not isinstance(team, dict) or str(team.get("id")) != settings.workspace_id:
            continue
        members_raw = team.get("members", [])
        if not isinstance(members_raw, list):
            raise TypeError("Unexpected /team response format")
        members: list[UserInfo] = []
        for member in members_raw:
            user = member.get("user") if isinstance(member, dict) else None
            if not isinstance(user, dict) or user.get("id") is None:
                continue
            members.append(
                UserInfo(
                    id=int(user["id"]),
                    username=str(user.get("username") or ""),
                    email=str(user.get("email") or ""),
                )
            )
        return members
    raise ToolError(f"Workspace {settings.workspace_id} not found in /team")


def _forget_members_task(task: asyncio.Task[list[UserInfo]]) -> None:
    global _members_task
    if _members_task is task:
        _members_task = None


async def get_workspace_members() -> list[UserInfo]:
    """Fetch the current workspace members; concurrent callers share one request."""
    global _members_task
    if _members_task is None:
        _members_task = asyncio.create_task(_fetch_workspace_members())
        _members_task.add_done_callback(_forget_members_task)
    return await asyncio.shield(_members_task)


def register_workspace_tools(server: MCPServer) -> None:
    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def get_current_user() -> str:
        """Get the current authenticated user's info (ID, username, email).

        Cached per session. Use the ID for assignee operations.
        """
        user = await get_current_user_cached()
        return compact_json(user)

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=True,
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
            return compact_json(
                {
                    "error": "No space_id provided and DEVELOPMENT_SPACE_ID is not configured."
                }
            )
        validate_space_id(sid)
        response = await clickup_client.get(f"/space/{sid}/folder")
        data = parse_response(response)

        result: list[dict[str, object]] = []
        folders_raw = data.get("folders", [])
        if not isinstance(folders_raw, list):
            return compact_json([])
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

        return compact_json(result)

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            idempotent_hint=True,
            open_world_hint=False,
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
            destructive_hint=False,
            open_world_hint=False,
        )
    )
    async def add_tag_to_task(task_id: str, tag_name: str) -> str:
        """Add a tag to a task.

        Args:
            task_id: Task ID (custom like DEV-1234 or UUID).
            tag_name: Tag name to add.
        """
        resolved = await resolve_task_id(task_id)
        response = await clickup_client.post(
            f"/task/{resolved}/tag/{encode_path_segment(tag_name)}"
        )
        parse_response(response)
        return compact_json({"status": "ok", "task_id": task_id, "tag": tag_name})

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        )
    )
    async def list_teams() -> str:
        """List the team names to pass as `team`, with their Component/Team option IDs.

        Names are the field's live labels lowercased with spaces as hyphens, plus any
        CLICKUP_TEAM_LABELS aliases whose option is still live. A name that matches
        two different options is omitted because it cannot be resolved.
        """
        return compact_json(await get_team_labels())

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=True,
        )
    )
    async def check_team_labels(space_id: str | None = None) -> str:
        """Audit the CLICKUP_TEAM_LABELS aliases against live Component/Team options.

        Reports stale aliases (their option ID is no longer live) and live options
        that no alias points at. Aliases are optional, so with none configured every
        live option is reported as unmapped and the result is in sync.

        Args:
            space_id: Space to check. Defaults to the configured development space.
        """
        sid = space_id or settings.development_space_id
        if not sid:
            return compact_json(
                TeamLabelsAudit(
                    configured=bool(TEAM_LABELS),
                    in_sync=False,
                    message=(
                        "No space_id provided and DEVELOPMENT_SPACE_ID is not "
                        "configured."
                    ),
                )
            )

        live_options = await fetch_team_options(sid)
        stale = {
            team: label_id
            for team, label_id in TEAM_LABELS.items()
            if label_id not in live_options
        }
        valid = [team for team in TEAM_LABELS if team not in stale]
        unmapped_live_options = {
            option_id: name
            for option_id, name in live_options.items()
            if option_id not in TEAM_LABELS.values()
        }

        return compact_json(
            TeamLabelsAudit(
                configured=bool(TEAM_LABELS),
                stale=stale,
                valid=valid,
                unmapped_live_options=unmapped_live_options,
                in_sync=not stale,
            )
        )
