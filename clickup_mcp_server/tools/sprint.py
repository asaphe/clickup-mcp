import asyncio
import json
import time

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from clickup_mcp_server.client import clickup_client, parse_response
from clickup_mcp_server.config import settings
from clickup_mcp_server.models import SprintInfo, TaskSummary, map_task_summary
from clickup_mcp_server.tools.workspace import get_current_user_cached

_sprint_task: asyncio.Task[SprintInfo] | None = None


async def _fetch_sprint() -> SprintInfo:
    if not settings.development_space_id:
        raise RuntimeError(
            "DEVELOPMENT_SPACE_ID is not configured. "
            "Set it to use sprint detection."
        )
    if not settings.sprints_folder_id:
        raise RuntimeError(
            "SPRINTS_FOLDER_ID is not configured. "
            "Set it to use sprint detection."
        )

    response = await clickup_client.get(
        f"/space/{settings.development_space_id}/folder"
    )
    data = parse_response(response)

    now_ms = int(time.time() * 1000)
    sprints_folder = None

    folders_raw = data.get("folders", [])
    if not isinstance(folders_raw, list):
        raise RuntimeError("Unexpected /space folder response format")
    for folder in folders_raw:
        if not isinstance(folder, dict):
            continue
        if str(folder.get("id")) == settings.sprints_folder_id:
            sprints_folder = folder
            break

    if not sprints_folder:
        raise RuntimeError(f"Sprints folder {settings.sprints_folder_id} not found")

    best_list = None
    best_start = 0

    for lst in sprints_folder.get("lists", []):
        if not isinstance(lst, dict):
            continue
        start = lst.get("start_date")
        end = lst.get("due_date")
        if not start or not end:
            continue
        start_ms = int(start)
        end_ms = int(end)

        if start_ms <= now_ms <= end_ms and start_ms > best_start:
            best_list = lst
            best_start = start_ms

    if not best_list:
        all_lists = sprints_folder.get("lists", [])
        if isinstance(all_lists, list) and all_lists:
            future_lists = [
                lst
                for lst in all_lists
                if isinstance(lst, dict)
                and lst.get("start_date")
                and int(lst["start_date"]) > now_ms
            ]
            if future_lists:
                future_lists.sort(key=lambda x: int(x["start_date"]))
                best_list = future_lists[0]
            else:
                past_lists = [
                    lst
                    for lst in all_lists
                    if isinstance(lst, dict)
                    and lst.get("due_date")
                    and lst.get("start_date")
                ]
                if past_lists:
                    past_lists.sort(key=lambda x: int(x["due_date"]), reverse=True)
                    best_list = past_lists[0]

    if (
        not best_list
        or not best_list.get("start_date")
        or not best_list.get("due_date")
    ):
        raise RuntimeError("No sprint lists found in sprints folder")

    from datetime import UTC, datetime

    start_dt = datetime.fromtimestamp(int(best_list["start_date"]) / 1000, tz=UTC)
    end_dt = datetime.fromtimestamp(int(best_list["due_date"]) / 1000, tz=UTC)

    return SprintInfo(
        list_id=str(best_list["id"]),
        name=str(best_list.get("name", "")),
        start_date=start_dt.strftime("%Y-%m-%d"),
        end_date=end_dt.strftime("%Y-%m-%d"),
    )


async def get_current_sprint_cached() -> SprintInfo:
    global _sprint_task
    if _sprint_task is None:
        _sprint_task = asyncio.create_task(_fetch_sprint())
    try:
        return await _sprint_task
    except Exception:
        _sprint_task = None
        raise


def register_sprint_tools(server: FastMCP) -> None:
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_current_sprint() -> str:
        """Get the current sprint's info (list ID, name, date range).

        Auto-detected by date. Cached per session — use refresh_sprint_cache if
        the sprint rolled over.

        Requires DEVELOPMENT_SPACE_ID and SPRINTS_FOLDER_ID to be configured.
        """
        sprint = await get_current_sprint_cached()
        return sprint.model_dump_json(indent=2)

    @server.tool(
        annotations=ToolAnnotations(
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def refresh_sprint_cache() -> str:
        """Clear and re-fetch the cached sprint info.

        Use when a sprint rolls over mid-session or if get_current_sprint
        returns stale data.
        """
        global _sprint_task
        _sprint_task = None
        sprint = await get_current_sprint_cached()
        return sprint.model_dump_json(indent=2)

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        )
    )
    async def get_sprint_tasks(
        assignee: str | None = None,
        status: str | None = None,
    ) -> str:
        """List tasks in the current sprint, optionally filtered.

        Args:
            assignee: Filter by assignee. Use "me" for the current user, or a username.
            status: Filter by status (e.g., "in progress", "done", "todo").
        """
        sprint = await get_current_sprint_cached()
        tasks: list[TaskSummary] = []
        page = 0
        while True:
            response = await clickup_client.get(
                f"/list/{sprint.list_id}/task",
                params={
                    "subtasks": "true",
                    "include_closed": "true",
                    "page": str(page),
                },
            )
            data = parse_response(response)
            tasks_raw = data.get("tasks", [])
            if not isinstance(tasks_raw, list):
                break
            tasks.extend(map_task_summary(t) for t in tasks_raw if isinstance(t, dict))
            if data.get("last_page", True):
                break
            page += 1

        if assignee:
            target = assignee.lower()
            if target == "me":
                user = await get_current_user_cached()
                target = user.username.lower()
            tasks = [t for t in tasks if any(a.lower() == target for a in t.assignees)]

        if status:
            status_lower = status.lower()
            tasks = [t for t in tasks if t.status.lower() == status_lower]

        result = {
            "sprint": sprint.name,
            "total": len(tasks),
            "tasks": [t.model_dump() for t in tasks],
        }
        return json.dumps(result, indent=2)
