"""
Docs JSON → markdown export.

Public entry point:
    docs_to_markdown(document) -> str

Reads structural elements (paragraphs, tables, section breaks) and emits
markdown that round-trips through the transformer with reasonable fidelity.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


_HEADING_PREFIX = {
    "TITLE": "# ",
    "SUBTITLE": "## ",
    "HEADING_1": "# ",
    "HEADING_2": "## ",
    "HEADING_3": "### ",
    "HEADING_4": "#### ",
    "HEADING_5": "##### ",
    "HEADING_6": "###### ",
}


def _wrap_inline(text: str, style: dict) -> str:
    """Apply markdown marks to text per the given Docs textStyle."""
    if not text:
        return text
    out = text
    # link wins over font styling for outer wrap
    if style.get("link", {}).get("url"):
        url = style["link"]["url"]
        return f"[{out}]({url})"
    if style.get("weightedFontFamily", {}).get("fontFamily") == "Roboto Mono":
        out = f"`{out}`"
    if style.get("bold") and style.get("italic"):
        out = f"***{out}***"
    elif style.get("bold"):
        out = f"**{out}**"
    elif style.get("italic"):
        out = f"*{out}*"
    if style.get("strikethrough"):
        out = f"~~{out}~~"
    return out


def _render_paragraph(paragraph: dict) -> str:
    style_name = paragraph.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT")
    prefix = _HEADING_PREFIX.get(style_name, "")

    parts: list[str] = []
    for element in paragraph.get("elements", []):
        text_run = element.get("textRun")
        if text_run:
            content = text_run.get("content", "")
            style = text_run.get("textStyle", {})
            # Strip the trailing newline from inline rendering — we'll add it back
            if content.endswith("\n"):
                inner = content[:-1]
                parts.append(_wrap_inline(inner, style))
            else:
                parts.append(_wrap_inline(content, style))

    body = "".join(parts)
    return prefix + body + "\n"


def docs_to_markdown(document: dict) -> str:
    """
    Convert a Google Docs JSON document to markdown.

    Supports: paragraphs (incl. headings), inline styles (bold/italic/strike/code/link).
    Lists and tables come in later tasks.
    """
    content_elements = document.get("body", {}).get("content", [])
    out_lines: list[str] = []
    for element in content_elements:
        paragraph = element.get("paragraph")
        if paragraph:
            out_lines.append(_render_paragraph(paragraph))
            continue
        # tables, section breaks, etc. — added in Task 16

    return "".join(out_lines)
