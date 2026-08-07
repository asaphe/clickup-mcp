"""Thin wrapper — delegates to clickup_mcp_server.setup.

Kept for backwards compatibility with existing setup instructions.
The canonical way to run setup after install is:
    clickup-mcp-server setup [--code|--desktop|--both|--remove]
"""

import sys

from clickup_mcp_server.setup import main

if __name__ == "__main__":
    sys.exit(main())
