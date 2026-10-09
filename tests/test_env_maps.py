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
        '{"bug": 1, "Bug": 2}',
        '{"bug": 1, "bug": 2}',
    ],
)
def test_parse_task_types_invalid(raw: str) -> None:
    assert parse_task_types(raw) is None


def test_parse_team_labels_valid() -> None:
    assert parse_team_labels('{"backend": "label-1", "n": 2}') == {
        "backend": "label-1",
        "n": "2",
    }


def test_parse_team_labels_lowercases_names() -> None:
    assert parse_team_labels('{"Backend": "label-1"}') == {"backend": "label-1"}


def test_names_match_caselessly_beyond_ascii() -> None:
    assert parse_team_labels('{"Straße": "x"}') == parse_team_labels('{"STRASSE": "x"}')
    assert parse_task_types('{"Straße": 1}') == parse_task_types('{"STRASSE": 1}')


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json",
        "[]",
        "null",
        '"x"',
        "{a: b}",
        '{"a": null}',
        '{"a": [1]}',
        '{"a": true}',
        '{"a": {"b": 1}}',
        '{"a": 1.5}',
        '{"a": ""}',
        '{"a": "  "}',
        '{"backend": "label-1", "Backend": "label-2"}',
        '{"STRASSE": "label-1", "Straße": "label-2"}',
        '{"backend": "label-1", "backend": "label-2"}',
    ],
)
def test_parse_team_labels_invalid(raw: str) -> None:
    assert parse_team_labels(raw) is None
