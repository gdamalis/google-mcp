"""
Markdown → Docs API request transformer.

Public entry points:
    markdown_to_requests(markdown, insert_index) -> list[dict]
        Pure function — produces request list, no API calls.

    render_markdown_to_doc(service, document_id, markdown, insert_index)
        Convenience: render + batchUpdate in one call.
"""

import logging
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

logger = logging.getLogger(__name__)


class _State:
    """Mutable cursor + request accumulator passed through handlers."""
    def __init__(self, insert_index: int):
        self.cursor: int = insert_index
        self.requests: list[dict] = []

    def insert_text(self, text: str) -> tuple[int, int]:
        """Append an insertText request. Return (start, end) range."""
        start = self.cursor
        self.requests.append({
            "insertText": {"location": {"index": start}, "text": text}
        })
        self.cursor += len(text)
        return start, self.cursor

    def style_paragraph(self, start: int, end: int, style: dict, fields: str) -> None:
        self.requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": style,
                "fields": fields,
            }
        })

    def style_text(self, start: int, end: int, style: dict, fields: str) -> None:
        if start == end:
            return  # empty range — Docs API rejects
        self.requests.append({
            "updateTextStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "textStyle": style,
                "fields": fields,
            }
        })


def _render_inline(state: _State, inline_token: Token) -> int:
    """
    Render an inline token (its `children` are spans) into a single insertText
    request containing the full plain text, followed by updateTextStyle requests
    for styled ranges. Returns the end index (before any trailing newline).

    The caller is responsible for inserting the trailing "\\n".
    """
    children = inline_token.children or []
    style_stack: list[dict] = []  # active styles for nested marks

    # First pass: build plain text and collect (rel_start, rel_end, style, fields)
    # using relative offsets within the paragraph.
    plain_parts: list[str] = []
    pending_styles: list[tuple[int, int, dict, str]] = []
    rel_cursor: int = 0

    def active_style() -> tuple[dict, str]:
        merged: dict = {}
        fields: set[str] = set()
        for s in style_stack:
            for k, v in s.items():
                merged[k] = v
                fields.add(k)
        return merged, ",".join(sorted(fields))

    for child in children:
        if child.type == "text":
            rel_start = rel_cursor
            plain_parts.append(child.content)
            rel_cursor += len(child.content)
            style, fields = active_style()
            if style:
                pending_styles.append((rel_start, rel_cursor, style, fields))
        elif child.type == "softbreak":
            plain_parts.append(" ")
            rel_cursor += 1
        elif child.type == "hardbreak":
            plain_parts.append("\v")
            rel_cursor += 1
        elif child.type == "strong_open":
            style_stack.append({"bold": True})
        elif child.type == "strong_close":
            style_stack.pop()
        elif child.type == "em_open":
            style_stack.append({"italic": True})
        elif child.type == "em_close":
            style_stack.pop()
        elif child.type == "s_open":
            style_stack.append({"strikethrough": True})
        elif child.type == "s_close":
            style_stack.pop()
        elif child.type == "code_inline":
            rel_start = rel_cursor
            plain_parts.append(child.content)
            rel_cursor += len(child.content)
            pending_styles.append((
                rel_start, rel_cursor,
                {"weightedFontFamily": {"fontFamily": "Roboto Mono"}},
                "weightedFontFamily",
            ))
        elif child.type == "link_open":
            attrs = child.attrs or {}
            url = attrs.get("href", "") if isinstance(attrs, dict) else next(
                (v for k, v in attrs if k == "href"), ""
            )
            style_stack.append({"link": {"url": url}})
        elif child.type == "link_close":
            style_stack.pop()
        else:
            logger.warning("Unhandled inline token type: %s", child.type)

    # Second pass: emit single insertText for the full plain text + trailing newline
    full_text = "".join(plain_parts) + "\n"
    para_start = state.cursor
    state.insert_text(full_text)
    paragraph_end = state.cursor - 1  # end index before the trailing newline

    # Emit style requests using absolute indices
    for rel_start, rel_end, style, fields in pending_styles:
        abs_start = para_start + rel_start
        abs_end = para_start + rel_end
        state.style_text(abs_start, abs_end, style, fields)

    return paragraph_end


def _handle_paragraph(state: _State, tokens: list[Token], i: int) -> int:
    """Tokens: paragraph_open, inline, paragraph_close."""
    inline = tokens[i + 1]
    _render_inline(state, inline)
    return i + 3


def _handle_heading(state: _State, tokens: list[Token], i: int) -> int:
    """
    Tokens: heading_open, inline, heading_close.
    Returns the new token index after consuming the heading.
    """
    open_token = tokens[i]
    level = int(open_token.tag[1])  # "h1" -> 1
    inline_token = tokens[i + 1]
    start = state.cursor
    _render_inline(state, inline_token)
    end = state.cursor
    state.style_paragraph(
        start, end,
        {"namedStyleType": f"HEADING_{level}"},
        "namedStyleType",
    )
    return i + 3  # skip heading_close


def markdown_to_requests(markdown: str, insert_index: int = 1) -> list[dict]:
    """
    Convert markdown source to a list of Docs API batchUpdate requests.

    Pure function — does not call any API.

    Args:
        markdown: Markdown source string.
        insert_index: 1-based Docs index where content should begin.

    Returns:
        List of Request dicts ready for documents.batchUpdate.
    """
    md = MarkdownIt("commonmark", {"html": False}).enable("table").enable("strikethrough")
    tokens = md.parse(markdown)
    state = _State(insert_index=insert_index)

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            i = _handle_heading(state, tokens, i)
        elif tok.type == "paragraph_open":
            i = _handle_paragraph(state, tokens, i)
        else:
            logger.debug("Skipping unhandled token: %s", tok.type)
            i += 1

    return state.requests


def render_markdown_to_doc(service: Any, document_id: str, markdown: str,
                           insert_index: int = 1) -> dict:
    """
    Convenience: build requests + send batchUpdate. Returns the API response.
    """
    requests = markdown_to_requests(markdown, insert_index=insert_index)
    if not requests:
        return {"replies": [], "documentId": document_id}
    return service.documents().batchUpdate(
        documentId=document_id, body={"requests": requests}
    ).execute()
