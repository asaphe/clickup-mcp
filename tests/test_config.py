import pytest

from clickup_mcp_server.config import _load_task_types


class TestLoadTaskTypes:
    def test_mapping_lowercases_names_and_accepts_digit_strings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CLICKUP_TASK_TYPES", '{"Bug": 1234, "epic": "5678"}')
        assert _load_task_types() == {"bug": 1234, "epic": 5678}

    def test_unset_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLICKUP_TASK_TYPES", raising=False)
        assert _load_task_types() == {}

    @pytest.mark.parametrize(
        "raw",
        [
            "not json",
            '["bug", 1234]',
            '{"bug": "abc"}',
            '{"bug": 1.5}',
            '{"bug": true}',
            '{"bug": null}',
        ],
    )
    def test_malformed_is_empty(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        monkeypatch.setenv("CLICKUP_TASK_TYPES", raw)
        assert _load_task_types() == {}
