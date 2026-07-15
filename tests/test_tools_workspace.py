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


class TestAddTagToTask:
    @pytest.mark.asyncio
    async def test_tag_name_is_url_encoded(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.workspace import register_workspace_tools

        captured_path: str | None = None

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal captured_path
            captured_path = path
            return _mock_response({})

        server = FastMCP("test")
        register_workspace_tools(server)

        with patch.object(clickup_client, "post", side_effect=mock_post):
            await server.call_tool(
                "add_tag_to_task",
                {"task_id": "abc123uuid", "tag_name": "../../../task/other/tag/x"},
            )

        assert (
            captured_path
            == "/task/abc123uuid/tag/..%2F..%2F..%2Ftask%2Fother%2Ftag%2Fx"
        )
        assert "/tag/../" not in captured_path


class TestCheckTeamLabels:
    @pytest.mark.asyncio
    async def test_reports_not_configured_without_fetching_live_options(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.workspace import register_workspace_tools

        monkeypatch.setattr("clickup_mcp_server.tools.workspace.TEAM_LABELS", {})
        get_called = False

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            nonlocal get_called
            get_called = True
            return _mock_response({})

        server = FastMCP("test")
        register_workspace_tools(server)

        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("check_team_labels", {})
            data = json.loads(get_tool_text(result))

        assert get_called is False
        assert data["configured"] is False
        assert data["in_sync"] is False
        assert "not configured" in data["message"]

    @pytest.mark.asyncio
    async def test_reports_in_sync_when_all_configured_ids_are_live(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.config import settings
        from clickup_mcp_server.tools.workspace import register_workspace_tools

        monkeypatch.setattr(
            "clickup_mcp_server.tools.workspace.TEAM_LABELS",
            {"example-team": "label-1"},
        )
        monkeypatch.setattr(settings, "component_team_field_id", "field-1")
        live_field = {
            "fields": [
                {
                    "id": "field-1",
                    "type_config": {
                        "options": [{"id": "label-1", "name": "Example Team"}]
                    },
                }
            ]
        }

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(live_field)

        server = FastMCP("test")
        register_workspace_tools(server)

        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("check_team_labels", {})
            data = json.loads(get_tool_text(result))

        assert data["configured"] is True
        assert data["in_sync"] is True
        assert data["stale"] == {}
        assert data["valid"] == ["example-team"]

    @pytest.mark.asyncio
    async def test_reports_stale_and_unmapped_live_options(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.config import settings
        from clickup_mcp_server.tools.workspace import register_workspace_tools

        monkeypatch.setattr(
            "clickup_mcp_server.tools.workspace.TEAM_LABELS",
            {"example-team": "stale-label"},
        )
        monkeypatch.setattr(settings, "component_team_field_id", "field-1")
        live_field = {
            "fields": [
                {
                    "id": "field-1",
                    "type_config": {
                        "options": [{"id": "live-label", "name": "Example Team"}]
                    },
                }
            ]
        }

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(live_field)

        server = FastMCP("test")
        register_workspace_tools(server)

        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("check_team_labels", {})
            data = json.loads(get_tool_text(result))

        assert data["in_sync"] is False
        assert data["stale"] == {"example-team": "stale-label"}
        assert data["unmapped_live_options"] == {"live-label": "Example Team"}
