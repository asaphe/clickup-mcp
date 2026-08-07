from __future__ import annotations

import importlib
import sys

import pytest


def test_cli_module_imports_cleanly() -> None:
    module = importlib.import_module("clickup_mcp_server.cli")

    assert module is not None


def test_setup_module_imports_cleanly() -> None:
    module = importlib.import_module("clickup_mcp_server.setup")

    assert module is not None


def test_cli_setup_help_dispatches_to_setup(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from clickup_mcp_server import cli

    monkeypatch.setattr(sys, "argv", ["prog", "setup", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "Configure Claude Code only" in out
    assert "Configure Claude Desktop only" in out


def test_cli_unknown_subcommand_errors_instead_of_starting_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from clickup_mcp_server import cli

    monkeypatch.setattr(sys, "argv", ["prog", "setp"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Unknown command: setp" in err


def test_cli_unknown_flag_errors_instead_of_starting_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from clickup_mcp_server import cli

    monkeypatch.setattr(sys, "argv", ["prog", "--code"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Unknown option: --code" in err
