import asyncio

from mcp.server.fastmcp import FastMCP
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


async def _fetch_live_team_label_options(space_id: str) -> dict[str, str]:
    """Fetch live Component/Team field options from ClickUp, keyed by ID."""
    validate_space_id(space_id)
    response = await clickup_client.get(f"/space/{space_id}/field")
    data = parse_response(response)
    fields_raw = data.get("fields", [])
    if not isinstance(fields_raw, list):
        return {}

    for field in fields_raw:
        if (
            not isinstance(field, dict)
            or field.get("id") != settings.component_team_field_id
        ):
            continue
        type_config = field.get("type_config", {})
        options_raw = (
            type_config.get("options", []) if isinstance(type_config, dict) else []
        )
        return {
            str(option["id"]): str(option.get("name", ""))
            for option in options_raw
            if isinstance(option, dict) and "id" in option
        }
    return {}


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
        return compact_json(user)

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
        response = await clickup_client.post(
            f"/task/{resolved}/tag/{encode_path_segment(tag_name)}"
        )
        parse_response(response)
        return compact_json({"status": "ok", "task_id": task_id, "tag": tag_name})

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
        return compact_json(TEAM_LABELS)

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=True,
        )
    )
    async def check_team_labels(space_id: str | None = None) -> str:
        """Audit configured team label IDs against live ClickUp field options.

        Args:
            space_id: Space to check. Defaults to the configured development space.
        """
        if not TEAM_LABELS:
            return compact_json(
                TeamLabelsAudit(
                    configured=False,
                    in_sync=False,
                    message=(
                        "CLICKUP_TEAM_LABELS is not configured; no team labels can "
                        "be reconciled."
                    ),
                )
            )

        sid = space_id or settings.development_space_id
        if not sid:
            return compact_json(
                TeamLabelsAudit(
                    configured=True,
                    in_sync=False,
                    message=(
                        "No space_id provided and DEVELOPMENT_SPACE_ID is not "
                        "configured."
                    ),
                )
            )

        live_options = await _fetch_live_team_label_options(sid)
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
                configured=True,
                stale=stale,
                valid=valid,
                unmapped_live_options=unmapped_live_options,
                in_sync=not stale,
            )
        )
