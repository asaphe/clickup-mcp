"""Integration tests against real ClickUp API.

Skipped unless CLICKUP_API_TOKEN is set in the environment.
Run manually: CLICKUP_API_TOKEN=<token> WORKSPACE_ID=<id> uv run pytest tests/test_integration.py -v
"""

import os

import pytest

from tests.helpers import get_tool_text

pytestmark = pytest.mark.skipif(
    not os.environ.get("CLICKUP_API_TOKEN")
    or os.environ.get("CLICKUP_API_TOKEN") == "test-token-12345",
    reason="No real CLICKUP_API_TOKEN set",
)


@pytest.fixture(autouse=True)
async def _reset_client():
    """Close the shared httpx client between tests to avoid stale event loops."""
    from clickup_mcp_server.client import clickup_client

    yield
    await clickup_client.close()


class TestIntegration:
    @pytest.mark.asyncio
    async def test_get_current_user(self) -> None:
        import clickup_mcp_server.tools.workspace as ws_mod
        from clickup_mcp_server.tools.workspace import (
            get_current_user_cached,
        )

        ws_mod._user_task = None
        user = await get_current_user_cached()
        assert user.id > 0
        assert len(user.username) > 0
        ws_mod._user_task = None

    @pytest.mark.asyncio
    async def test_get_current_sprint(self) -> None:
        import clickup_mcp_server.tools.sprint as sprint_mod
        from clickup_mcp_server.tools.sprint import get_current_sprint_cached

        sprint_mod._sprint_task = None
        sprint = await get_current_sprint_cached()
        assert len(sprint.list_id) > 0
        assert "Sprint" in sprint.name or "sprint" in sprint.name.lower()
        sprint_mod._sprint_task = None

    @pytest.mark.asyncio
    async def test_search_tasks(self) -> None:
        import json

        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.tools.tasks import register_task_tools

        server = FastMCP("test")
        register_task_tools(server)
        result = await server.call_tool(
            "search_tasks", {"include_closed": True, "page": 0}
        )
        data = json.loads(get_tool_text(result))
        assert "tasks" in data
        assert isinstance(data["tasks"], list)
