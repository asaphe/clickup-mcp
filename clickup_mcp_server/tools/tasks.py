import asyncio
import json

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from clickup_mcp_server.client import (
    ClickUpAPIError,
    clickup_client,
    is_custom_task_id,
    parse_response,
    resolve_task_id,
)
from clickup_mcp_server.config import TEAM_LABELS, settings
from clickup_mcp_server.models import (
    BulkUpdateResult,
    CreateTaskResult,
    EnsureFieldsResult,
    FieldCheckResult,
    SearchResult,
    TaskSummary,
    map_task_detail,
    map_task_summary,
)
from clickup_mcp_server.tools.sprint import get_current_sprint_cached
from clickup_mcp_server.tools.workspace import get_current_user_cached


def _build_custom_field_payload(team: str) -> list[dict[str, object]]:
    label_id = TEAM_LABELS.get(team.lower())
    if not label_id:
        return []
    return [{"id": settings.component_team_field_id, "value": [label_id]}]


async def _set_custom_field(task_uuid: str, field_id: object, value: object) -> None:
    resp = await clickup_client.post(
        f"/task/{task_uuid}/field/{field_id}",
        json_data={"value": value},
    )
    parse_response(resp)


def register_task_tools(server: FastMCP) -> None:
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=True,
        )
    )
    async def get_task(task_id: str, include_subtasks: bool = True) -> str:
        """Get detailed info for a task.

        Accepts custom IDs (DEV-1234) or UUIDs. Returns status, assignees,
        description, subtasks, priority, team label, and more.

        Args:
            task_id: Task ID (custom like DEV-1234 or UUID).
            include_subtasks: Include subtask details (default: true).
        """
        params: dict[str, str] = {}
        if is_custom_task_id(task_id):
            params["custom_task_ids"] = "true"
            params["team_id"] = settings.workspace_id
        if include_subtasks:
            params["include_subtasks"] = "true"

        response = await clickup_client.get(f"/task/{task_id}", params=params or None)
        data = parse_response(response)
        detail = map_task_detail(data)
        return detail.model_dump_json(indent=2)

    @server.tool(
        annotations=ToolAnnotations(
            destructiveHint=False,
            openWorldHint=False,
        )
    )
    async def create_task(
        name: str,
        list_id: str,
        description: str | None = None,
        assignee_id: int | None = None,
        status: str = "in progress",
        points: float | None = None,
        team: str | None = None,
        parent_task_id: str | None = None,
        priority: int | None = None,
    ) -> str:
        """Create a new task in a specific list.

        For sprint tasks, prefer create_sprint_task which auto-resolves the sprint list.

        Args:
            name: Task title.
            list_id: Target list ID. Use get_current_sprint or get_workspace_hierarchy to find IDs.
            description: Task description (markdown supported).
            assignee_id: User ID to assign. Use get_current_user to find your ID.
            status: Initial status (default: "in progress").
            points: Story points.
            team: Component/Team label. See list_teams for available values.
            parent_task_id: Parent task ID for creating subtasks.
            priority: 1=urgent, 2=high, 3=normal, 4=low.
        """
        body: dict[str, object] = {"name": name, "status": status}
        if description:
            body["description"] = description
        if assignee_id:
            body["assignees"] = [assignee_id]
        if points is not None:
            body["points"] = points
        if priority is not None:
            body["priority"] = priority
        if parent_task_id:
            resolved_parent = await resolve_task_id(parent_task_id)
            body["parent"] = resolved_parent
        if team:
            cf = _build_custom_field_payload(team)
            if cf:
                body["custom_fields"] = cf

        response = await clickup_client.post(f"/list/{list_id}/task", json_data=body)
        data = parse_response(response)

        custom_id = data.get("custom_id")
        if not custom_id:
            await asyncio.sleep(1.0)
            refetch = await clickup_client.get(f"/task/{data['id']}")
            refetch_data = parse_response(refetch)
            custom_id = refetch_data.get("custom_id")

        status_data = data.get("status")
        result = CreateTaskResult(
            id=str(data["id"]),
            custom_id=custom_id,  # type: ignore[arg-type]
            name=str(data.get("name", "")),
            url=f"https://app.clickup.com/t/{data['id']}",
            status=status_data.get("status", "unknown")  # type: ignore[union-attr]
            if isinstance(status_data, dict)
            else "unknown",
        )
        return result.model_dump_json(indent=2)

    @server.tool(
        annotations=ToolAnnotations(
            destructiveHint=False,
            openWorldHint=False,
        )
    )
    async def create_sprint_task(
        name: str,
        team: str | None = None,
        description: str | None = None,
        points: float = 1.0,
        assign_to_me: bool = True,
        parent_task_id: str | None = None,
    ) -> str:
        """Create a task in the current sprint with sensible defaults.

        Auto-resolves the current sprint list and (optionally) the current user.

        Requires DEVELOPMENT_SPACE_ID and SPRINTS_FOLDER_ID to be configured.

        Args:
            name: Task title.
            team: Component/Team label. See list_teams for available values.
            description: Task description.
            points: Story points (default: 1.0).
            assign_to_me: Assign to the authenticated user (default: true).
            parent_task_id: Parent task ID (custom like DEV-1234 or UUID) for creating subtasks.
        """
        sprint = await get_current_sprint_cached()
        assignee_id = None
        if assign_to_me:
            user = await get_current_user_cached()
            assignee_id = user.id

        return await create_task(
            name=name,
            list_id=sprint.list_id,
            description=description,
            assignee_id=assignee_id,
            points=points,
            team=team,
            parent_task_id=parent_task_id,
        )

    @server.tool(
        annotations=ToolAnnotations(
            destructiveHint=False,
            openWorldHint=False,
        )
    )
    async def update_task(
        task_id: str,
        name: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        points: float | None = None,
        description: str | None = None,
        append_description: str | None = None,
        assignee_add: int | None = None,
        assignee_remove: int | None = None,
    ) -> str:
        """Update fields on a task. Only specified fields are changed.

        Args:
            task_id: Task ID (custom like DEV-1234 or UUID).
            name: New task name.
            status: New status (e.g., "done", "in progress", "in review").
            priority: 1=urgent, 2=high, 3=normal, 4=low.
            points: Story points.
            description: Replace entire description. Use append_description to add text instead.
            append_description: Append text to existing description (separated by newline).
            assignee_add: User ID to add as assignee.
            assignee_remove: User ID to remove from assignees.
        """
        resolved = await resolve_task_id(task_id)
        body: dict[str, object] = {}

        if name is not None:
            body["name"] = name
        if status is not None:
            body["status"] = status
        if priority is not None:
            body["priority"] = priority
        if points is not None:
            body["points"] = points

        if append_description is not None:
            current_resp = await clickup_client.get(f"/task/{resolved}")
            current_data = parse_response(current_resp)
            existing = current_data.get("description", "") or ""
            separator = "\n\n---\n\n" if existing else ""
            body["description"] = f"{existing}{separator}{append_description}"
        elif description is not None:
            body["description"] = description

        assignees: dict[str, list[int]] = {}
        if assignee_add is not None:
            assignees["add"] = [assignee_add]
        if assignee_remove is not None:
            assignees["rem"] = [assignee_remove]
        if assignees:
            body["assignees"] = assignees

        if not body:
            return "Error: No fields to update. Provide at least one field to change."

        response = await clickup_client.put(f"/task/{resolved}", json_data=body)
        data = parse_response(response)
        detail = map_task_detail(data)
        return detail.model_dump_json(indent=2)

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=True,
        )
    )
    async def search_tasks(
        query: str | None = None,
        status: list[str] | None = None,
        assignee_id: int | None = None,
        list_id: str | None = None,
        include_closed: bool = False,
        date_created_after: str | None = None,
        date_updated_after: str | None = None,
        page: int = 0,
    ) -> str:
        """Search tasks across the workspace.

        Supports filtering by query text, status, assignee, list, and dates.
        Returns paginated results with has_more indicator.

        Note: ``query`` is applied as a client-side filter after fetching each page
        from the API. The ``has_more`` flag reflects the API's pagination state,
        not whether additional *matching* results exist. Callers should continue
        paginating while ``has_more`` is true if they need exhaustive results.

        Args:
            query: Text search query (client-side filtered — see note above).
            status: Filter by status(es).
            assignee_id: Filter by assignee user ID. Use get_current_user for your ID.
            list_id: Limit to a specific list.
            include_closed: Include closed/done tasks (default: false).
            date_created_after: ISO date or Unix millis — only tasks created after this.
            date_updated_after: ISO date or Unix millis — only tasks updated after this.
            page: Page number (0-indexed). Check has_more in response for pagination.
        """
        params: list[tuple[str, str]] = [("page", str(page))]
        if include_closed:
            params.append(("include_closed", "true"))
        if list_id:
            params.append(("list_ids[]", list_id))
        if assignee_id:
            params.append(("assignees[]", str(assignee_id)))
        if status:
            for s in status:
                params.append(("statuses[]", s))
        if date_created_after:
            params.append(("date_created_gt", _to_millis(date_created_after)))
        if date_updated_after:
            params.append(("date_updated_gt", _to_millis(date_updated_after)))

        response = await clickup_client.get(
            f"/team/{settings.workspace_id}/task",
            params=params,
        )
        data = parse_response(response)
        tasks_raw = data.get("tasks", [])
        if not isinstance(tasks_raw, list):
            tasks_raw = []

        tasks = [map_task_summary(t) for t in tasks_raw if isinstance(t, dict)]

        if query:
            query_lower = query.lower()
            tasks = [
                t
                for t in tasks
                if query_lower in t.name.lower()
                or (t.custom_id and query_lower in t.custom_id.lower())
            ]

        last_page = data.get("last_page", False)

        result = SearchResult(
            tasks=tasks,
            total=len(tasks),
            page=page,
            has_more=not last_page if isinstance(last_page, bool) else True,
        )
        return result.model_dump_json(indent=2)

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=True,
        )
    )
    async def get_my_tasks(
        status: list[str] | None = None,
        date_updated_after: str | None = None,
        include_closed: bool = False,
        page: int = 0,
    ) -> str:
        """Get tasks assigned to the current user across all lists.

        Convenience wrapper around search_tasks with automatic user resolution.

        Args:
            status: Filter by status(es).
            date_updated_after: ISO date or Unix millis — only tasks updated after this.
            include_closed: Include closed/done tasks (default: false).
            page: Page number (0-indexed).
        """
        user = await get_current_user_cached()
        return await search_tasks(
            assignee_id=user.id,
            status=status,
            date_updated_after=date_updated_after,
            include_closed=include_closed,
            page=page,
        )

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        )
    )
    async def get_list_tasks(
        list_id: str,
        status: str | None = None,
        include_closed: bool = False,
    ) -> str:
        """Get all tasks in a specific list (backlog, epic, tech debt, etc.).

        Args:
            list_id: List ID. Use get_workspace_hierarchy to discover list IDs.
            status: Filter by status (e.g., "todo", "in progress").
            include_closed: Include closed/done tasks (default: false).
        """
        base_params: dict[str, str] = {"subtasks": "true"}
        if include_closed:
            base_params["include_closed"] = "true"
        if status:
            base_params["statuses[]"] = status

        tasks: list[TaskSummary] = []
        page = 0
        while True:
            params = {**base_params, "page": str(page)}
            response = await clickup_client.get(f"/list/{list_id}/task", params=params)
            data = parse_response(response)
            tasks_raw = data.get("tasks", [])
            if not isinstance(tasks_raw, list):
                break
            tasks.extend(map_task_summary(t) for t in tasks_raw if isinstance(t, dict))
            if data.get("last_page", True):
                break
            page += 1
        result = {
            "list_id": list_id,
            "total": len(tasks),
            "tasks": [t.model_dump() for t in tasks],
        }
        return json.dumps(result, indent=2)

    @server.tool(
        annotations=ToolAnnotations(
            destructiveHint=False,
            openWorldHint=False,
        )
    )
    async def move_task_to_list(task_id: str, list_id: str) -> str:
        """Move a task to a different list.

        Args:
            task_id: Task ID (custom like DEV-1234 or UUID).
            list_id: Target list ID.
        """
        resolved = await resolve_task_id(task_id)
        response = await clickup_client.post(f"/list/{list_id}/task/{resolved}")
        parse_response(response)
        return json.dumps(
            {"status": "ok", "task_id": task_id, "moved_to_list": list_id}
        )

    @server.tool(
        annotations=ToolAnnotations(
            destructiveHint=True,
            openWorldHint=False,
        )
    )
    async def bulk_update_tasks(
        task_ids: list[str],
        status: str | None = None,
        assignee_add: int | None = None,
        team: str | None = None,
        points: float | None = None,
    ) -> str:
        """Update multiple tasks at once. Verify the task_ids list before calling.

        This is a convenience tool that applies the same update to multiple tasks.
        Partial failures are reported — some tasks may succeed while others fail.

        Args:
            task_ids: List of task IDs (custom or UUID). Double-check before calling.
            status: Set status on all tasks.
            assignee_add: Add assignee (user ID) to all tasks.
            team: Set Component/Team label on all tasks.
            points: Set story points on all tasks.
        """
        if not task_ids:
            return "Error: task_ids list is empty."

        updated: list[str] = []
        failed: list[dict[str, str]] = []

        for tid in task_ids:
            try:
                resolved = await resolve_task_id(tid)
                body: dict[str, object] = {}
                if status:
                    body["status"] = status
                if points is not None:
                    body["points"] = points
                if assignee_add:
                    body["assignees"] = {"add": [assignee_add]}
                if body:
                    response = await clickup_client.put(
                        f"/task/{resolved}", json_data=body
                    )
                    parse_response(response)
                if team:
                    cf = _build_custom_field_payload(team)
                    if cf:
                        await _set_custom_field(resolved, cf[0]["id"], cf[0]["value"])
                updated.append(tid)
            except (ClickUpAPIError, Exception) as exc:
                failed.append({"task_id": tid, "error": str(exc)})

        result = BulkUpdateResult(updated=updated, failed=failed, total=len(task_ids))
        return result.model_dump_json(indent=2)

    @server.tool(
        annotations=ToolAnnotations(
            openWorldHint=False,
        )
    )
    async def ensure_task_fields(
        task_ids: list[str],
        required_fields: list[str] | None = None,
        fix: bool = False,
        default_assignee_id: int | None = None,
        default_team: str | None = None,
        default_points: float | None = None,
    ) -> str:
        """Check (and optionally fix) that tasks have required fields set.

        By default checks assignee, team, and points. Useful for sprint compliance.

        Args:
            task_ids: List of task IDs to check.
            required_fields: Fields to check. Default: ["assignee", "team", "points"].
            fix: If true, apply defaults to fill missing fields. If false, report only.
            default_assignee_id: User ID to assign if assignee is missing and fix=true.
            default_team: Team label to set if team is missing and fix=true.
            default_points: Points to set if missing and fix=true.
        """
        fields = required_fields or ["assignee", "team", "points"]
        issues: list[FieldCheckResult] = []

        for tid in task_ids:
            try:
                params: dict[str, str] = {}
                if is_custom_task_id(tid):
                    params["custom_task_ids"] = "true"
                    params["team_id"] = settings.workspace_id

                response = await clickup_client.get(
                    f"/task/{tid}", params=params or None
                )
                data = parse_response(response)

                missing: list[str] = []
                assignees_raw = data.get("assignees", [])
                has_assignee = (
                    isinstance(assignees_raw, list) and len(assignees_raw) > 0
                )
                if "assignee" in fields and not has_assignee:
                    missing.append("assignee")

                detail = map_task_detail(data)
                if "team" in fields and not detail.team:
                    missing.append("team")
                if "points" in fields and detail.points is None:
                    missing.append("points")

                if missing:
                    fixed = False
                    if fix:
                        fix_body: dict[str, object] = {}
                        if "assignee" in missing and default_assignee_id:
                            fix_body["assignees"] = {"add": [default_assignee_id]}
                        if "points" in missing and default_points is not None:
                            fix_body["points"] = default_points
                        resolved = await resolve_task_id(tid)
                        if fix_body:
                            fix_resp = await clickup_client.put(
                                f"/task/{resolved}", json_data=fix_body
                            )
                            parse_response(fix_resp)
                        if "team" in missing and default_team:
                            cf = _build_custom_field_payload(default_team)
                            if cf:
                                await _set_custom_field(
                                    resolved, cf[0]["id"], cf[0]["value"]
                                )
                        if fix_body or ("team" in missing and default_team):
                            fixed = True

                    issues.append(
                        FieldCheckResult(
                            task_id=str(data["id"]),
                            custom_id=data.get("custom_id"),  # type: ignore[arg-type]
                            name=str(data.get("name", "")),
                            missing_fields=missing,
                            fixed=fixed,
                        )
                    )
            except (ClickUpAPIError, Exception) as exc:
                issues.append(
                    FieldCheckResult(
                        task_id=tid,
                        custom_id=None,
                        name=f"Error: {exc}",
                        missing_fields=[],
                        fixed=False,
                    )
                )

        result = EnsureFieldsResult(
            checked=len(task_ids),
            issues=issues,
            all_compliant=len(issues) == 0,
        )
        return result.model_dump_json(indent=2)


def _to_millis(value: str) -> str:
    if value.isdigit():
        if len(value) > 10:
            return value
        return str(int(value) * 1000)
    from datetime import UTC, datetime

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return str(int(dt.timestamp() * 1000))
    except ValueError:
        return value
