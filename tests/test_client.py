import pytest

from clickup_mcp_server.client import (
    ClickUpAPIError,
    is_custom_task_id,
    parse_response,
    validate_list_id,
    validate_space_id,
    validate_task_id,
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


class TestValidateTaskId:
    def test_custom_id_passes(self) -> None:
        assert validate_task_id("TASK-1234") == "TASK-1234"

    def test_uuid_like_id_passes(self) -> None:
        assert validate_task_id("abc123_xyz") == "abc123_xyz"

    @pytest.mark.parametrize(
        "malicious_id",
        [
            "../../workspace/999999999/field",
            "abc123/../../list/1",
            "abc?team_id=evil",
            "abc#fragment",
            "abc 123",
            "abc123\n",
            "",
        ],
    )
    def test_rejects_path_altering_characters(self, malicious_id: str) -> None:
        with pytest.raises(ValueError, match="Invalid task_id"):
            validate_task_id(malicious_id)


class TestValidateListId:
    def test_numeric_id_passes(self) -> None:
        assert validate_list_id("123456789") == "123456789"

    @pytest.mark.parametrize(
        "malicious_id",
        ["123/../../task/x", "123?x=y", "123#fragment", "abc", "", "123 456"],
    )
    def test_rejects_non_numeric_id(self, malicious_id: str) -> None:
        with pytest.raises(ValueError, match="Invalid list_id"):
            validate_list_id(malicious_id)


class TestValidateSpaceId:
    def test_numeric_id_passes(self) -> None:
        assert validate_space_id("123456789") == "123456789"

    @pytest.mark.parametrize(
        "malicious_id",
        ["123/../../field", "123?x=y", "123#fragment", "abc", "", "123 456"],
    )
    def test_rejects_non_numeric_id(self, malicious_id: str) -> None:
        with pytest.raises(ValueError, match="Invalid space_id"):
            validate_space_id(malicious_id)


class TestParseResponse:
    def test_success(self) -> None:
        import httpx

        response = httpx.Response(200, json={"id": "abc123"})
        data = parse_response(response)
        assert data["id"] == "abc123"

    def test_204_no_content(self, caplog: pytest.LogCaptureFixture) -> None:
        import httpx

        response = httpx.Response(204)
        with caplog.at_level("WARNING"):
            assert parse_response(response) == {}
        assert caplog.records == []

    def test_200_empty_body_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import httpx

        response = httpx.Response(200, content=b"")
        with caplog.at_level("WARNING"):
            assert parse_response(response) == {}
        assert any("Empty body with status 200" in r.message for r in caplog.records)

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
