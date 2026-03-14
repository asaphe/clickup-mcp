import asyncio
import logging
import re

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from clickup_mcp_server.client import clickup_client, parse_response
from clickup_mcp_server.config import TEAM_LABELS
from clickup_mcp_server.models import (
    AtRiskItem,
    SprintReport,
    SprintReportTask,
    map_comment,
    map_task_detail,
)
from clickup_mcp_server.tools.sprint import get_current_sprint_cached

logger = logging.getLogger(__name__)

_PR_URL_RE = re.compile(r"github\.com/[^/]+/[^/]+/pull/\d+")

_DONE_STATUSES = {"done", "closed", "complete", "completed"}


def _extract_pr_links(text: str) -> list[str]:
    links: list[str] = []
    for match in _PR_URL_RE.finditer(text):
        url = match.group(0)
        if not url.startswith("http"):
            url = "https://" + url
        links.append(url)
    return links


_COMMENT_CONCURRENCY = 5


def _add_at_risk(
    at_risk_map: dict[str, AtRiskItem],
    task_id: str,
    custom_id: str | None,
    name: str,
    assignee: str | None,
    reason: str,
) -> None:
    existing = at_risk_map.get(task_id)
    if existing is not None:
        existing.reason = f"{existing.reason}; {reason}"
    else:
        at_risk_map[task_id] = AtRiskItem(
            custom_id=custom_id, name=name, assignee=assignee, reason=reason
        )


async def _fetch_task_pr_links(task_id: str) -> list[str]:
    try:
        resp = await clickup_client.get(f"/task/{task_id}/comment")
        data = parse_response(resp)
        comments_raw = data.get("comments", [])
        links: list[str] = []
        if isinstance(comments_raw, list):
            for c_raw in comments_raw:
                if isinstance(c_raw, dict):
                    c = map_comment(c_raw)
                    links.extend(_extract_pr_links(c.comment_text))
        return links
    except Exception:
        logger.debug("Failed to fetch comments for %s", task_id)
        return []


_PRIORITY_ORDER: dict[str | None, int] = {
    "urgent": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
    None: 4,
}


def _format_task_line(t: SprintReportTask) -> str:
    tid = t.custom_id or "—"
    parts = [f"**{tid}** — {t.name}"]
    if t.priority and t.priority in ("urgent", "high"):
        parts.append(f"[{t.priority}]")
    parts.append(f"| {t.status}")
    if t.subtasks_summary:
        parts.append(f"(subtasks: {t.subtasks_summary})")
    if t.pr_links:
        parts.append(f"PR: {', '.join(t.pr_links)}")
    if t.tags:
        parts.append(f"tags: {', '.join(t.tags)}")
    return " ".join(parts)


def _format_report(report: SprintReport) -> str:
    lines: list[str] = []

    lines.append(f"# {report.sprint_name}")
    lines.append(f"_{report.date_range}_\n")

    total = report.summary.get("total", 0)
    done = report.summary.get("done", 0) + report.summary.get("closed", 0)
    in_progress = report.summary.get("in progress", 0)
    in_review = report.summary.get("in review", 0)
    todo = report.summary.get("todo", 0) + report.summary.get("backlog", 0)
    named = done + in_progress + in_review + todo
    other = total - named
    status_parts = [
        f"{done}/{total} done",
        f"{in_progress} in progress",
        f"{in_review} in review",
        f"{todo} todo/backlog",
    ]
    if other > 0:
        status_parts.append(f"{other} other")
    lines.append(f"**Status:** {', '.join(status_parts)}\n")

    if report.at_risk:
        lines.append("## At Risk\n")
        for item in report.at_risk:
            tid = item.custom_id or "—"
            assignee = item.assignee or "unassigned"
            lines.append(f"- **{tid}** — {item.name} ({assignee}): {item.reason}")
        lines.append("")

    all_tasks: list[tuple[str, SprintReportTask]] = []
    for assignee, tasks in report.by_assignee.items():
        for t in tasks:
            all_tasks.append((assignee, t))
    for t in report.unassigned:
        all_tasks.append(("UNASSIGNED", t))

    by_priority: dict[int, list[tuple[str, SprintReportTask]]] = {}
    for assignee, t in all_tasks:
        rank = _PRIORITY_ORDER.get(t.priority, 4)
        by_priority.setdefault(rank, []).append((assignee, t))

    priority_labels = {0: "Urgent", 1: "High", 2: "Normal", 3: "Low", 4: "Other"}
    for rank in sorted(by_priority):
        group = by_priority[rank]
        not_done = [(a, t) for a, t in group if t.status.lower() not in _DONE_STATUSES]
        done_group = [(a, t) for a, t in group if t.status.lower() in _DONE_STATUSES]
        if not_done:
            lines.append(f"## {priority_labels.get(rank, 'Other')} Priority\n")
            for assignee, t in not_done:
                lines.append(f"- {_format_task_line(t)} — **{assignee}**")
            lines.append("")
        if done_group:
            lines.append(f"## {priority_labels.get(rank, 'Other')} Priority (Done)\n")
            for assignee, t in done_group:
                lines.append(f"- {_format_task_line(t)} — **{assignee}**")
            lines.append("")

    assignee_names = sorted(report.by_assignee.keys())
    if assignee_names or report.unassigned:
        lines.append("## By Assignee\n")
        for assignee in assignee_names:
            tasks = report.by_assignee[assignee]
            task_strs = [f"{t.custom_id or '—'} ({t.status})" for t in tasks]
            lines.append(f"- **{assignee}**: {', '.join(task_strs)}")
        if report.unassigned:
            task_strs = [
                f"{t.custom_id or '—'} ({t.status})" for t in report.unassigned
            ]
            lines.append(f"- **UNASSIGNED**: {', '.join(task_strs)}")

    return "\n".join(lines)


def register_reporting_tools(server: FastMCP) -> None:
    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        )
    )
    async def get_sprint_report(
        team: str | None = None,
        include_pr_links: bool = True,
    ) -> str:
        """Generate a structured sprint status report.

        Returns tasks grouped by assignee with status summary, at-risk flags,
        unassigned task warnings, and optionally linked GitHub PRs.

        Requires DEVELOPMENT_SPACE_ID and SPRINTS_FOLDER_ID to be configured.

        Args:
            team: Filter to a Component/Team label (e.g., "backend", "devops").
                  If omitted, includes all tasks in the sprint.
                  Requires CLICKUP_TEAM_LABELS to be configured for filtering.
            include_pr_links: Extract GitHub PR links from task descriptions and
                              comments (default: true). Adds latency for comment fetching.
        """
        sprint = await get_current_sprint_cached()

        all_tasks_raw: list[dict[str, object]] = []
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
            all_tasks_raw.extend(t for t in tasks_raw if isinstance(t, dict))
            if data.get("last_page", True):
                break
            page += 1

        tasks = [map_task_detail(t) for t in all_tasks_raw]

        if team:
            team_lower = team.lower()
            team_label_id = TEAM_LABELS.get(team_lower)
            if team_label_id:
                tasks = [t for t in tasks if t.team and t.team.lower() == team_lower]
            else:
                if TEAM_LABELS:
                    valid_teams = ", ".join(sorted(TEAM_LABELS.keys()))
                    return f"Unknown team '{team}'. Valid teams: {valid_teams}"
                return (
                    f"Unknown team '{team}'. "
                    "No team labels configured — set CLICKUP_TEAM_LABELS."
                )

        task_pr_links: dict[str, list[str]] = {}
        if include_pr_links:
            needs_comment_fetch: list[str] = []
            for task in tasks:
                desc_links = (
                    _extract_pr_links(task.description) if task.description else []
                )
                if desc_links:
                    task_pr_links[task.id] = desc_links
                else:
                    needs_comment_fetch.append(task.id)

            sem = asyncio.Semaphore(_COMMENT_CONCURRENCY)

            async def _bounded_fetch(tid: str) -> tuple[str, list[str]]:
                async with sem:
                    return tid, await _fetch_task_pr_links(tid)

            results = await asyncio.gather(
                *[_bounded_fetch(tid) for tid in needs_comment_fetch]
            )
            for tid, links in results:
                if links:
                    task_pr_links[tid] = links

        by_assignee: dict[str, list[SprintReportTask]] = {}
        unassigned_tasks: list[SprintReportTask] = []
        at_risk_map: dict[str, AtRiskItem] = {}
        status_counts: dict[str, int] = {}

        for task in tasks:
            status_key = task.status.lower()
            status_counts[status_key] = status_counts.get(status_key, 0) + 1

            pr_links = task_pr_links.get(task.id, [])

            subtasks_summary = None
            if task.subtasks:
                done_count = sum(
                    1 for s in task.subtasks if s.status.lower() in _DONE_STATUSES
                )
                subtasks_summary = f"{done_count}/{len(task.subtasks)} done"

            report_task = SprintReportTask(
                custom_id=task.custom_id,
                name=task.name,
                status=task.status,
                priority=task.priority,
                tags=task.tags,
                pr_links=pr_links,
                subtasks_summary=subtasks_summary,
            )

            if not task.assignees:
                unassigned_tasks.append(report_task)
                if task.status.lower() not in _DONE_STATUSES:
                    _add_at_risk(
                        at_risk_map,
                        task.id,
                        task.custom_id,
                        task.name,
                        None,
                        "Unassigned, not done",
                    )
            else:
                for assignee in task.assignees:
                    by_assignee.setdefault(assignee, []).append(report_task)

            assignee_name = task.assignees[0] if task.assignees else None

            if (
                task.priority in ("urgent", "high")
                and task.status.lower() not in _DONE_STATUSES
            ):
                _add_at_risk(
                    at_risk_map,
                    task.id,
                    task.custom_id,
                    task.name,
                    assignee_name,
                    f"{task.priority} priority, not done",
                )

            if include_pr_links and "review" in task.status.lower() and not pr_links:
                _add_at_risk(
                    at_risk_map,
                    task.id,
                    task.custom_id,
                    task.name,
                    assignee_name,
                    "In review but no PR link found",
                )

            if (
                task.status.lower() == "in progress"
                and task.subtasks
                and all(
                    s.status.lower() in ("backlog", "todo", "open")
                    for s in task.subtasks
                )
            ):
                _add_at_risk(
                    at_risk_map,
                    task.id,
                    task.custom_id,
                    task.name,
                    assignee_name,
                    "In progress but all subtasks in backlog/todo",
                )

        status_counts["total"] = len(tasks)

        report = SprintReport(
            sprint_name=sprint.name,
            date_range=f"{sprint.start_date} to {sprint.end_date}",
            summary=status_counts,
            by_assignee=by_assignee,
            unassigned=unassigned_tasks,
            at_risk=list(at_risk_map.values()),
        )
        return _format_report(report)
