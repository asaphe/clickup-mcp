from unittest.mock import AsyncMock, patch

import httpx
import pytest

from clickup_mcp_server.tools.reporting import _fetch_task_pr_links
from tests.conftest import (
    BACKEND_OPTION_ID,
    DATA_PLATFORM_OPTION_ID,
    FRONTEND_OPTION_ID,
    RESEARCH_OPTION_ID,
)


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
    async def test_unknown_team_lists_the_live_names_and_fetches_no_tasks(
        self,
    ) -> None:
        from mcp.server.mcpserver import MCPServer

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.reporting import register_reporting_tools
        from tests.helpers import get_tool_text

        server = MCPServer("test")
        register_reporting_tools(server)

        with patch.object(clickup_client, "get", new_callable=AsyncMock) as mock_get:
            result = await server.call_tool("get_sprint_report", {"team": "nope"})

        text = get_tool_text(result)
        assert "Unknown team 'nope'." in text
        assert "backend" in text
        assert "frontend-web-squad" in text
        mock_get.assert_not_awaited()

    @pytest.mark.parametrize(
        ("team", "wanted"),
        [
            ("Backend", BACKEND_OPTION_ID),
            ("frontend web squad", FRONTEND_OPTION_ID),
            ("Straße", RESEARCH_OPTION_ID),
        ],
    )
    @pytest.mark.asyncio
    async def test_team_filter_matches_by_option_id(
        self, monkeypatch: pytest.MonkeyPatch, team: str, wanted: str
    ) -> None:
        from mcp.server.mcpserver import MCPServer

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.models import SprintInfo
        from clickup_mcp_server.tools.reporting import register_reporting_tools
        from tests.conftest import SAMPLE_TASK_RAW
        from tests.helpers import get_tool_text

        monkeypatch.setattr(
            "clickup_mcp_server.team_labels.TEAM_LABELS",
            {"strasse": RESEARCH_OPTION_ID},
        )
        monkeypatch.setattr(
            "clickup_mcp_server.tools.reporting.get_current_sprint_cached",
            AsyncMock(
                return_value=SprintInfo(
                    list_id="9", name="S", start_date="0", end_date="0"
                )
            ),
        )
        labelled = {
            **SAMPLE_TASK_RAW,
            "id": "t1",
            "name": "labelled-task",
            "custom_fields": [{"id": "test-field-id", "value": [wanted]}],
        }
        other_option = {
            **SAMPLE_TASK_RAW,
            "id": "t3",
            "name": "other-option-task",
            "custom_fields": [
                {"id": "test-field-id", "value": [DATA_PLATFORM_OPTION_ID]}
            ],
        }
        unlabelled = {
            **SAMPLE_TASK_RAW,
            "id": "t2",
            "name": "other-task",
            "custom_fields": [],
        }
        server = MCPServer("test")
        register_reporting_tools(server)

        with patch.object(
            clickup_client,
            "get",
            new_callable=AsyncMock,
            return_value=_mock_response(
                {"tasks": [labelled, other_option, unlabelled], "last_page": True}
            ),
        ):
            result = await server.call_tool(
                "get_sprint_report", {"team": team, "include_pr_links": False}
            )

        text = get_tool_text(result)
        assert "labelled-task" in text
        assert "other-option-task" not in text
        assert "other-task" not in text
