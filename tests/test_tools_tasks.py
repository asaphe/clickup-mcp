import json
from unittest.mock import patch

import httpx
import pytest

from tests.conftest import SAMPLE_TASK_RAW
from tests.helpers import get_tool_text


def _mock_response(data: dict[str, object], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data, headers={"x-ratelimit-remaining": "999"})


class TestGetTask:
    @pytest.mark.asyncio
    async def test_get_task_by_custom_id(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("get_task", {"task_id": "DEV-9999"})
            data = json.loads(get_tool_text(result))

        assert data["custom_id"] == "DEV-9999"
        assert data["status"] == "in progress"

    @pytest.mark.asyncio
    async def test_get_task_by_uuid(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("get_task", {"task_id": "abc123"})
            data = json.loads(get_tool_text(result))

        assert data["id"] == "abc123"


class TestDateConversion:
    def test_iso_date(self) -> None:
        from clickup_mcp_server.tools.tasks import _to_millis

        result = _to_millis("2024-03-01T00:00:00Z")
        assert result.isdigit()
        assert len(result) == 13

    def test_already_millis(self) -> None:
        from clickup_mcp_server.tools.tasks import _to_millis

        result = _to_millis("1709251200000")
        assert result == "1709251200000"

    def test_date_only(self) -> None:
        from clickup_mcp_server.tools.tasks import _to_millis

        result = _to_millis("2024-03-01")
        assert result.isdigit()
