from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator

import pytest

from clickup_mcp_server import setup


def _completed(
    args: list[str], returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=args, returncode=returncode, stdout="", stderr=""
    )


def test_collect_workspace_config_returns_expected_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers: Iterator[str] = iter(
        [
            "workspace-1",
            "space-1",
            "folder-1",
            "field-1",
            '{"backend": "label-1"}',
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    assert setup.collect_workspace_config() == {
        "WORKSPACE_ID": "workspace-1",
        "DEVELOPMENT_SPACE_ID": "space-1",
        "SPRINTS_FOLDER_ID": "folder-1",
        "COMPONENT_TEAM_FIELD_ID": "field-1",
        "CLICKUP_TEAM_LABELS": '{"backend": "label-1"}',
    }


def test_collect_workspace_config_requires_workspace_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt: "")

    with pytest.raises(SystemExit) as exc_info:
        setup.collect_workspace_config()

    assert exc_info.value.code == 1


def test_setup_claude_code_builds_install_based_env_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args == ["claude", "mcp", "get", setup.MCP_NAME]:
            return _completed(args, returncode=1)
        return _completed(args)

    monkeypatch.setattr(setup.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(setup.subprocess, "run", fake_run)

    assert setup.setup_claude_code(
        "token-1",
        {
            "WORKSPACE_ID": "workspace-1",
            "DEVELOPMENT_SPACE_ID": "space-1",
            "SPRINTS_FOLDER_ID": "folder-1",
        },
    )

    assert calls[-1] == [
        "claude",
        "mcp",
        "add",
        "-e",
        "CLICKUP_API_TOKEN=token-1",
        "-e",
        "WORKSPACE_ID=workspace-1",
        "-e",
        "DEVELOPMENT_SPACE_ID=space-1",
        "-e",
        "SPRINTS_FOLDER_ID=folder-1",
        "-s",
        "user",
        setup.MCP_NAME,
        "--",
        setup.TOOL_BIN_NAME,
    ]
    assert "uv" not in calls[-1]
    assert "--directory" not in calls[-1]


def test_setup_claude_desktop_builds_install_based_env_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeParent:
        def mkdir(self, **_kwargs: object) -> None:
            return None

        def chmod(self, _mode: int) -> None:
            return None

    class FakeConfigPath:
        parent = FakeParent()
        content = ""

        def is_file(self) -> bool:
            return False

        def write_text(self, text: str) -> None:
            self.content = text

        def chmod(self, _mode: int) -> None:
            return None

        def __str__(self) -> str:
            return "/mock/claude_desktop_config.json"

    config_path = FakeConfigPath()
    monkeypatch.setattr(setup, "_desktop_config_path", lambda: config_path)

    assert setup.setup_claude_desktop(
        "token-1",
        {
            "WORKSPACE_ID": "workspace-1",
            "COMPONENT_TEAM_FIELD_ID": "field-1",
            "CLICKUP_TEAM_LABELS": '{"backend": "label-1"}',
        },
    )

    cfg = json.loads(config_path.content)
    server = cfg["mcpServers"][setup.MCP_NAME]
    assert server == {
        "command": setup.TOOL_BIN_NAME,
        "args": [],
        "env": {
            "CLICKUP_API_TOKEN": "token-1",
            "WORKSPACE_ID": "workspace-1",
            "COMPONENT_TEAM_FIELD_ID": "field-1",
            "CLICKUP_TEAM_LABELS": '{"backend": "label-1"}',
        },
    }


@pytest.mark.parametrize(
    ("returncode", "expected"),
    [
        (0, True),
        (1, False),
    ],
)
def test_smoke_check_installed_tool(
    monkeypatch: pytest.MonkeyPatch, returncode: int, expected: bool
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return _completed(args, returncode=returncode)

    monkeypatch.setattr(setup.subprocess, "run", fake_run)

    assert setup._smoke_check_installed_tool() is expected
    assert calls == [[setup.TOOL_BIN_NAME, "--help"]]


def test_setup_claude_code_uses_resolved_absolute_tool_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args == ["claude", "mcp", "get", setup.MCP_NAME]:
            return _completed(args, returncode=1)
        return _completed(args)

    monkeypatch.setattr(setup.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(setup.subprocess, "run", fake_run)

    assert setup.setup_claude_code(
        "token-1",
        {"WORKSPACE_ID": "workspace-1"},
        "/opt/homebrew/bin/clickup-mcp-server",
    )

    assert calls[-1][-1] == "/opt/homebrew/bin/clickup-mcp-server"


def test_setup_claude_desktop_uses_resolved_absolute_tool_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeParent:
        def mkdir(self, **_kwargs: object) -> None:
            return None

        def chmod(self, _mode: int) -> None:
            return None

    class FakeConfigPath:
        parent = FakeParent()
        content = ""

        def is_file(self) -> bool:
            return False

        def write_text(self, text: str) -> None:
            self.content = text

        def chmod(self, _mode: int) -> None:
            return None

        def __str__(self) -> str:
            return "/mock/claude_desktop_config.json"

    config_path = FakeConfigPath()
    monkeypatch.setattr(setup, "_desktop_config_path", lambda: config_path)

    assert setup.setup_claude_desktop(
        "token-1",
        {"WORKSPACE_ID": "workspace-1"},
        "/opt/homebrew/bin/clickup-mcp-server",
    )

    cfg = json.loads(config_path.content)
    assert (
        cfg["mcpServers"][setup.MCP_NAME]["command"]
        == "/opt/homebrew/bin/clickup-mcp-server"
    )


def test_setup_claude_desktop_aborts_on_unparseable_existing_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConfigPath:
        def is_file(self) -> bool:
            return True

        def read_text(self) -> str:
            return "{not valid json"

        def __str__(self) -> str:
            return "/mock/claude_desktop_config.json"

    config_path = FakeConfigPath()
    monkeypatch.setattr(setup, "_desktop_config_path", lambda: config_path)

    assert (
        setup.setup_claude_desktop("token-1", {"WORKSPACE_ID": "workspace-1"}) is False
    )


def test_install_tool_skips_reinstall_when_already_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path

    monkeypatch.setattr(
        setup.shutil, "which", lambda _name: "/home/user/.local/bin/clickup-mcp-server"
    )

    def run_only_smoke_check(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if "install" in args:
            raise AssertionError(
                "uv tool install should not run when already installed"
            )
        return _completed(args)

    monkeypatch.setattr(setup.subprocess, "run", run_only_smoke_check)

    assert setup._install_tool(Path("/usr/bin/uv")) is True


def test_op_run_survives_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("op not found")

    monkeypatch.setattr(setup.subprocess, "run", fake_run)

    result = setup._op_run(["account", "list", "--format=json"])

    assert result.returncode != 0


def test_remove_claude_code_succeeds_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(setup.shutil, "which", lambda _name: "/usr/bin/claude")

    def fake_run(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr='No MCP server named "clickup" in user scope',
        )

    monkeypatch.setattr(setup.subprocess, "run", fake_run)

    assert setup.remove_claude_code() is True


def test_remove_claude_code_fails_on_genuine_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(setup.shutil, "which", lambda _name: "/usr/bin/claude")

    def fake_run(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args, returncode=1, stdout="", stderr="internal error: something broke"
        )

    monkeypatch.setattr(setup.subprocess, "run", fake_run)

    assert setup.remove_claude_code() is False


def test_remove_claude_desktop_fails_on_unparseable_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConfigPath:
        def is_file(self) -> bool:
            return True

        def read_text(self) -> str:
            return "{not valid json"

    monkeypatch.setattr(setup, "_desktop_config_path", lambda: FakeConfigPath())

    assert setup.remove_claude_desktop() is False


def test_remove_claude_desktop_removes_existing_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConfigPath:
        content = ""

        def is_file(self) -> bool:
            return True

        def read_text(self) -> str:
            return json.dumps({"mcpServers": {setup.MCP_NAME: {"command": "x"}}})

        def write_text(self, text: str) -> None:
            self.content = text

    config_path = FakeConfigPath()
    monkeypatch.setattr(setup, "_desktop_config_path", lambda: config_path)

    assert setup.remove_claude_desktop() is True
    cfg = json.loads(config_path.content)
    assert setup.MCP_NAME not in cfg["mcpServers"]


def test_main_remove_reports_failure_when_a_step_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    monkeypatch.setattr(sys, "argv", ["setup.py", "--remove"])
    monkeypatch.setattr(setup, "remove_claude_code", lambda: False)
    monkeypatch.setattr(setup, "remove_claude_desktop", lambda: True)

    assert setup.main() == 1
