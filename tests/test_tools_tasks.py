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
        from clickup_mcp_server.config import settings
        from clickup_mcp_server.tools.tasks import register_task_tools

        captured_params: dict[str, str] | None = None

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            nonlocal captured_params
            captured_params = params
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with patch.object(clickup_client, "get", side_effect=mock_get):
            result = await server.call_tool("get_task", {"task_id": "DEV-9999"})
            data = json.loads(get_tool_text(result))

        assert data["custom_id"] == "DEV-9999"
        assert data["status"] == "in progress"
        assert captured_params == {
            "custom_task_ids": "true",
            "team_id": settings.workspace_id,
            "include_subtasks": "true",
        }

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

    @pytest.mark.asyncio
    async def test_get_task_rejects_path_altering_id(self) -> None:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        get_called = False

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            nonlocal get_called
            get_called = True
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            pytest.raises(ToolError, match="Invalid task_id"),
        ):
            await server.call_tool(
                "get_task", {"task_id": "../../workspace/999999999/field"}
            )

        assert get_called is False


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_create_task_sends_markdown_content(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        captured_body: dict[str, object] = {}

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            if json_data:
                captured_body.update(json_data)
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with patch.object(clickup_client, "post", side_effect=mock_post):
            await server.call_tool(
                "create_task",
                {
                    "name": "Test",
                    "list_id": "123",
                    "description": "## Summary\n- item",
                },
            )

        assert captured_body["markdown_content"] == "## Summary\n- item"
        assert "description" not in captured_body

    @pytest.mark.asyncio
    async def test_create_task_sets_team_custom_field(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.config import settings
        from clickup_mcp_server.tools.tasks import register_task_tools

        monkeypatch.setattr(
            "clickup_mcp_server.tools.tasks.TEAM_LABELS",
            {"example-team": "label-1"},
        )
        monkeypatch.setattr(settings, "component_team_field_id", "field-1")
        captured_body: dict[str, object] = {}

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            if json_data:
                captured_body.update(json_data)
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with patch.object(clickup_client, "post", side_effect=mock_post):
            await server.call_tool(
                "create_task",
                {"name": "Test", "list_id": "123", "team": "example-team"},
            )

        assert captured_body["custom_fields"] == [
            {"id": "field-1", "value": ["label-1"]}
        ]

    @pytest.mark.asyncio
    async def test_create_task_invalid_team_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError

        from clickup_mcp_server.tools.tasks import register_task_tools

        monkeypatch.setattr("clickup_mcp_server.tools.tasks.TEAM_LABELS", {})
        server = FastMCP("test")
        register_task_tools(server)

        with pytest.raises(ToolError, match="Unknown team"):
            await server.call_tool(
                "create_task",
                {"name": "Test", "list_id": "123", "team": "unknown"},
            )

    @pytest.mark.asyncio
    async def test_create_task_uses_parent_list_when_different(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        captured_get_path: str | None = None
        captured_post_path: str | None = None

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            nonlocal captured_get_path
            captured_get_path = path
            return _mock_response(
                {**SAMPLE_TASK_RAW, "id": "parent1", "list": {"id": "999"}}
            )

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal captured_post_path
            captured_post_path = path
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            patch.object(clickup_client, "post", side_effect=mock_post),
        ):
            result = await server.call_tool(
                "create_task",
                {"name": "Test", "list_id": "123", "parent_task_id": "DEV-1"},
            )
            data = json.loads(get_tool_text(result))

        assert captured_get_path == "/task/DEV-1"
        assert captured_post_path == "/list/999/task"
        assert data["list_id_override"] == "999"

    @pytest.mark.asyncio
    async def test_create_task_no_override_when_parent_shares_list(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        captured_post_path: str | None = None

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(
                {**SAMPLE_TASK_RAW, "id": "parent1", "list": {"id": "123"}}
            )

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal captured_post_path
            captured_post_path = path
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            patch.object(clickup_client, "post", side_effect=mock_post),
        ):
            result = await server.call_tool(
                "create_task",
                {"name": "Test", "list_id": "123", "parent_task_id": "DEV-1"},
            )
            data = json.loads(get_tool_text(result))

        assert captured_post_path == "/list/123/task"
        assert "list_id_override" not in data

    @pytest.mark.asyncio
    async def test_create_task_rejects_path_altering_parent_task_id(self) -> None:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        post_called = False

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal post_called
            post_called = True
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "post", side_effect=mock_post),
            pytest.raises(ToolError, match="Invalid task_id"),
        ):
            await server.call_tool(
                "create_task",
                {
                    "name": "X",
                    "list_id": "123",
                    "parent_task_id": "../../workspace/1/field",
                },
            )

        assert post_called is False


class TestUpdateTask:
    @pytest.mark.asyncio
    async def test_update_task_replace_sends_markdown_content(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        captured_body: dict[str, object] = {}

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            if json_data:
                captured_body.update(json_data)
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "put", side_effect=mock_put),
            patch(
                "clickup_mcp_server.tools.tasks.resolve_task_id",
                return_value="abc123",
            ),
        ):
            await server.call_tool(
                "update_task",
                {"task_id": "TASK-9999", "description": "**new desc**"},
            )

        assert captured_body["markdown_content"] == "**new desc**"
        assert "description" not in captured_body

    @pytest.mark.asyncio
    async def test_update_task_sets_parent(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        captured_body: dict[str, object] = {}
        resolve_calls: list[str] = []

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            if json_data:
                captured_body.update(json_data)
            return _mock_response(SAMPLE_TASK_RAW)

        async def mock_resolve(task_id: str) -> str:
            resolve_calls.append(task_id)
            return f"resolved-{task_id}"

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "put", side_effect=mock_put),
            patch(
                "clickup_mcp_server.tools.tasks.resolve_task_id",
                side_effect=mock_resolve,
            ),
        ):
            await server.call_tool(
                "update_task",
                {"task_id": "TASK-9999", "parent_task_id": "TASK-1000"},
            )

        assert captured_body["parent"] == "resolved-TASK-1000"
        assert resolve_calls == ["TASK-9999", "TASK-1000"]

    @pytest.mark.asyncio
    async def test_update_task_rejects_path_altering_id(self) -> None:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        put_called = False

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal put_called
            put_called = True
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "put", side_effect=mock_put),
            pytest.raises(ToolError, match="Invalid task_id"),
        ):
            await server.call_tool(
                "update_task",
                {
                    "task_id": "../../workspace/999999999/field",
                    "name": "New name",
                },
            )

        assert put_called is False

    @pytest.mark.asyncio
    async def test_update_task_rejects_path_altering_parent_id(self) -> None:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        put_called = False

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal put_called
            put_called = True
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "put", side_effect=mock_put),
            pytest.raises(ToolError, match="Invalid task_id"),
        ):
            await server.call_tool(
                "update_task",
                {
                    "task_id": "abc123",
                    "parent_task_id": "../../workspace/999999999/field",
                },
            )

        assert put_called is False

    @pytest.mark.asyncio
    async def test_update_task_append_reads_markdown_description(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        captured_body: dict[str, object] = {}
        captured_get_params: dict[str, str] | None = None

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            nonlocal captured_get_params
            captured_get_params = params
            return _mock_response(
                {**SAMPLE_TASK_RAW, "markdown_description": "## Existing\n- item"}
            )

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            if json_data:
                captured_body.update(json_data)
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            patch.object(clickup_client, "put", side_effect=mock_put),
            patch(
                "clickup_mcp_server.tools.tasks.resolve_task_id",
                return_value="abc123",
            ),
        ):
            await server.call_tool(
                "update_task",
                {"task_id": "TASK-9999", "append_description": "## New"},
            )

        assert captured_get_params == {"include_markdown_description": "true"}
        assert captured_body["markdown_content"].startswith("## Existing\n- item")
        assert "---" in str(captured_body["markdown_content"])


class TestDeleteTask:
    @pytest.mark.asyncio
    async def test_delete_by_custom_id(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.config import settings
        from clickup_mcp_server.tools.tasks import register_task_tools

        captured_get_params: dict[str, str] | None = None
        captured_delete_path: str | None = None

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            nonlocal captured_get_params
            captured_get_params = params
            return _mock_response(SAMPLE_TASK_RAW)

        async def mock_delete(path: str) -> httpx.Response:
            nonlocal captured_delete_path
            captured_delete_path = path
            return httpx.Response(204)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            patch.object(clickup_client, "delete", side_effect=mock_delete),
        ):
            result = await server.call_tool("delete_task", {"task_id": "TASK-9999"})
            data = json.loads(get_tool_text(result))

        assert captured_get_params == {
            "custom_task_ids": "true",
            "team_id": settings.workspace_id,
        }
        assert captured_delete_path == "/task/abc123"
        assert data == {
            "status": "deleted",
            "task_id": "TASK-9999",
            "name": "Test task",
        }

    @pytest.mark.asyncio
    async def test_delete_by_uuid(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            assert params is None
            return _mock_response(SAMPLE_TASK_RAW)

        async def mock_delete(path: str) -> httpx.Response:
            return httpx.Response(204)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            patch.object(clickup_client, "delete", side_effect=mock_delete),
        ):
            result = await server.call_tool("delete_task", {"task_id": "abc123"})
            data = json.loads(get_tool_text(result))

        assert data["status"] == "deleted"
        assert data["task_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_delete_rejects_path_altering_id(self) -> None:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        delete_called = False

        async def mock_delete(path: str) -> httpx.Response:
            nonlocal delete_called
            delete_called = True
            return httpx.Response(204)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "delete", side_effect=mock_delete),
            pytest.raises(ToolError, match="Invalid task_id"),
        ):
            await server.call_tool("delete_task", {"task_id": "abc/../../other"})

        assert delete_called is False


class TestBulkUpdateTasks:
    @pytest.mark.asyncio
    async def test_bulk_invalid_team_aborts_before_any_update(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        monkeypatch.setattr("clickup_mcp_server.tools.tasks.TEAM_LABELS", {})
        put_called = False

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            nonlocal put_called
            put_called = True
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "put", side_effect=mock_put),
            pytest.raises(ToolError, match="Unknown team"),
        ):
            await server.call_tool(
                "bulk_update_tasks",
                {"task_ids": ["TASK-1"], "status": "done", "team": "unknown"},
            )

        assert put_called is False

    @pytest.mark.asyncio
    async def test_bulk_assignee_add_zero_is_applied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        captured_body: dict[str, object] = {}

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            if json_data:
                captured_body.update(json_data)
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "put", side_effect=mock_put),
            patch(
                "clickup_mcp_server.tools.tasks.resolve_task_id",
                return_value="abc123",
            ),
        ):
            await server.call_tool(
                "bulk_update_tasks",
                {"task_ids": ["TASK-1"], "assignee_add": 0},
            )

        assert captured_body["assignees"] == {"add": [0]}

    @pytest.mark.asyncio
    async def test_bulk_sanitizes_clickup_api_error_body(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            return httpx.Response(
                403,
                json={"err": "private upstream body"},
                headers={"x-ratelimit-remaining": "999"},
            )

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "put", side_effect=mock_put),
            patch(
                "clickup_mcp_server.tools.tasks.resolve_task_id",
                return_value="abc123",
            ),
        ):
            result = await server.call_tool(
                "bulk_update_tasks", {"task_ids": ["TASK-1"], "status": "done"}
            )
            data = json.loads(get_tool_text(result))

        assert data["failed"] == [
            {"task_id": "TASK-1", "error": "ClickUp API error 403"}
        ]
        assert "private upstream body" not in json.dumps(data)


class TestEnsureTaskFields:
    @pytest.mark.asyncio
    async def test_invalid_default_team_aborts_before_any_write(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        monkeypatch.setattr("clickup_mcp_server.tools.tasks.TEAM_LABELS", {})
        get_called = False

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            nonlocal get_called
            get_called = True
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            pytest.raises(ToolError, match="Unknown team"),
        ):
            await server.call_tool(
                "ensure_task_fields",
                {
                    "task_ids": ["TASK-1"],
                    "required_fields": ["team"],
                    "fix": True,
                    "default_team": "unknown",
                },
            )

        assert get_called is False

    @pytest.mark.asyncio
    async def test_ignores_default_team_when_team_not_required(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        task_missing_assignee = {**SAMPLE_TASK_RAW, "assignees": []}

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(task_missing_assignee)

        async def mock_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            return _mock_response(SAMPLE_TASK_RAW)

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            patch.object(clickup_client, "put", side_effect=mock_put),
            patch(
                "clickup_mcp_server.tools.tasks.resolve_task_id",
                return_value="abc123",
            ),
        ):
            result = await server.call_tool(
                "ensure_task_fields",
                {
                    "task_ids": ["TASK-1"],
                    "required_fields": ["assignee"],
                    "fix": True,
                    "default_assignee_id": 123,
                    "default_team": "unknown",
                },
            )
            data = json.loads(get_tool_text(result))

        assert data["all_compliant"] is True
        assert data["issues"][0]["fixed"] is True

    @pytest.mark.asyncio
    async def test_all_compliant_true_when_fix_resolves_every_issue(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mcp.server.fastmcp import FastMCP

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.config import settings
        from clickup_mcp_server.tools.tasks import register_task_tools

        monkeypatch.setattr(
            "clickup_mcp_server.tools.tasks.TEAM_LABELS",
            {"example-team": "label-1"},
        )
        monkeypatch.setattr(settings, "component_team_field_id", "field-1")
        task_missing_team = {**SAMPLE_TASK_RAW, "custom_fields": []}

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(task_missing_team)

        async def mock_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            return _mock_response({})

        server = FastMCP("test")
        register_task_tools(server)

        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            patch.object(clickup_client, "post", side_effect=mock_post),
            patch(
                "clickup_mcp_server.tools.tasks.resolve_task_id",
                return_value="abc123",
            ),
        ):
            result = await server.call_tool(
                "ensure_task_fields",
                {
                    "task_ids": ["TASK-1"],
                    "required_fields": ["team"],
                    "fix": True,
                    "default_team": "example-team",
                },
            )
            data = json.loads(get_tool_text(result))

        assert data["all_compliant"] is True
        assert data["issues"][0]["fixed"] is True


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
