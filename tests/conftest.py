import os

import pytest

os.environ.setdefault("CLICKUP_API_TOKEN", "test-token-12345")
os.environ.setdefault("WORKSPACE_ID", "123456789")
os.environ.setdefault("DEVELOPMENT_SPACE_ID", "222222222")
os.environ.setdefault("SPRINTS_FOLDER_ID", "333333333")

BACKEND_OPTION_ID = "00000000-0000-4000-8000-0000000000b1"
FRONTEND_OPTION_ID = "00000000-0000-4000-8000-0000000000f1"
DATA_PLATFORM_OPTION_ID = "00000000-0000-4000-8000-0000000000d1"
PLATFORM_OPTION_ID = "00000000-0000-4000-8000-000000000071"
RESEARCH_OPTION_ID = "00000000-0000-4000-8000-0000000000e5"


def live_team_options() -> dict[str, str]:
    """The Component/Team field's live options as ClickUp labels them."""
    return {
        BACKEND_OPTION_ID: "Backend",
        FRONTEND_OPTION_ID: "Frontend Web squad",
        DATA_PLATFORM_OPTION_ID: "Data Platform",
        PLATFORM_OPTION_ID: "Platform ",
        RESEARCH_OPTION_ID: "Research",
    }


@pytest.fixture(autouse=True)
def stub_team_options(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    """Serve live team options from memory so unit tests never call ClickUp for them."""
    from clickup_mcp_server import team_labels
    from clickup_mcp_server.config import settings

    options = live_team_options()
    if request.module.__name__.endswith("test_integration"):
        return options

    monkeypatch.setattr(settings, "component_team_field_id", "test-field-id")
    if request.node.get_closest_marker("real_team_fetch"):
        return options

    async def fetch(space_id: str | None = None) -> dict[str, str]:
        return dict(options)

    monkeypatch.setattr(team_labels, "fetch_team_options", fetch)
    return options


SAMPLE_TASK_RAW: dict[str, object] = {
    "id": "abc123",
    "custom_id": "DEV-9999",
    "name": "Test task",
    "status": {"status": "in progress", "color": "#4194f6"},
    "assignees": [{"id": 12345678, "username": "testuser", "email": "t@example.com"}],
    "points": 3.0,
    "description": "A test task description with PR https://github.com/org/repo/pull/42",
    "markdown_description": "A test task description with PR https://github.com/org/repo/pull/42",
    "priority": {"priority": "high", "id": "2"},
    "tags": [{"name": "31-committed"}],
    "parent": None,
    "subtasks": [],
    "custom_fields": [
        {
            "id": "test-field-id",
            "name": "Component/Team",
            "value": ["test-label-id"],
        }
    ],
    "list": {"id": "444444444", "name": "Sprint 31"},
    "date_created": "1709000000000",
    "date_updated": "1709100000000",
    "date_done": None,
}

SAMPLE_USER_RAW: dict[str, object] = {
    "user": {
        "id": 12345678,
        "username": "testuser",
        "email": "testuser@example.com",
    }
}

SAMPLE_FOLDER_RAW: dict[str, object] = {
    "folders": [
        {
            "id": "333333333",
            "name": "Sprints",
            "lists": [
                {
                    "id": "444444444",
                    "name": "Sprint 31",
                    "start_date": "1709000000000",
                    "due_date": "1710000000000",
                },
                {
                    "id": "555555555",
                    "name": "Sprint 30",
                    "start_date": "1708000000000",
                    "due_date": "1708999999999",
                },
            ],
        }
    ]
}

SAMPLE_COMMENTS_RAW: dict[str, object] = {
    "comments": [
        {
            "id": "comment1",
            "comment": [{"text": "Merged PR https://github.com/org/repo/pull/55"}],
            "user": {"username": "testuser"},
            "date": "1709050000000",
        }
    ]
}
