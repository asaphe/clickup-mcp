import pytest

from clickup_mcp_server.client import (
    ClickUpAPIError,
    is_custom_task_id,
    parse_response,
)


class TestIsCustomTaskId:
    def test_dev_id(self) -> None:
        assert is_custom_task_id("DEV-1234") is True

    def test_other_prefix(self) -> None:
        assert is_custom_task_id("PROJ-456") is True

    def test_lowercase(self) -> None:
        assert is_custom_task_id("dev-100") is True

    def test_uuid(self) -> None:
        assert is_custom_task_id("abc123xyz") is False

    def test_empty(self) -> None:
        assert is_custom_task_id("") is False

    def test_no_dash(self) -> None:
        assert is_custom_task_id("DEV1234") is False


class TestParseResponse:
    def test_success(self) -> None:
        import httpx

        response = httpx.Response(200, json={"id": "abc123"})
        data = parse_response(response)
        assert data["id"] == "abc123"

    def test_error_with_err_field(self) -> None:
        import httpx

        response = httpx.Response(404, json={"err": "Task not found"})
        with pytest.raises(ClickUpAPIError) as exc_info:
            parse_response(response)
        assert exc_info.value.status_code == 404
        assert "Task not found" in exc_info.value.message

    def test_error_with_error_field(self) -> None:
        import httpx

        response = httpx.Response(400, json={"error": "Bad request"})
        with pytest.raises(ClickUpAPIError) as exc_info:
            parse_response(response)
        assert "Bad request" in exc_info.value.message

    def test_error_non_json(self) -> None:
        import httpx

        response = httpx.Response(500, text="Internal Server Error")
        with pytest.raises(ClickUpAPIError) as exc_info:
            parse_response(response)
        assert exc_info.value.status_code == 500
