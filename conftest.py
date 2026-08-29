"""
Pytest bootstrap.

`auth.py` exits at import time when ACCOUNT is unset, and importing any tool
module reaches it. Supply a placeholder so `uv run pytest` works with no
ceremony — nothing here authenticates, credentials are never loaded.
"""

import os

os.environ.setdefault("ACCOUNT", "test")
