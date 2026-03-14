import json
from unittest.mock import patch

import httpx
import pytest

from tests.conftest import SAMPLE_COMMENTS_RAW
from tests.helpers import get_tool_text


def _mock_response(data: dict[str, object], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data, headers={"x-ratelimit-remaining": "999"})


class TestGetComments:
    @pytest.mark.asyncio
    async def test_get_comments(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.comments import register_comment_tools

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(SAMPLE_COMMENTS_RAW)

        server = FastMCP("test")
        register_comment_tools(server)

        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("get_task_comments", {"task_id": "abc123"})
            data = json.loads(get_tool_text(result))

        assert len(data) == 1
        assert "PR" in data[0]["comment_text"]


class TestAddComment:
    @pytest.mark.asyncio
    async def test_add_comment(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.comments import register_comment_tools

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            return _mock_response({"id": "new-comment-123"})

        server = FastMCP("test")
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
