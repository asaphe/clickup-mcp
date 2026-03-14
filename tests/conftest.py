import os

os.environ.setdefault("CLICKUP_API_TOKEN", "test-token-12345")
os.environ.setdefault("WORKSPACE_ID", "123456789")
os.environ.setdefault("DEVELOPMENT_SPACE_ID", "90182208792")
os.environ.setdefault("SPRINTS_FOLDER_ID", "90183221906")


SAMPLE_TASK_RAW: dict[str, object] = {
    "id": "abc123",
    "custom_id": "DEV-9999",
    "name": "Test task",
    "status": {"status": "in progress", "color": "#4194f6"},
    "assignees": [{"id": 12345678, "username": "testuser", "email": "t@example.com"}],
    "points": 3.0,
    "description": "A test task description with PR https://github.com/org/repo/pull/42",
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
    "list": {"id": "901816121536", "name": "Sprint 31"},
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
            "id": "90183221906",
            "name": "Sprints",
            "lists": [
                {
                    "id": "901816121536",
                    "name": "Sprint 31",
                    "start_date": "1709000000000",
                    "due_date": "1710000000000",
                },
                {
                    "id": "901816121535",
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
