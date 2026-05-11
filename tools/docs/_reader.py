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


def _render_bullet_line(paragraph: dict, document: dict) -> str:
    """A paragraph that has a `bullet` field — render as a list item."""
    bullet = paragraph.get("bullet") or {}
    list_id = bullet.get("listId")
    nesting = bullet.get("nestingLevel", 0)

    # Determine glyph from document.lists[listId].listProperties.nestingLevels[nesting].glyphType
    glyph_type = "GLYPH_TYPE_UNSPECIFIED"
    lists = document.get("lists", {})
    if list_id and list_id in lists:
        levels = lists[list_id].get("listProperties", {}).get("nestingLevels", [])
        if nesting < len(levels):
            glyph_type = levels[nesting].get("glyphType", glyph_type)

    if glyph_type in ("DECIMAL", "ALPHA", "ROMAN", "UPPER_ALPHA", "UPPER_ROMAN"):
        marker = "1. "
    elif glyph_type == "GLYPH_TYPE_UNSPECIFIED" and list_id in lists:
        # Try to detect checkbox by glyphSymbol
        levels = lists[list_id].get("listProperties", {}).get("nestingLevels", [])
        if nesting < len(levels) and levels[nesting].get("glyphSymbol") == "☐":
            marker = "- [ ] "
        else:
            marker = "- "
    else:
        marker = "- "

    inline_parts = []
    for element in paragraph.get("elements", []):
        text_run = element.get("textRun")
        if text_run:
            content = text_run.get("content", "")
            style = text_run.get("textStyle", {})
            if content.endswith("\n"):
                inner = content[:-1]
                inline_parts.append(_wrap_inline(inner, style))
            else:
                inline_parts.append(_wrap_inline(content, style))

    indent = "  " * nesting
    return f"{indent}{marker}{''.join(inline_parts)}\n"


def _render_table(table: dict) -> str:
    rows: list[list[str]] = []
    for tr in table.get("tableRows", []):
        cells: list[str] = []
        for tc in tr.get("tableCells", []):
            cell_text_parts = []
            for content in tc.get("content", []):
                p = content.get("paragraph")
                if p:
                    line = _render_paragraph(p)
                    cell_text_parts.append(line.rstrip("\n"))
            cells.append(" ".join(cell_text_parts).strip() or " ")
        rows.append(cells)

    if not rows:
        return ""

    col_count = max(len(r) for r in rows)
    for r in rows:
        while len(r) < col_count:
            r.append(" ")

    lines = [
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join(["---"] * col_count) + " |",
    ]
    for r in rows[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines) + "\n"


def docs_to_markdown(document: dict) -> str:
    content_elements = document.get("body", {}).get("content", [])
    out_lines: list[str] = []
    for element in content_elements:
        paragraph = element.get("paragraph")
        if paragraph:
            if paragraph.get("bullet"):
                out_lines.append(_render_bullet_line(paragraph, document))
            else:
                out_lines.append(_render_paragraph(paragraph))
            continue
        table = element.get("table")
        if table:
            out_lines.append(_render_table(table))
            continue
        # section breaks etc. ignored

    return "".join(out_lines)
