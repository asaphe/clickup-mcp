# ClickUp MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server that connects Claude Code and Claude Desktop to ClickUp. Provides task management, sprint tracking, reporting, and workspace navigation through 21 tools.

## Features

- **Task management** — create, update, search, and bulk-edit tasks
- **Sprint tracking** — auto-detect current sprint, list sprint tasks, filter by assignee/status
- **Reporting** — sprint reports with at-risk detection, PR link extraction, status summaries
- **Workspace navigation** — browse spaces, folders, lists; resolve custom task IDs
- **Comments** — read and write task comments

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (`brew install uv`)
- A ClickUp personal API token

## Quick Start

```bash
git clone https://github.com/asaphe/clickup-mcp.git
cd clickup-mcp
python3 setup_mcp.py
```

The setup script walks you through:
1. Token retrieval (1Password integration or manual paste)
2. Workspace configuration (workspace ID required, sprint/team IDs optional)
3. Client registration (Claude Code, Claude Desktop, or both)
4. Automatic restart of Claude Desktop if running

## Configuration

All configuration is via environment variables. Only `CLICKUP_API_TOKEN` and `WORKSPACE_ID` are required — the rest enable optional features.

### Required

| Variable | Description |
|----------|-------------|
| `CLICKUP_API_TOKEN` | Personal API token from https://app.clickup.com/settings/apps |
| `WORKSPACE_ID` | Your ClickUp workspace (team) ID |

### Optional — Sprint Detection

| Variable | Description |
|----------|-------------|
| `DEVELOPMENT_SPACE_ID` | Space ID containing your sprints. Required for sprint tools. |
| `SPRINTS_FOLDER_ID` | Folder ID within the space that holds sprint lists. Required for sprint tools. |

### Optional — Team Labels

| Variable | Description |
|----------|-------------|
| `COMPONENT_TEAM_FIELD_ID` | Custom field ID for Component/Team labels |
| `CLICKUP_TEAM_LABELS` | JSON mapping of team names to label IDs (see below) |

Example `CLICKUP_TEAM_LABELS`:
```json
{"backend": "uuid-1", "frontend": "uuid-2", "devops": "uuid-3"}
```

### Optional — Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `API_BASE_URL` | `https://api.clickup.com/api/v2` | ClickUp API base URL |
| `REQUEST_TIMEOUT` | `15.0` | HTTP request timeout in seconds |
| `MAX_RETRIES` | `3` | Max retry attempts for failed/rate-limited requests |

### Finding Your IDs

- **Workspace ID**: Settings → Workspaces → look at the URL or API response
- **Space ID**: Click on a Space → the ID is in the URL (`/s/{space_id}/...`)
- **Folder ID**: Click on a Folder → inspect the URL or use the `get_workspace_hierarchy` tool
- **Custom Field ID**: Use the ClickUp API: `GET /list/{list_id}/field`
- **Team Label IDs**: Use the ClickUp API: `GET /list/{list_id}/field` → find the labels dropdown field → extract option IDs

## Tools

21 tools across 5 categories:

### Sprint Management
| Tool | Description |
|------|-------------|
| `get_current_sprint` | Auto-detect the active sprint by date |
| `refresh_sprint_cache` | Force-refresh the cached sprint |
| `get_sprint_tasks` | List tasks in the current sprint (filter by assignee/status) |

### Task Management
| Tool | Description |
|------|-------------|
| `get_task` | Get task details by ID (DEV-1234 or UUID) |
| `create_task` | Create a task in any list |
| `create_sprint_task` | Create a task in the current sprint (auto-assign, team, points) |
| `update_task` | Update status, assignee, description, points, dates |
| `search_tasks` | Search tasks by name |
| `get_my_tasks` | Get tasks assigned to the current user |
| `get_list_tasks` | Get all tasks in a specific list |
| `move_task_to_list` | Move a task to a different list |
| `bulk_update_tasks` | Batch-update status/team/assignee across multiple tasks |
| `ensure_task_fields` | Check and fix missing fields (assignee, team, points) |

### Comments
| Tool | Description |
|------|-------------|
| `add_task_comment` | Post a comment on a task |
| `get_task_comments` | Retrieve comments from a task |

### Reporting
| Tool | Description |
|------|-------------|
| `get_sprint_report` | Sprint report by assignee with status counts and at-risk flags |

### Workspace
| Tool | Description |
|------|-------------|
| `get_current_user` | Show the authenticated user |
| `get_workspace_hierarchy` | Browse spaces, folders, and lists |
| `task_url` | Get the ClickUp URL for a task |
| `add_tag_to_task` | Add a tag to a task |
| `list_teams` | List available team labels |

## Usage Examples

In Claude Code or Claude Desktop, just ask naturally:

- "show my tasks"
- "sprint report for backend"
- "create a task for fixing the login bug"
- "mark DEV-1234 as done"
- "what's the current sprint?"
- "show unassigned tasks in the sprint"

## Key Patterns

- **Task IDs**: Both custom IDs (`DEV-1234`, `PROJ-456`) and UUIDs are accepted everywhere
- **"me" as assignee**: Resolved automatically from the API token
- **Sprint auto-detection**: Current sprint is detected by date and cached per session
- **Rate limiting**: Automatic retry with exponential backoff on 429 responses
- **Concurrent comment fetching**: Sprint reports fetch PR links from comments with bounded concurrency

## Coexistence with Built-in ClickUp MCP

This server works alongside the official ClickUp MCP connector. The built-in handles features not covered here (time tracking, Docs, chat). You can register both, though having both may cause tool-selection ambiguity for overlapping operations.

## Development

```bash
uv sync --dev
uv run pytest
uv run mypy clickup_mcp_server
uv run ruff check .
```

## Architecture

```
clickup_mcp_server/
  server.py       — FastMCP server entry point and instructions
  client.py       — Async HTTP client with retry and rate-limit handling
  config.py       — Settings (env var based, no hardcoded IDs)
  models.py       — Pydantic models for API responses
  tools/
    sprint.py     — Sprint detection and caching
    tasks.py      — Task CRUD, search, bulk operations
    comments.py   — Comment read/write
    reporting.py  — Sprint reports with at-risk detection
    workspace.py  — User info, hierarchy, tags
```

## License

MIT
