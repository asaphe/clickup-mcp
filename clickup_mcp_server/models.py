from pydantic import BaseModel, Field

from clickup_mcp_server.config import TEAM_LABELS, settings


class SprintInfo(BaseModel):
    list_id: str
    name: str
    start_date: str
    end_date: str


class UserInfo(BaseModel):
    id: int
    username: str
    email: str


class TaskSummary(BaseModel):
    id: str
    custom_id: str | None
    name: str
    status: str
    assignees: list[str]
    points: float | None
    url: str
    list_name: str | None = None
    date_created: str | None = None
    date_updated: str | None = None
    date_done: str | None = None


class TaskDetail(TaskSummary):
    description: str | None = None
    priority: str | None = None
    tags: list[str] = Field(default_factory=list)
    parent: str | None = None
    parent_custom_id: str | None = None
    subtasks: list[TaskSummary] = Field(default_factory=list)
    team: str | None = None


class TaskComment(BaseModel):
    id: str
    comment_text: str
    user: str
    date: str


class CreateTaskResult(BaseModel):
    id: str
    custom_id: str | None
    name: str
    url: str
    status: str


class SearchResult(BaseModel):
    tasks: list[TaskSummary]
    total: int
    page: int
    has_more: bool


class BulkUpdateResult(BaseModel):
    updated: list[str]
    failed: list[dict[str, str]]
    total: int


class FieldCheckResult(BaseModel):
    task_id: str
    custom_id: str | None
    name: str
    missing_fields: list[str]
    fixed: bool


class EnsureFieldsResult(BaseModel):
    checked: int
    issues: list[FieldCheckResult]
    all_compliant: bool


class SprintReportTask(BaseModel):
    custom_id: str | None
    name: str
    status: str
    priority: str | None
    tags: list[str]
    pr_links: list[str]
    subtasks_summary: str | None


class AtRiskItem(BaseModel):
    custom_id: str | None
    name: str
    assignee: str | None
    reason: str


class SprintReport(BaseModel):
    sprint_name: str
    date_range: str
    summary: dict[str, int]
    by_assignee: dict[str, list[SprintReportTask]]
    unassigned: list[SprintReportTask]
    at_risk: list[AtRiskItem]


def map_task_summary(raw: dict[str, object]) -> TaskSummary:
    assignees_raw = raw.get("assignees", [])
    assignees = (
        [a["username"] for a in assignees_raw if isinstance(a, dict)]
        if isinstance(assignees_raw, list)
        else []
    )
    list_data = raw.get("list")
    list_name = list_data.get("name") if isinstance(list_data, dict) else None
    status_data = raw.get("status", {})
    status = (
        status_data.get("status", "unknown")
        if isinstance(status_data, dict)
        else "unknown"
    )

    return TaskSummary(
        id=str(raw["id"]),
        custom_id=raw.get("custom_id"),  # type: ignore[arg-type]
        name=str(raw.get("name", "")),
        status=status,
        assignees=assignees,
        points=raw.get("points"),  # type: ignore[arg-type]
        url=f"https://app.clickup.com/t/{raw['id']}",
        list_name=list_name,
        date_created=raw.get("date_created"),  # type: ignore[arg-type]
        date_updated=raw.get("date_updated"),  # type: ignore[arg-type]
        date_done=raw.get("date_done"),  # type: ignore[arg-type]
    )


def map_task_detail(raw: dict[str, object]) -> TaskDetail:
    subtasks_raw = raw.get("subtasks", [])
    subtasks = (
        [map_task_summary(s) for s in subtasks_raw]
        if isinstance(subtasks_raw, list)
        else []
    )

    team = None
    custom_fields = raw.get("custom_fields", [])
    if isinstance(custom_fields, list) and settings.component_team_field_id:
        for cf in custom_fields:
            if (
                isinstance(cf, dict)
                and cf.get("id") == settings.component_team_field_id
            ):
                values = cf.get("value", [])
                if values and isinstance(values, list):
                    label_id = values[0] if values else None
                    team = next(
                        (k for k, v in TEAM_LABELS.items() if v == label_id), None
                    )

    assignees_raw = raw.get("assignees", [])
    assignees = (
        [a["username"] for a in assignees_raw if isinstance(a, dict)]
        if isinstance(assignees_raw, list)
        else []
    )
    status_data = raw.get("status", {})
    status = (
        status_data.get("status", "unknown")
        if isinstance(status_data, dict)
        else "unknown"
    )
    priority_data = raw.get("priority")
    priority = (
        priority_data.get("priority") if isinstance(priority_data, dict) else None
    )
    tags_raw = raw.get("tags", [])
    tags = (
        [t["name"] for t in tags_raw if isinstance(t, dict)]
        if isinstance(tags_raw, list)
        else []
    )

    return TaskDetail(
        id=str(raw["id"]),
        custom_id=raw.get("custom_id"),  # type: ignore[arg-type]
        name=str(raw.get("name", "")),
        status=status,
        assignees=assignees,
        points=raw.get("points"),  # type: ignore[arg-type]
        url=f"https://app.clickup.com/t/{raw['id']}",
        description=raw.get("description"),  # type: ignore[arg-type]
        priority=priority,
        tags=tags,
        parent=raw["parent"]["id"]  # type: ignore[index]
        if isinstance(raw.get("parent"), dict)
        else raw.get("parent"),  # type: ignore[arg-type]
        parent_custom_id=raw["parent"].get("custom_id")  # type: ignore[attr-defined]
        if isinstance(raw.get("parent"), dict)
        else None,
        subtasks=subtasks,
        team=team,
        date_created=raw.get("date_created"),  # type: ignore[arg-type]
        date_updated=raw.get("date_updated"),  # type: ignore[arg-type]
        date_done=raw.get("date_done"),  # type: ignore[arg-type]
    )


def map_comment(raw: dict[str, object]) -> TaskComment:
    parts = raw.get("comment", [])
    text = ""
    if isinstance(parts, list):
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    user_data = raw.get("user")
    username = (
        user_data.get("username", "unknown")  # type: ignore[union-attr]
        if isinstance(user_data, dict)
        else "unknown"
    )
    return TaskComment(
        id=str(raw.get("id", "")),
        comment_text=text,
        user=username,
        date=str(raw.get("date", "")),
    )
