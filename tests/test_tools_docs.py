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


class TestUpdateDocPage:
    @pytest.mark.asyncio
    async def test_replaces_content_with_defaults(self) -> None:
        captured: list[tuple[str, dict[str, object] | None]] = []

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            captured.append((path, json_data))
            return _mock_response({})

        server = _make_server()
        with patch.object(clickup_client, "put", side_effect=mock_put):
            result = await server.call_tool(
                "update_doc_page",
                {"doc_id": "doc123", "page_id": "page456", "content": "# New body"},
            )
            data = json.loads(get_tool_text(result))

        path, body = captured[0]
        assert path == (
            f"{settings.api_v3_base_url}/workspaces/{settings.workspace_id}"
            "/docs/doc123/pages/page456"
        )
        assert body == {
            "content": "# New body",
            "content_edit_mode": "replace",
            "content_format": "text/md",
        }
        assert data == {
            "doc_id": "doc123",
            "page_id": "page456",
            "url": f"https://app.clickup.com/{settings.workspace_id}/v/dc/doc123/page456",
        }

    @pytest.mark.asyncio
    async def test_replaces_content_with_new_name(self) -> None:
        captured: dict[str, object] = {}

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            captured["body"] = json_data
            return _mock_response({})

        server = _make_server()
        with patch.object(clickup_client, "put", side_effect=mock_put):
            result = await server.call_tool(
                "update_doc_page",
                {
                    "doc_id": "doc123",
                    "page_id": "page456",
                    "content": "# Corrected body",
                    "name": "Corrected Title",
                },
            )
            data = json.loads(get_tool_text(result))

        assert captured["body"] == {
            "content": "# Corrected body",
            "content_edit_mode": "replace",
            "content_format": "text/md",
            "name": "Corrected Title",
        }
        assert data["name"] == "Corrected Title"

    @pytest.mark.asyncio
    async def test_rejects_invalid_doc_id(self) -> None:
        put_called = False

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal put_called
            put_called = True
            return _mock_response({})

        server = _make_server()
        with (
            patch.object(clickup_client, "put", side_effect=mock_put),
            pytest.raises(ToolError, match="Invalid doc_id"),
        ):
            await server.call_tool(
                "update_doc_page",
                {
                    "doc_id": "../../workspace/999999999/docs",
                    "page_id": "page456",
                    "content": "body",
                },
            )

        assert put_called is False

    @pytest.mark.asyncio
    async def test_rejects_invalid_page_id(self) -> None:
        put_called = False

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal put_called
            put_called = True
            return _mock_response({})

        server = _make_server()
        with (
            patch.object(clickup_client, "put", side_effect=mock_put),
            pytest.raises(ToolError, match="Invalid page_id"),
        ):
            await server.call_tool(
                "update_doc_page",
                {
                    "doc_id": "doc123",
                    "page_id": "page456?team_id=evil",
                    "content": "body",
                },
            )

        assert put_called is False

    @pytest.mark.asyncio
    async def test_rejects_invalid_content_format(self) -> None:
        put_called = False

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal put_called
            put_called = True
            return _mock_response({})

        server = _make_server()
        with (
            patch.object(clickup_client, "put", side_effect=mock_put),
            pytest.raises(ToolError, match="Invalid content_format"),
        ):
            await server.call_tool(
                "update_doc_page",
                {
                    "doc_id": "doc123",
                    "page_id": "page456",
                    "content": "body",
                    "content_format": "text/html",
                },
            )

        assert put_called is False


class TestGetDoc:
    @pytest.mark.asyncio
    async def test_returns_doc_metadata(self) -> None:
        captured: list[tuple[str, object]] = []

        async def mock_get(
            path: str,
            params: dict[str, str] | list[tuple[str, str]] | None = None,
        ) -> httpx.Response:
            captured.append((path, params))
            return _mock_response(
                {
                    "id": "doc123",
                    "name": "RFC Title",
                    "parent": {"id": "123456789", "type": 4},
                    "public": False,
                    "date_created": 1784208435058,
                    "date_updated": 1784635013781,
                }
            )

        server = _make_server()
        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("get_doc", {"doc_id": "doc123"})
            data = json.loads(get_tool_text(result))

        path, params = captured[0]
        assert path == (
            f"{settings.api_v3_base_url}/workspaces/{settings.workspace_id}/docs/doc123"
        )
        assert params is None
        assert data == {
            "id": "doc123",
            "name": "RFC Title",
            "parent_id": "123456789",
            "parent_type": "space",
            "public": False,
            "date_created": 1784208435058,
            "date_updated": 1784635013781,
        }

    @pytest.mark.asyncio
    async def test_unknown_parent_type_code_omitted(self) -> None:
        async def mock_get(
            path: str,
            params: dict[str, str] | list[tuple[str, str]] | None = None,
        ) -> httpx.Response:
            return _mock_response(
                {
                    "id": "doc123",
                    "name": "RFC Title",
                    "parent": {"id": "123456789", "type": 999},
                    "public": False,
                    "date_created": 1784208435058,
                    "date_updated": 1784635013781,
                }
            )

        server = _make_server()
        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("get_doc", {"doc_id": "doc123"})
            data = json.loads(get_tool_text(result))

        assert "parent_type" not in data

    @pytest.mark.asyncio
    async def test_rejects_invalid_doc_id(self) -> None:
        get_called = False

        async def mock_get(
            path: str,
            params: dict[str, str] | list[tuple[str, str]] | None = None,
        ) -> httpx.Response:
            nonlocal get_called
            get_called = True
            return _mock_response({"id": "doc123"})

        server = _make_server()
        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            pytest.raises(ToolError, match="Invalid doc_id"),
        ):
            await server.call_tool(
                "get_doc", {"doc_id": "../../workspace/999999999/docs"}
            )

        assert get_called is False


class TestGetDocPages:
    @pytest.mark.asyncio
    async def test_returns_flat_page_list_with_defaults(self) -> None:
        captured: list[tuple[str, object]] = []

        async def mock_get(
            path: str,
            params: dict[str, str] | list[tuple[str, str]] | None = None,
        ) -> httpx.Response:
            captured.append((path, params))
            return _mock_response(
                [
                    {
                        "id": "page456",
                        "doc_id": "doc123",
                        "name": "RFC Title",
                        "content": "# Body",
                        "date_created": 1784208436171,
                        "date_updated": 1784635013781,
                        "archived": False,
                    }
                ]
            )

        server = _make_server()
        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("get_doc_pages", {"doc_id": "doc123"})
            data = json.loads(get_tool_text(result))

        path, params = captured[0]
        assert path == (
            f"{settings.api_v3_base_url}/workspaces/{settings.workspace_id}"
            "/docs/doc123/pages"
        )
        assert params == {"content_format": "text/md", "max_page_depth": "-1"}
        assert data == [
            {
                "id": "page456",
                "doc_id": "doc123",
                "name": "RFC Title",
                "content": "# Body",
                "date_created": 1784208436171,
                "date_updated": 1784635013781,
                "archived": False,
            }
        ]

    @pytest.mark.asyncio
    async def test_flattens_nested_subpages(self) -> None:
        """ClickUp nests sub-pages under their parent's "pages" key rather
        than returning a flat array — regression test for content silently
        dropped when a Doc has sub-pages."""

        async def mock_get(
            path: str,
            params: dict[str, str] | list[tuple[str, str]] | None = None,
        ) -> httpx.Response:
            return _mock_response(
                [
                    {
                        "id": "parent1",
                        "doc_id": "doc123",
                        "name": "Parent",
                        "content": "",
                        "date_created": 1,
                        "date_updated": 2,
                        "archived": False,
                        "pages": [
                            {
                                "id": "child1",
                                "doc_id": "doc123",
                                "name": "Child One",
                                "content": "child one body",
                                "date_created": 3,
                                "date_updated": 4,
                                "archived": False,
                            },
                            {
                                "id": "child2",
                                "doc_id": "doc123",
                                "name": "Child Two",
                                "content": "child two body",
                                "date_created": 5,
                                "date_updated": 6,
                                "archived": False,
                                "pages": [
                                    {
                                        "id": "grandchild1",
                                        "doc_id": "doc123",
                                        "name": "Grandchild",
                                        "content": "grandchild body",
                                        "date_created": 7,
                                        "date_updated": 8,
                                        "archived": False,
                                    }
                                ],
                            },
                        ],
                    }
                ]
            )

        server = _make_server()
        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("get_doc_pages", {"doc_id": "doc123"})
            data = json.loads(get_tool_text(result))

        assert [p["id"] for p in data] == [
            "parent1",
            "child1",
            "child2",
            "grandchild1",
        ]
        assert [p["content"] for p in data] == [
            "",
            "child one body",
            "child two body",
            "grandchild body",
        ]

    @pytest.mark.asyncio
    async def test_custom_content_format_and_depth(self) -> None:
        captured: dict[str, object] = {}

        async def mock_get(
            path: str,
            params: dict[str, str] | list[tuple[str, str]] | None = None,
        ) -> httpx.Response:
            captured["params"] = params
            return _mock_response([])

        server = _make_server()
        with patch.object(clickup_client, "get", side_effect=mock_get):
            await server.call_tool(
                "get_doc_pages",
                {
                    "doc_id": "doc123",
                    "content_format": "text/plain",
                    "max_page_depth": 2,
                },
            )

        assert captured["params"] == {
            "content_format": "text/plain",
            "max_page_depth": "2",
        }

    @pytest.mark.asyncio
    async def test_rejects_invalid_doc_id(self) -> None:
        get_called = False

        async def mock_get(
            path: str,
            params: dict[str, str] | list[tuple[str, str]] | None = None,
        ) -> httpx.Response:
            nonlocal get_called
            get_called = True
            return _mock_response([])

        server = _make_server()
        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            pytest.raises(ToolError, match="Invalid doc_id"),
        ):
            await server.call_tool(
                "get_doc_pages", {"doc_id": "../../workspace/999999999/docs"}
            )

        assert get_called is False

    @pytest.mark.asyncio
    async def test_rejects_invalid_content_format(self) -> None:
        get_called = False

        async def mock_get(
            path: str,
            params: dict[str, str] | list[tuple[str, str]] | None = None,
        ) -> httpx.Response:
            nonlocal get_called
            get_called = True
            return _mock_response([])

        server = _make_server()
        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            pytest.raises(ToolError, match="Invalid content_format"),
        ):
            await server.call_tool(
                "get_doc_pages",
                {"doc_id": "doc123", "content_format": "text/html"},
            )

        assert get_called is False


class TestGetDocPage:
    @pytest.mark.asyncio
    async def test_returns_single_page_with_defaults(self) -> None:
        captured: list[tuple[str, object]] = []

        async def mock_get(
            path: str,
            params: dict[str, str] | list[tuple[str, str]] | None = None,
        ) -> httpx.Response:
            captured.append((path, params))
            return _mock_response(
                {
                    "id": "page456",
                    "doc_id": "doc123",
                    "name": "RFC Title",
                    "content": "# Body",
                    "date_created": 1784208436171,
                    "date_updated": 1784635013781,
                    "archived": False,
                }
            )

        server = _make_server()
        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool(
                "get_doc_page", {"doc_id": "doc123", "page_id": "page456"}
            )
            data = json.loads(get_tool_text(result))

        path, params = captured[0]
        assert path == (
            f"{settings.api_v3_base_url}/workspaces/{settings.workspace_id}"
            "/docs/doc123/pages/page456"
        )
        assert params == {"content_format": "text/md"}
        assert data == {
            "id": "page456",
            "doc_id": "doc123",
            "name": "RFC Title",
            "content": "# Body",
            "date_created": 1784208436171,
            "date_updated": 1784635013781,
            "archived": False,
        }

    @pytest.mark.asyncio
    async def test_rejects_invalid_doc_id(self) -> None:
        get_called = False

        async def mock_get(
            path: str,
            params: dict[str, str] | list[tuple[str, str]] | None = None,
        ) -> httpx.Response:
            nonlocal get_called
            get_called = True
            return _mock_response({})

        server = _make_server()
        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            pytest.raises(ToolError, match="Invalid doc_id"),
        ):
            await server.call_tool(
                "get_doc_page",
                {"doc_id": "../../workspace/999999999/docs", "page_id": "page456"},
            )

        assert get_called is False

    @pytest.mark.asyncio
    async def test_rejects_invalid_page_id(self) -> None:
        get_called = False

        async def mock_get(
            path: str,
            params: dict[str, str] | list[tuple[str, str]] | None = None,
        ) -> httpx.Response:
            nonlocal get_called
            get_called = True
            return _mock_response({})

        server = _make_server()
        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            pytest.raises(ToolError, match="Invalid page_id"),
        ):
            await server.call_tool(
                "get_doc_page",
                {"doc_id": "doc123", "page_id": "page456?team_id=evil"},
            )

        assert get_called is False

    @pytest.mark.asyncio
    async def test_rejects_invalid_content_format(self) -> None:
        get_called = False

        async def mock_get(
            path: str,
            params: dict[str, str] | list[tuple[str, str]] | None = None,
        ) -> httpx.Response:
            nonlocal get_called
            get_called = True
            return _mock_response({})

        server = _make_server()
        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            pytest.raises(ToolError, match="Invalid content_format"),
        ):
            await server.call_tool(
                "get_doc_page",
                {
                    "doc_id": "doc123",
                    "page_id": "page456",
                    "content_format": "text/html",
                },
            )

        assert get_called is False
