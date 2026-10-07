from __future__ import annotations

import pytest

from clickup_mcp_server.env_maps import parse_task_types, parse_team_labels


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"bug": 1234}', {"bug": 1234}),
        ('{"Bug": "5", "task": 0}', {"bug": 5, "task": 0}),
        ("{}", {}),
    ],
)
def test_parse_task_types_valid(raw: str, expected: dict[str, int]) -> None:
    assert parse_task_types(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json",
        "[]",
        "null",
        "{bug: 1234}",
        '{"bug": "abc"}',
        '{"bug": 1.5}',
        '{"bug": true}',
        '{"bug": null}',
        '{"bug": 1, "epic": "x"}',
    ],
)
def test_parse_task_types_invalid(raw: str) -> None:
    assert parse_task_types(raw) is None


def test_parse_team_labels_valid() -> None:
    assert parse_team_labels('{"backend": "label-1", "n": 2}') == {
        "backend": "label-1",
        "n": "2",
    }


@pytest.mark.parametrize("raw", ["", "not json", "[]", "null", '"x"', "{a: b}"])
def test_parse_team_labels_invalid(raw: str) -> None:
    assert parse_team_labels(raw) is None
