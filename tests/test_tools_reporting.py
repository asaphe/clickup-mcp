from unittest.mock import AsyncMock, patch

import httpx
import pytest

from clickup_mcp_server.tools.reporting import _fetch_task_pr_links


def _mock_response(data: dict[str, object], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data, headers={"x-ratelimit-remaining": "999"})


class TestFetchTaskPrLinks:
    @pytest.mark.asyncio
    async def test_unreadable_comments_return_none_not_empty(self) -> None:
        from clickup_mcp_server.client import clickup_client

        async def boom(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            raise httpx.ConnectError("boom")

        # [] would be reported as "In review but no PR link found".
        with patch.object(clickup_client, "get", side_effect=boom):
            assert await _fetch_task_pr_links("abc123") is None

    @pytest.mark.asyncio
    async def test_readable_comments_without_links_return_empty_list(self) -> None:
        from clickup_mcp_server.client import clickup_client

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(
                {"comments": [{"id": "1", "comment": [{"text": "no links here"}]}]}
            )

        with patch.object(clickup_client, "get", side_effect=mock_get):
            assert await _fetch_task_pr_links("abc123") == []

    @pytest.mark.asyncio
    async def test_links_are_extracted_from_comments(self) -> None:
        from clickup_mcp_server.client import clickup_client

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(
                {
                    "comments": [
                        {
                            "id": "1",
                            "comment": [
                                {"text": "see https://github.com/org/repo/pull/7"}
                            ],
                        }
                    ]
                }
            )

        with patch.object(clickup_client, "get", side_effect=mock_get):
            links = await _fetch_task_pr_links("abc123")

        assert links == ["https://github.com/org/repo/pull/7"]


class TestSprintReportTeamFilter:
    @pytest.mark.asyncio
    async def test_unknown_team_without_labels_names_the_variable_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mcp.server.mcpserver import MCPServer

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.models import SprintInfo
        from clickup_mcp_server.tools.reporting import register_reporting_tools
        from tests.helpers import get_tool_text

        monkeypatch.setattr("clickup_mcp_server.tools.reporting.TEAM_LABELS", {})
        monkeypatch.setattr(
            "clickup_mcp_server.tools.reporting.get_current_sprint_cached",
            AsyncMock(
                return_value=SprintInfo(
                    list_id="9", name="S", start_date="0", end_date="0"
                )
            ),
        )
        server = MCPServer("test")
        register_reporting_tools(server)

        with patch.object(
            clickup_client,
            "get",
            new_callable=AsyncMock,
            return_value=_mock_response({"tasks": [], "last_page": True}),
        ):
            result = await server.call_tool("get_sprint_report", {"team": "backend"})

        text = get_tool_text(result)
        assert "Unknown team 'backend'." in text
        assert "unset, empty, or not a JSON object of team names" in text
