"""CLI entry point for clickup-mcp-server.

Dispatches between MCP server mode (default) and setup subcommand.

Usage:
    clickup-mcp-server              # start MCP server (stdio)
    clickup-mcp-server setup        # interactive setup wizard
    clickup-mcp-server setup --code # Claude Code only
"""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[0] != "-c":
        subcmd = sys.argv[1]
        if subcmd == "setup":
            sys.argv = [sys.argv[0], *sys.argv[2:]]
            from clickup_mcp_server.setup import main as setup_main

            sys.exit(setup_main())
        if subcmd in ("-h", "--help"):
            print("Usage: clickup-mcp-server [setup]")
            print()
            print("Commands:")
            print("  (none)    Start the MCP server (stdio mode)")
            print("  setup     Configure Claude Code / Desktop")
            print()
            print("Setup options:")
            print("  --code     Claude Code only")
            print("  --desktop  Claude Desktop only")
            print("  --both     Both clients")
            print("  --remove   Unregister from both")
            return
        if subcmd.startswith("-"):
            print(f"Unknown option: {subcmd}", file=sys.stderr)
            print("Usage: clickup-mcp-server [setup] | --help", file=sys.stderr)
            sys.exit(1)
        print(f"Unknown command: {subcmd}", file=sys.stderr)
        print("Usage: clickup-mcp-server [setup] | --help", file=sys.stderr)
        sys.exit(1)

    from clickup_mcp_server.server import mcp_server

    mcp_server.run()
