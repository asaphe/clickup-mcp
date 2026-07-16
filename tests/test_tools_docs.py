import json
from unittest.mock import patch

import httpx
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from clickup_mcp_server.client import clickup_client
from clickup_mcp_server.config import settings
from clickup_mcp_server.tools.docs import register_doc_tools
from tests.helpers import get_tool_text


def _mock_response(data: dict[str, object], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data, headers={"x-ratelimit-remaining": "999"})


def _make_server() -> FastMCP:
    server = FastMCP("test")
    register_doc_tools(server)
    return server


class TestCreateDoc:
    @pytest.mark.asyncio
    async def test_creates_doc_and_page_with_defaults(self) -> None:
        captured: list[tuple[str, dict[str, object] | None]] = []

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            captured.append((path, json_data))
            if path.endswith("/docs"):
                return _mock_response({"id": "doc123"})
            return _mock_response({"id": "page456"})

        server = _make_server()
        with patch.object(clickup_client, "post", side_effect=mock_post):
            result = await server.call_tool(
                "create_doc", {"name": "RFC Title", "content": "# Body"}
            )
            data = json.loads(get_tool_text(result))

        doc_path, doc_body = captured[0]
        page_path, page_body = captured[1]

        assert doc_path == (
            f"{settings.api_v3_base_url}/workspaces/{settings.workspace_id}/docs"
        )
        assert doc_body == {
            "name": "RFC Title",
            "create_page": False,
            "parent": {"id": settings.development_space_id, "type": 4},
            "visibility": "PRIVATE",
        }

        assert page_path == (
            f"{settings.api_v3_base_url}/workspaces/{settings.workspace_id}"
            "/docs/doc123/pages"
        )
        assert page_body == {
            "name": "RFC Title",
            "content": "# Body",
            "content_format": "text/md",
        }

        assert data == {
            "doc_id": "doc123",
            "page_id": "page456",
            "name": "RFC Title",
            "url": f"https://app.clickup.com/{settings.workspace_id}/v/dc/doc123/page456",
        }

    @pytest.mark.asyncio
    async def test_custom_parent_type_and_id(self) -> None:
        captured: dict[str, object] = {}

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            if path.endswith("/docs"):
                captured["doc_body"] = json_data
                return _mock_response({"id": "doc1"})
            return _mock_response({"id": "page1"})

        server = _make_server()
        with patch.object(clickup_client, "post", side_effect=mock_post):
            await server.call_tool(
                "create_doc",
                {
                    "name": "Doc",
                    "content": "body",
                    "parent_id": "901816121536",
                    "parent_type": "list",
                },
            )

        assert captured["doc_body"] == {
            "name": "Doc",
            "create_page": False,
            "parent": {"id": "901816121536", "type": 6},
            "visibility": "PRIVATE",
        }

    @pytest.mark.asyncio
    async def test_rejects_invalid_parent_type(self) -> None:
        post_called = False

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal post_called
            post_called = True
            return _mock_response({"id": "doc1"})

        server = _make_server()
        with (
            patch.object(clickup_client, "post", side_effect=mock_post),
            pytest.raises(ToolError, match="Invalid parent_type"),
        ):
            await server.call_tool(
                "create_doc",
                {"name": "Doc", "content": "body", "parent_type": "board"},
            )

        assert post_called is False

    @pytest.mark.asyncio
    async def test_rejects_path_altering_parent_id(self) -> None:
        post_called = False

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal post_called
            post_called = True
            return _mock_response({"id": "doc1"})

        server = _make_server()
        with (
            patch.object(clickup_client, "post", side_effect=mock_post),
            pytest.raises(ToolError, match="Invalid parent_id"),
        ):
            await server.call_tool(
                "create_doc",
                {
                    "name": "Doc",
                    "content": "body",
                    "parent_id": "../../space/EVIL/docs",
                },
            )

        assert post_called is False

    @pytest.mark.asyncio
    async def test_rejects_invalid_content_format(self) -> None:
        post_called = False

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal post_called
            post_called = True
            return _mock_response({"id": "doc1"})

        server = _make_server()
        with (
            patch.object(clickup_client, "post", side_effect=mock_post),
            pytest.raises(ToolError, match="Invalid content_format"),
        ):
            await server.call_tool(
                "create_doc",
                {"name": "Doc", "content": "body", "content_format": "text/html"},
            )

        assert post_called is False

    @pytest.mark.asyncio
    async def test_rejects_invalid_visibility(self) -> None:
        post_called = False

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal post_called
            post_called = True
            return _mock_response({"id": "doc1"})

        server = _make_server()
        with (
            patch.object(clickup_client, "post", side_effect=mock_post),
            pytest.raises(ToolError, match="Invalid visibility"),
        ):
            await server.call_tool(
                "create_doc",
                {"name": "Doc", "content": "body", "visibility": "SECRET"},
            )

        assert post_called is False
