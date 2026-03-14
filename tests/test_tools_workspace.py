import json
from unittest.mock import patch

import httpx
import pytest

from tests.conftest import SAMPLE_FOLDER_RAW, SAMPLE_USER_RAW
from tests.helpers import get_tool_text


def _mock_response(data: dict[str, object], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data, headers={"x-ratelimit-remaining": "999"})


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_returns_user_info(self) -> None:
        from clickup_mcp_server.tools import workspace as ws_mod

        ws_mod._user_task = None

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(SAMPLE_USER_RAW)

        with patch.object(ws_mod.clickup_client, "get", side_effect=mock_get):
            user = await ws_mod.get_current_user_cached()

        assert user.id == 12345678
        assert user.username == "testuser"
        ws_mod._user_task = None


class TestWorkspaceHierarchy:
    @pytest.mark.asyncio
    async def test_returns_folders_and_lists(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.workspace import register_workspace_tools

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(SAMPLE_FOLDER_RAW)

        server = FastMCP("test")
        register_workspace_tools(server)

        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("get_workspace_hierarchy", {})
            data = json.loads(get_tool_text(result))

        assert len(data) == 1
        assert data[0]["name"] == "Sprints"
        assert len(data[0]["lists"]) == 2


class TestTaskUrl:
    @pytest.mark.asyncio
    async def test_resolves_custom_id(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.workspace import register_workspace_tools

        async def mock_get(
            path: str, params: dict[str, str] | list[tuple[str, str]] | None = None
        ) -> httpx.Response:
            return _mock_response({"id": "abc123uuid"})

        server = FastMCP("test")
        register_workspace_tools(server)

        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("task_url", {"task_id": "DEV-1234"})
            text = get_tool_text(result)

        assert "abc123uuid" in text
        assert text == "https://app.clickup.com/t/abc123uuid"

    @pytest.mark.asyncio
    async def test_uuid_passthrough(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.tools.workspace import register_workspace_tools

        server = FastMCP("test")
        register_workspace_tools(server)
        result = await server.call_tool("task_url", {"task_id": "abc123uuid"})
        text = get_tool_text(result)
        assert text == "https://app.clickup.com/t/abc123uuid"
