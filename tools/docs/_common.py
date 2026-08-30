"""
Shared helpers for Docs tools — service builders, parsers, error decorator.
"""

import functools
import logging
import re
from typing import Callable, Optional

from googleapiclient.errors import HttpError

from auth import get_service

logger = logging.getLogger(__name__)


def docs():
    """Return cached Docs API v1 service."""
    return get_service("docs", "v1")


def drive():
    """Return cached Drive API v3 service."""
    return get_service("drive", "v3")


def u16len(text: str) -> int:
    """Length of `text` in UTF-16 code units, which is how the Docs API counts.

    Python measures strings in code points, so anything outside the BMP —
    most emoji — is one short per character. Use this for every index
    calculation sent to the API; plain len() silently desynchronizes the
    cursor and everything after the emoji lands in the wrong place.
    """
    return len(text.encode("utf-16-le")) // 2


def tool_errors(fn: Callable) -> Callable:
    """
    Decorator: convert HttpError into {"error": "..."} dict.

    Validation errors raised as ValueError are also converted.
    All other exceptions propagate (programmer errors should be visible).
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HttpError as e:
            status = getattr(e, "status_code", "unknown")
            reason = getattr(e, "reason", "")
            return {"error": f"Docs API {status}: {reason}", "details": str(e)}
        except ValueError as e:
            return {"error": "Invalid input", "details": str(e)}
    return wrapper


_NAMED_COLORS = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000",
    "green": "#00aa00", "blue": "#0000ff", "yellow": "#ffff00",
    "orange": "#ff8800", "gray": "#808080", "grey": "#808080",
    "light_gray": "#d9d9d9", "dark_gray": "#404040",
}


def parse_color(value: Optional[str]) -> Optional[dict]:
    """
    Parse a color spec into a Docs API OptionalColor.color.rgbColor dict.

    Accepts:
        "#ff8800", "#f80", "ff8800", "f80", "red", "light_gray"
    Returns:
        {"red": 1.0, "green": 0.533, "blue": 0.0}
        or None if value is None.

    Raises ValueError on unparseable input.
    """
    if value is None:
        return None
    s = value.strip().lower()
    if s in _NAMED_COLORS:
        s = _NAMED_COLORS[s]
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6 or not re.fullmatch(r"[0-9a-f]{6}", s):
        raise ValueError(
            f"Unrecognized color: {value!r}. Use #rgb, #rrggbb, or a named color "
            f"({', '.join(sorted(_NAMED_COLORS))})."
        )
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    return {"red": r / 255.0, "green": g / 255.0, "blue": b / 255.0}


def pt(value: Optional[float]) -> Optional[dict]:
    """
    Wrap a points value as a Docs API Dimension dict.
    Returns None when value is None.
    Raises ValueError on negative values.
    """
    if value is None:
        return None
    if value < 0:
        raise ValueError(f"Length must be non-negative; got {value}")
    return {"magnitude": float(value), "unit": "PT"}


def end_index(document: dict) -> int:
    """Return the insertion index just before the trailing newline."""
    content = document.get("body", {}).get("content", [])
    if not content:
        return 1
    return content[-1]["endIndex"] - 1
