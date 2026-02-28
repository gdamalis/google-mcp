"""
Google MCP Server — entry point.

STDIO transport: all logging goes to stderr, stdout is MCP JSON-RPC.
"""

import sys
import logging

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from app import mcp  # noqa: E402

# Import tool modules — their @mcp.tool() decorators register tools on import
import tools.gmail  # noqa: F401, E402
import tools.calendar  # noqa: F401, E402
import tools.docs  # noqa: F401, E402
import tools.sheets  # noqa: F401, E402

if __name__ == "__main__":
    mcp.run(transport="stdio")
