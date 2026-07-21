from mcp.server.fastmcp import FastMCP

from clickup_mcp_server.tools.comments import register_comment_tools
from clickup_mcp_server.tools.docs import register_doc_tools
from clickup_mcp_server.tools.reporting import register_reporting_tools
from clickup_mcp_server.tools.sprint import register_sprint_tools
from clickup_mcp_server.tools.tasks import register_task_tools
from clickup_mcp_server.tools.workspace import register_workspace_tools

INSTRUCTIONS = """\
ClickUp MCP Server for task management, sprint tracking, and reporting.

Key patterns:
- Task IDs: Custom IDs (e.g., DEV-1234) or UUIDs — both accepted everywhere
- "me" as assignee: resolved automatically from the API token
- Sprint: auto-detected by date, cached per session

Common workflows:
- Quick task creation: create_sprint_task (auto sprint + user + defaults)
- Sprint review: get_sprint_tasks (filter by assignee/status)
- My work: get_my_tasks (cross-list, filterable)
- Post-merge: update_task(status="done") + update_task(append_description="...")
- Delete junk: delete_task (permanently remove a task)
- Compliance: ensure_task_fields (check/fix assignee, team, points)
- Bulk fix: bulk_update_tasks (set status/team/assignee across multiple tasks)
- Team labels: check_team_labels (compare config with live options)
- Sprint report: get_sprint_report (tasks by assignee, status counts, at-risk flags)
- Shareable report/RFC: create_doc (native ClickUp Doc with real markdown tables,
  not a task description — sharing/visibility is a separate manual step)
- Correct a published Doc: update_doc_page (edits the existing page in place —
  the v3 Docs API has no delete endpoint, so re-running create_doc orphans
  the old Doc instead of fixing it)
- Read a published Doc: get_doc_page (single page) / get_doc_pages (whole Doc)
  — content only, Doc comments still require the browser
"""

mcp_server = FastMCP("clickup", instructions=INSTRUCTIONS)

register_sprint_tools(mcp_server)
register_task_tools(mcp_server)
register_comment_tools(mcp_server)
register_reporting_tools(mcp_server)
register_workspace_tools(mcp_server)
register_doc_tools(mcp_server)
