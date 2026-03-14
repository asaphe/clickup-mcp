from clickup_mcp_server.models import map_comment, map_task_detail, map_task_summary
from tests.conftest import SAMPLE_TASK_RAW


class TestMapTaskSummary:
    def test_basic_mapping(self) -> None:
        result = map_task_summary(SAMPLE_TASK_RAW)
        assert result.id == "abc123"
        assert result.custom_id == "DEV-9999"
        assert result.name == "Test task"
        assert result.status == "in progress"
        assert result.assignees == ["testuser"]
        assert result.points == 3.0
        assert result.url == "https://app.clickup.com/t/abc123"
        assert result.list_name == "Sprint 31"

    def test_missing_assignees(self) -> None:
        raw = {**SAMPLE_TASK_RAW, "assignees": []}
        result = map_task_summary(raw)
        assert result.assignees == []

    def test_null_points(self) -> None:
        raw = {**SAMPLE_TASK_RAW, "points": None}
        result = map_task_summary(raw)
        assert result.points is None


class TestMapTaskDetail:
    def test_priority_extraction(self) -> None:
        result = map_task_detail(SAMPLE_TASK_RAW)
        assert result.priority == "high"

    def test_tags_extraction(self) -> None:
        result = map_task_detail(SAMPLE_TASK_RAW)
        assert result.tags == ["31-committed"]

    def test_no_custom_fields(self) -> None:
        raw = {**SAMPLE_TASK_RAW, "custom_fields": []}
        result = map_task_detail(raw)
        assert result.team is None

    def test_subtasks(self) -> None:
        sub = {
            "id": "sub1",
            "custom_id": None,
            "name": "Subtask 1",
            "status": {"status": "done"},
            "assignees": [],
            "points": None,
            "list": None,
        }
        raw = {**SAMPLE_TASK_RAW, "subtasks": [sub]}
        result = map_task_detail(raw)
        assert len(result.subtasks) == 1
        assert result.subtasks[0].status == "done"


class TestMapComment:
    def test_basic_comment(self) -> None:
        raw = {
            "id": "c1",
            "comment": [{"text": "Hello "}, {"text": "world"}],
            "user": {"username": "testuser"},
            "date": "1709000000000",
        }
        result = map_comment(raw)
        assert result.comment_text == "Hello world"
        assert result.user == "testuser"

    def test_empty_comment(self) -> None:
        raw = {
            "id": "c2",
            "comment": [],
            "user": {"username": "bot"},
            "date": "1709000000000",
        }
        result = map_comment(raw)
        assert result.comment_text == ""
