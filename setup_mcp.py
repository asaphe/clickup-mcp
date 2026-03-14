"""Set up the ClickUp MCP Server for Claude Code and/or Claude Desktop.

Usage:
    python3 setup_mcp.py            # interactive mode
    python3 setup_mcp.py --code     # Claude Code only
    python3 setup_mcp.py --desktop  # Claude Desktop only
    python3 setup_mcp.py --both     # both clients
    python3 setup_mcp.py --remove   # unregister from both
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

MCP_NAME = "clickup"

IS_WINDOWS = platform.system() == "Windows"


def _supports_color() -> bool:
    if IS_WINDOWS:
        return os.environ.get("WT_SESSION") is not None or "ANSICON" in os.environ
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


USE_COLOR = _supports_color()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def info(msg: str) -> None:
    print(f"  {_c('0;34', '▸')} {msg}")


def ok(msg: str) -> None:
    print(f"  {_c('0;32', '✓')} {msg}")


def warn(msg: str) -> None:
    print(f"  {_c('1;33', '!')} {msg}")


def fail(msg: str) -> None:
    print(f"  {_c('0;31', '✗')} {msg}")


def bold(msg: str) -> str:
    return _c("1", msg)


def _start_script_path() -> Path:
    return Path(__file__).resolve().parent / "start-clickup-mcp.sh"


# --- Token setup ---


def _op_cli_available() -> bool:
    return shutil.which("op") is not None


def _op_run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["op", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _op_list_accounts() -> list[dict[str, object]]:
    result = _op_run(["account", "list", "--format=json"])
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return []


def _op_list_vaults(account_id: str) -> list[dict[str, object]]:
    result = _op_run(["vault", "list", "--account", account_id, "--format=json"])
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return []


def _op_search_items(
    account_id: str, vault_name: str, query: str
) -> list[dict[str, object]]:
    result = _op_run(
        [
            "item",
            "list",
            "--vault",
            vault_name,
            "--account",
            account_id,
            "--format=json",
        ]
    )
    if result.returncode != 0:
        return []
    try:
        items: list[dict[str, object]] = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return []
    q = query.lower()
    return [i for i in items if q in str(i.get("title", "")).lower()]


def _op_get_item_fields(
    account_id: str, vault_name: str, item_id: str
) -> list[dict[str, object]]:
    result = _op_run(
        [
            "item",
            "get",
            item_id,
            "--vault",
            vault_name,
            "--account",
            account_id,
            "--format=json",
        ]
    )
    if result.returncode != 0:
        return []
    try:
        item: dict[str, object] = json.loads(result.stdout)
        fields = item.get("fields", [])
        return fields if isinstance(fields, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _pick_from_list(items: list[str], prompt: str) -> str | None:
    for i, item in enumerate(items, 1):
        print(f"    {bold(str(i))}) {item}")
    print()
    choice = input(f"  {prompt} ").strip()
    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(items):
        return None
    return items[int(choice) - 1]


def _pick_from_list_idx(items: list[str], prompt: str) -> int | None:
    for i, item in enumerate(items, 1):
        print(f"    {bold(str(i))}) {item}")
    print()
    choice = input(f"  {prompt} ").strip()
    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(items):
        return None
    return int(choice) - 1


def _find_token_field(fields: list[dict[str, object]]) -> str | None:
    candidates = [
        f
        for f in fields
        if f.get("type") == "CONCEALED" and f.get("purpose") != "PASSWORD"
    ]
    if len(candidates) == 1:
        return str(candidates[0].get("label", ""))
    return None


def _read_token_from_1password() -> str | None:
    print()
    print(f"    {bold('1Password token retrieval')}")
    print()

    accounts = _op_list_accounts()
    if not accounts:
        fail("No 1Password accounts found. Run: op signin")
        return None

    if len(accounts) == 1:
        account = accounts[0]
        ok(f"Using account: {account.get('email', account.get('url', 'default'))}")
    else:
        print("    Which 1Password account?")
        labels = [f"{a.get('email', 'unknown')} ({a.get('url', '')})" for a in accounts]
        idx = _pick_from_list_idx(labels, "Account [number]:")
        if idx is None:
            fail("Invalid choice.")
            return None
        account = accounts[idx]

    account_id = str(account.get("account_uuid", account.get("user_uuid", "")))

    print()
    info("Loading vaults...")
    vaults = _op_list_vaults(account_id)
    if not vaults:
        fail("Could not list vaults. Check your 1Password sign-in.")
        return None

    vault_names = [str(v.get("name", "unnamed")) for v in vaults]
    if len(vault_names) == 1:
        vault = vault_names[0]
    else:
        print("    Which vault contains your ClickUp token?")
        picked_vault = _pick_from_list(vault_names, "Vault [number]:")
        if not picked_vault:
            fail("Invalid choice.")
            return None
        vault = picked_vault
    ok(f"Vault: {vault}")

    print()
    info('Searching for "clickup" items...')
    matches = _op_search_items(account_id, vault, "clickup")

    if not matches:
        info("No items matching 'clickup' found. Listing all items in vault...")
        all_items = _op_search_items(account_id, vault, "")
        if all_items:
            print()
            print("    Which item contains your ClickUp API token?")
            labels = [str(m.get("title", "unnamed")) for m in all_items]
            idx = _pick_from_list_idx(labels, "Item [number]:")
            if idx is not None:
                matches = [all_items[idx]]
        if not matches:
            fail("No item selected.")
            return None

    if len(matches) == 1:
        item = matches[0]
        ok(f"Found: {item.get('title', '?')}")
    else:
        print("    Which item?")
        labels = [str(m.get("title", "unnamed")) for m in matches]
        idx = _pick_from_list_idx(labels, "Item [number]:")
        if idx is None:
            fail("Invalid choice.")
            return None
        item = matches[idx]

    item_id = str(item.get("id", ""))
    item_title = str(item.get("title", ""))

    info("Reading item fields...")
    fields = _op_get_item_fields(account_id, vault, item_id)
    auto_field = _find_token_field(fields)

    if auto_field:
        ok(f"Detected token field: {auto_field}")
        field_name = auto_field
    else:
        concealed = [
            f for f in fields if f.get("type") == "CONCEALED" and f.get("label")
        ]
        if concealed:
            print("    Which field contains the API token?")
            field_labels = [str(f.get("label", "?")) for f in concealed]
            picked_field = _pick_from_list(field_labels, "Field [number]:")
            if not picked_field:
                fail("Invalid choice.")
                return None
            field_name = picked_field
        else:
            field_name = input("  Field name [API Token]: ").strip() or "API Token"

    info(f"Reading field '{field_name}' from '{item_title}'...")

    result = _op_run(
        [
            "item",
            "get",
            item_id,
            "--vault",
            vault,
            "--account",
            account_id,
            "--fields",
            f"label={field_name}",
            "--format=json",
        ]
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "sign in" in stderr.lower() or "not signed in" in stderr.lower():
            fail("Not signed in to 1Password CLI. Run: op signin")
        else:
            fail(f"1Password read failed: {stderr}")
        return None

    try:
        field_data = json.loads(result.stdout)
        token = str(field_data.get("value", "")).strip()
    except (json.JSONDecodeError, TypeError, AttributeError):
        token = result.stdout.strip()

    if not token:
        fail("1Password returned an empty value.")
        return None

    ok("Token retrieved from 1Password.")
    return token


def collect_token() -> str | None:
    if os.environ.get("CLICKUP_API_TOKEN"):
        ok("CLICKUP_API_TOKEN found in environment.")
        return os.environ["CLICKUP_API_TOKEN"]

    print(f"  {bold('Token setup')}")
    print()
    print("  How would you like to provide your ClickUp API token?")
    print()

    has_op = _op_cli_available()

    if has_op:
        print(
            f"    {bold('1')}) 1Password (recommended — keeps the token in your vault)"
        )
        print(f"    {bold('2')}) Paste token directly")
        print()
        choice = input("  Choice [1/2]: ").strip()
        if choice == "1":
            token = _read_token_from_1password()
            if token:
                return token
            print()
            info("Falling back to manual paste.")
            print()
    else:
        info("1Password CLI not found — install with: brew install 1password-cli")
        print("    (Recommended for secure token storage)")
        print()

    print(
        f"    Get a personal API token at: {bold('https://app.clickup.com/settings/apps')}"
    )
    print()
    token = input("  Paste your ClickUp API token: ").strip()
    if not token:
        fail("No token provided.")
        return None

    ok("Token received.")
    return token


# --- Workspace config ---

_WORKSPACE_HINT = "Settings → Workspaces, or from any ClickUp URL: app.clickup.com/{workspace_id}/..."
_SPACE_HINT = "Click a Space → ID is in the URL: /s/{space_id}/..."
_FOLDER_HINT = "The folder containing your sprint lists. Find it via get_workspace_hierarchy tool or URL."
_FIELD_HINT = "Custom field ID for your Component/Team dropdown. Use the ClickUp API: GET /list/{id}/field"
_LABELS_HINT = 'JSON mapping: {"backend": "uuid-1", "frontend": "uuid-2"}'


def collect_workspace_config() -> dict[str, str]:
    """Collect workspace-specific env vars interactively."""
    env_vars: dict[str, str] = {}

    print(f"  {bold('Workspace configuration')}")
    print()
    print(f"  {bold('WORKSPACE_ID')} (required)")
    print(f"    Hint: {_WORKSPACE_HINT}")
    print()
    workspace_id = input("  Workspace ID: ").strip()
    if not workspace_id:
        fail("Workspace ID is required.")
        raise SystemExit(1)
    env_vars["WORKSPACE_ID"] = workspace_id
    ok(f"Workspace ID: {workspace_id}")
    print()

    print(f"  {bold('Optional: Sprint detection')}")
    print("  Press Enter to skip (sprint tools will be disabled).")
    print()

    print(f"    {_SPACE_HINT}")
    space_id = input("  DEVELOPMENT_SPACE_ID [skip]: ").strip()
    if space_id:
        env_vars["DEVELOPMENT_SPACE_ID"] = space_id
        ok(f"Space ID: {space_id}")

        print(f"    {_FOLDER_HINT}")
        folder_id = input("  SPRINTS_FOLDER_ID [skip]: ").strip()
        if folder_id:
            env_vars["SPRINTS_FOLDER_ID"] = folder_id
            ok(f"Sprints folder ID: {folder_id}")
    print()

    print(f"  {bold('Optional: Team labels')}")
    print("  Press Enter to skip (team filtering will be disabled).")
    print()

    print(f"    {_FIELD_HINT}")
    field_id = input("  COMPONENT_TEAM_FIELD_ID [skip]: ").strip()
    if field_id:
        env_vars["COMPONENT_TEAM_FIELD_ID"] = field_id
        ok(f"Team field ID: {field_id}")

        print(f"    {_LABELS_HINT}")
        labels = input("  CLICKUP_TEAM_LABELS [skip]: ").strip()
        if labels:
            env_vars["CLICKUP_TEAM_LABELS"] = labels
            ok("Team labels configured.")
    print()

    return env_vars


# --- Claude Code ---


def _claude_code_available() -> bool:
    return shutil.which("claude") is not None


def setup_claude_code(token: str, env_vars: dict[str, str]) -> bool:
    if not _claude_code_available():
        fail("Claude Code CLI not found.")
        print(
            f"    Install: {bold('https://docs.anthropic.com/en/docs/claude-code/overview')}"
        )
        return False

    script = _start_script_path()
    if not script.is_file():
        fail(f"Start script not found: {script}")
        return False

    try:
        result = subprocess.run(
            ["claude", "mcp", "get", MCP_NAME],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            info(f"MCP server '{MCP_NAME}' already configured — updating.")
            subprocess.run(
                ["claude", "mcp", "remove", MCP_NAME, "-s", "user"],
                capture_output=True,
                check=False,
            )
    except FileNotFoundError:
        fail("Claude Code CLI not found.")
        return False

    all_env = {"CLICKUP_API_TOKEN": token, **env_vars}
    cmd: list[str] = ["claude", "mcp", "add"]
    for key, value in all_env.items():
        cmd.extend(["-e", f"{key}={value}"])
    cmd.extend(["-s", "user", MCP_NAME, str(script)])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"Failed to add MCP server: {result.stderr.strip()}")
        return False

    ok(f"Added '{MCP_NAME}' to Claude Code (user scope).")
    return True


def remove_claude_code() -> bool:
    if not _claude_code_available():
        return True
    result = subprocess.run(
        ["claude", "mcp", "remove", MCP_NAME, "-s", "user"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        ok(f"Removed '{MCP_NAME}' from Claude Code.")
    return True


# --- Claude Desktop ---


def _desktop_config_path() -> Path:
    system = platform.system()
    if system == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    if system == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def setup_claude_desktop(token: str, env_vars: dict[str, str]) -> bool:
    script = _start_script_path()
    if not script.is_file():
        fail(f"Start script not found: {script}")
        return False

    config_path = _desktop_config_path()

    if config_path.is_file():
        try:
            cfg = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            cfg = {}
        if MCP_NAME in cfg.get("mcpServers", {}):
            info(f"MCP server '{MCP_NAME}' already configured — updating.")
    else:
        cfg = {}

    config_path.parent.mkdir(parents=True, exist_ok=True)

    cfg.setdefault("mcpServers", {})
    all_env = {"CLICKUP_API_TOKEN": token, **env_vars}
    cfg["mcpServers"][MCP_NAME] = {
        "command": str(script),
        "env": all_env,
    }

    config_path.write_text(json.dumps(cfg, indent=2) + "\n")
    ok(f"Added '{MCP_NAME}' to Claude Desktop config.")
    print(f"    Config: {config_path}")
    return True


def remove_claude_desktop() -> bool:
    config_path = _desktop_config_path()
    if not config_path.is_file():
        return True

    try:
        cfg = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return True

    servers = cfg.get("mcpServers", {})
    if MCP_NAME in servers:
        del servers[MCP_NAME]
        config_path.write_text(json.dumps(cfg, indent=2) + "\n")
        ok(f"Removed '{MCP_NAME}' from Claude Desktop config.")
    return True


# --- Claude Desktop restart ---


def _is_claude_desktop_running() -> bool:
    system = platform.system()
    try:
        if system == "Darwin":
            result = subprocess.run(
                ["pgrep", "-x", "Claude"],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        if system == "Windows":
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Claude.exe", "/NH"],
                capture_output=True,
                text=True,
                check=False,
            )
            return "Claude.exe" in result.stdout
        result = subprocess.run(
            ["pgrep", "-x", "claude-desktop"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _restart_claude_desktop() -> bool:
    system = platform.system()
    was_running = _is_claude_desktop_running()

    try:
        if was_running:
            info("Stopping Claude Desktop...")
            if system == "Darwin":
                subprocess.run(
                    ["osascript", "-e", 'quit app "Claude"'],
                    capture_output=True,
                    check=False,
                )
            elif system == "Windows":
                subprocess.run(
                    ["taskkill", "/IM", "Claude.exe"],
                    capture_output=True,
                    check=False,
                )
            else:
                subprocess.run(
                    ["pkill", "-x", "claude-desktop"],
                    capture_output=True,
                    check=False,
                )

            import time

            for _ in range(10):
                time.sleep(1)
                if not _is_claude_desktop_running():
                    break

            info("Starting Claude Desktop...")
        else:
            info("Launching Claude Desktop...")

        if system == "Darwin":
            subprocess.Popen(
                ["open", "-a", "Claude"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif system == "Windows":
            app_path = (
                Path(os.environ.get("LOCALAPPDATA", ""))
                / "Programs"
                / "claude"
                / "Claude.exe"
            )
            if app_path.is_file():
                subprocess.Popen(
                    [str(app_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                warn(
                    "Could not find Claude.exe — please start Claude Desktop manually."
                )
                return False
        elif shutil.which("claude-desktop"):
            subprocess.Popen(
                ["claude-desktop"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            warn("Could not find claude-desktop — please start it manually.")
            return False

        action = "Restarted" if was_running else "Launched"
        ok(f"{action} Claude Desktop.")
        return True

    except OSError as exc:
        warn(f"Could not restart Claude Desktop: {exc}")
        print("    Please restart it manually.")
        return False


# --- Main ---


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set up the ClickUp MCP Server for Claude Code and/or Claude Desktop.",
    )
    parser.add_argument(
        "--code", action="store_true", help="Configure Claude Code only"
    )
    parser.add_argument(
        "--desktop", action="store_true", help="Configure Claude Desktop only"
    )
    parser.add_argument("--both", action="store_true", help="Configure both clients")
    parser.add_argument(
        "--remove", action="store_true", help="Unregister from both clients"
    )
    args = parser.parse_args()

    print()
    print(f"  {bold('ClickUp MCP Server Setup')}")
    print("  Connects Claude to ClickUp for task management, sprints, and reporting.")
    print()

    if args.remove:
        remove_claude_code()
        remove_claude_desktop()
        print()
        ok("Unregistered from all clients.")
        print()
        return 0

    if not args.code and not args.desktop and not args.both:
        print("  Which client(s) do you want to configure?")
        print(f"    {bold('1')}) Claude Code (CLI)")
        print(f"    {bold('2')}) Claude Desktop (app)")
        print(f"    {bold('3')}) Both")
        print()
        choice = input("  Choice [1/2/3]: ").strip()
        args.code = choice == "1"
        args.desktop = choice == "2"
        args.both = choice == "3"
        if not args.code and not args.desktop and not args.both:
            fail("Invalid choice. Run the script again.")
            return 1

    print()

    token = collect_token()
    if not token:
        print()
        return 1
    print()

    env_vars = collect_workspace_config()

    rc = 0
    if args.code or args.both:
        if not setup_claude_code(token, env_vars):
            rc = 1
        print()

    desktop_configured = False
    if args.desktop or args.both:
        if not setup_claude_desktop(token, env_vars):
            rc = 1
        else:
            desktop_configured = True
        print()

    if desktop_configured and _is_claude_desktop_running():
        _restart_claude_desktop()
        print()

    if rc == 0:
        print(f"  {_c('1;32', 'Setup complete!')}")
        print()
        print("  Next steps:")
        print("    1. Start a new conversation")
        print("    2. Try: 'show my tasks' or 'sprint report'")
    else:
        warn("Some setup steps failed. Review the errors above.")

    print()
    return rc


if __name__ == "__main__":
    sys.exit(main())
