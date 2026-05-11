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


def _handle_heading(state: _State, tokens: list[Token], i: int) -> int:
    """
    Tokens: heading_open, inline, heading_close.
    Returns the new token index after consuming the heading.
    """
    open_token = tokens[i]
    level = int(open_token.tag[1])  # "h1" -> 1
    inline_token = tokens[i + 1]
    text = inline_token.content
    start, end = state.insert_text(text + "\n")
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
        else:
            # Unhandled token types are skipped silently for now.
            # Subsequent tasks add handlers.
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
