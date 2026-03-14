import asyncio
import json
from unittest.mock import patch

import httpx
import pytest

from clickup_mcp_server.models import SprintInfo
from tests.conftest import SAMPLE_FOLDER_RAW
from tests.helpers import get_tool_text


def _mock_response(data: dict[str, object], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data, headers={"x-ratelimit-remaining": "999"})


class TestSprintDetection:
    @pytest.mark.asyncio
    async def test_current_sprint_by_date(self) -> None:
        from clickup_mcp_server.tools import sprint as sprint_mod

        sprint_mod._sprint_task = None

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(SAMPLE_FOLDER_RAW)

        with patch.object(sprint_mod.clickup_client, "get", side_effect=mock_get):
            with patch("clickup_mcp_server.tools.sprint.time") as mock_time:
                mock_time.time.return_value = 1709500000.0
                result = await sprint_mod.get_current_sprint_cached()

        assert result.list_id == "901816121536"
        assert result.name == "Sprint 31"
        sprint_mod._sprint_task = None

    @pytest.mark.asyncio
    async def test_cache_dedup(self) -> None:
        from clickup_mcp_server.tools import sprint as sprint_mod

        sprint_mod._sprint_task = None

        call_count = 0

        async def counting_fetch() -> SprintInfo:
            nonlocal call_count
            call_count += 1
            return SprintInfo(
                list_id="test",
                name="Test Sprint",
                start_date="2024-01-01",
                end_date="2024-01-14",
            )

        with patch.object(sprint_mod, "_fetch_sprint", counting_fetch):
            results = await asyncio.gather(
                sprint_mod.get_current_sprint_cached(),
                sprint_mod.get_current_sprint_cached(),
                sprint_mod.get_current_sprint_cached(),
            )

        assert all(r.list_id == "test" for r in results)
        assert call_count == 1
        sprint_mod._sprint_task = None


class TestSprintTasks:
    @pytest.mark.asyncio
    async def test_filter_by_status(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.tools import sprint as sprint_mod
        from clickup_mcp_server.tools.sprint import register_sprint_tools

        sprint_mod._sprint_task = None

        async def _ready_sprint() -> SprintInfo:
            return SprintInfo(
                list_id="list1",
                name="Sprint 31",
                start_date="2024-01-01",
                end_date="2024-01-14",
            )

        sprint_mod._sprint_task = asyncio.ensure_future(_ready_sprint())

        tasks_response = {
            "tasks": [
                {
                    "id": "t1",
                    "custom_id": "DEV-1",
                    "name": "Task 1",
                    "status": {"status": "done"},
                    "assignees": [],
                    "points": 1.0,
                },
                {
                    "id": "t2",
                    "custom_id": "DEV-2",
                    "name": "Task 2",
                    "status": {"status": "in progress"},
                    "assignees": [],
                    "points": 2.0,
                },
            ]
        }

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(tasks_response)

        server = FastMCP("test")
        register_sprint_tools(server)

        with patch.object(sprint_mod.clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("get_sprint_tasks", {"status": "done"})
            data = json.loads(get_tool_text(result))
            assert data["total"] == 1
            assert data["tasks"][0]["custom_id"] == "DEV-1"

        sprint_mod._sprint_task = None
