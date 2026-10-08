import json
from unittest.mock import patch

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from tests.conftest import SAMPLE_COMMENTS_RAW
from tests.helpers import get_tool_text


def _mock_response(data: dict[str, object], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data, headers={"x-ratelimit-remaining": "999"})


class TestGetComments:
    @pytest.mark.asyncio
    async def test_get_comments(self) -> None:
        from mcp.server.mcpserver import MCPServer

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.comments import register_comment_tools

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(SAMPLE_COMMENTS_RAW)

        server = MCPServer("test")
        register_comment_tools(server)

        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("get_task_comments", {"task_id": "abc123"})
            data = json.loads(get_tool_text(result))

        assert len(data) == 1
        assert "PR" in data[0]["comment_text"]


class TestAddComment:
    @pytest.mark.asyncio
    async def test_add_comment(self) -> None:
        from mcp.server.mcpserver import MCPServer

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.comments import register_comment_tools

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            return _mock_response({"id": "new-comment-123"})

        server = MCPServer("test")
        register_comment_tools(server)

        with patch.object(clickup_client, "post", side_effect=mock_post):
            result = await server.call_tool(
                "add_task_comment",
                {
                    "task_id": "abc123",
                    "comment_text": "Initial design posted",
                },
            )
            data = json.loads(get_tool_text(result))

        assert data["status"] == "ok"


def _team_raw() -> dict[str, object]:
    from clickup_mcp_server.config import settings

    return {
        "teams": [
            {
                "id": settings.workspace_id,
                "members": [
                    {"user": {"id": 23456789, "username": "Jordan Example"}},
                    {
                        "user": {
                            "id": 12345678,
                            "username": "testuser",
                            "email": "testuser@example.com",
                        }
                    },
                ],
            }
        ]
    }


def _assert_tool_error(result: object, needle: str) -> None:
    assert isinstance(result, ToolError)
    assert not isinstance(result, UnexpectedToolError)
    assert needle in str(result)


class TestAddCommentMarkup:
    @pytest.fixture(autouse=True)
    def _reset_member_cache(self) -> None:
        from clickup_mcp_server.tools import workspace

        workspace._members_task = None

    async def _call(
        self, text: str, mentions: list[str] | None = None
    ) -> tuple[list[dict[str, object]], object]:
        from mcp.server.mcpserver import MCPServer

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.comments import register_comment_tools

        posted: list[dict[str, object]] = []

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            assert path == "/team"
            return _mock_response(_team_raw())

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            posted.append(json_data or {})
            return _mock_response({"id": "c1"})

        args: dict[str, object] = {"task_id": "abc123", "comment_text": text}
        if mentions is not None:
            args["mentions"] = mentions
        server = MCPServer("test")
        register_comment_tools(server)
        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            patch.object(clickup_client, "post", side_effect=mock_post),
        ):
            try:
                result: object = await server.call_tool("add_task_comment", args)
            except ToolError as exc:
                result = exc
        return posted, result

    @pytest.mark.asyncio
    async def test_plain_text_body_unchanged(self) -> None:
        posted, _ = await self._call("[adr-draft] Initial design posted")
        assert posted == [{"comment_text": "[adr-draft] Initial design posted"}]

    @pytest.mark.asyncio
    async def test_mention_and_bold_post_rich_blocks(self) -> None:
        posted, _ = await self._call(
            "@[Jordan Example] see **this**", mentions=["Jordan Example"]
        )
        assert posted == [
            {
                "comment": [
                    {"type": "tag", "user": {"id": 23456789}},
                    {"text": " see "},
                    {"text": "this", "attributes": {"bold": True}},
                ]
            }
        ]

    @pytest.mark.asyncio
    async def test_bold_only_skips_member_lookup(self) -> None:
        from clickup_mcp_server.tools import workspace

        with patch.object(
            workspace, "_fetch_workspace_members", side_effect=AssertionError
        ):
            posted, _ = await self._call("**bold** only")
        assert posted == [
            {
                "comment": [
                    {"text": "bold", "attributes": {"bold": True}},
                    {"text": " only"},
                ]
            }
        ]

    @pytest.mark.asyncio
    async def test_unknown_mention_posts_nothing(self) -> None:
        posted, result = await self._call("@[Nobody Here] hi", mentions=["Nobody Here"])
        assert posted == []
        _assert_tool_error(result, "Nobody Here")

    @pytest.mark.asyncio
    async def test_relayed_mention_not_in_mentions_posts_nothing(self) -> None:
        from clickup_mcp_server.tools import workspace

        with patch.object(
            workspace, "_fetch_workspace_members", side_effect=AssertionError
        ):
            posted, result = await self._call("PR says: ping @[Jordan Example]")
        assert posted == []
        _assert_tool_error(result, "wrap it in backticks or remove it")

    @pytest.mark.asyncio
    async def test_unlisted_mention_with_other_mentions_skips_lookup(self) -> None:
        from clickup_mcp_server.tools import workspace

        with patch.object(
            workspace, "_fetch_workspace_members", side_effect=AssertionError
        ):
            posted, result = await self._call(
                "ping @[Jordan Example]", mentions=["someone else"]
            )
        assert posted == []
        _assert_tool_error(result, "not in mentions")

    @pytest.mark.asyncio
    async def test_listed_mention_without_brackets_posts_nothing(self) -> None:
        from clickup_mcp_server.tools import workspace

        with patch.object(
            workspace, "_fetch_workspace_members", side_effect=AssertionError
        ):
            posted, result = await self._call(
                "@Jordan Example please review", mentions=["Jordan Example"]
            )
        assert posted == []
        _assert_tool_error(result, "nobody would be notified")

    @pytest.mark.asyncio
    async def test_members_are_fetched_for_every_mentioning_comment(self) -> None:
        from clickup_mcp_server.tools import workspace

        calls = 0
        real_fetch = workspace._fetch_workspace_members

        async def counting_fetch() -> list[object]:
            nonlocal calls
            calls += 1
            return await real_fetch()

        with patch.object(
            workspace, "_fetch_workspace_members", side_effect=counting_fetch
        ):
            for _ in range(2):
                posted, _ = await self._call(
                    "@[Jordan Example] hi", mentions=["Jordan Example"]
                )
                assert posted
        assert calls == 2
