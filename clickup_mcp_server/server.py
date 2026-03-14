from mcp.server.fastmcp import FastMCP

from clickup_mcp_server.tools.comments import register_comment_tools
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
- Compliance: ensure_task_fields (check/fix assignee, team, points)
- Bulk fix: bulk_update_tasks (set status/team/assignee across multiple tasks)
- Sprint report: get_sprint_report (tasks by assignee, status counts, at-risk flags)
"""

mcp_server = FastMCP("clickup", instructions=INSTRUCTIONS)

register_sprint_tools(mcp_server)
register_task_tools(mcp_server)
register_comment_tools(mcp_server)
register_reporting_tools(mcp_server)
register_workspace_tools(mcp_server)
