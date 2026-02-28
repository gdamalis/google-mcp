"""
MCP application instance.

Separate module to avoid circular imports — tools import `mcp` from here,
and server.py imports both this module and the tool modules.
"""

import os

from mcp.server.fastmcp import FastMCP

account = os.environ.get("ACCOUNT", "unknown")
mcp = FastMCP(f"google-{account}")
