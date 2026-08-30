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

from ._common import u16len

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
        self.cursor += u16len(text)
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
    Render an inline token (its `children` are spans) into insertText requests
    containing the plain text, followed by updateTextStyle requests for styled
    ranges. When an inline image is encountered, the text buffer is flushed first,
    then an insertInlineImage request is appended. Returns the end index (before
    any trailing newline).

    The caller is responsible for inserting the trailing "\\n".
    """
    children = inline_token.children or []
    style_stack: list[dict] = []  # active styles for nested marks

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

    def flush_buffer() -> None:
        nonlocal plain_parts, pending_styles, rel_cursor
        if not plain_parts:
            return
        full_text = "".join(plain_parts)
        para_start = state.cursor
        state.insert_text(full_text)
        for rel_start, rel_end, style, fields in pending_styles:
            state.style_text(para_start + rel_start, para_start + rel_end, style, fields)
        plain_parts = []
        pending_styles = []
        rel_cursor = 0

    for child in children:
        if child.type == "text":
            rel_start = rel_cursor
            plain_parts.append(child.content)
            rel_cursor += u16len(child.content)
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
            rel_cursor += u16len(child.content)
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
        elif child.type == "image":
            attrs = child.attrs or {}
            src = attrs.get("src", "") if isinstance(attrs, dict) else next(
                (v for k, v in attrs if k == "src"), ""
            )
            if src.startswith("http://") or src.startswith("https://"):
                flush_buffer()
                state.requests.append({
                    "insertInlineImage": {
                        "location": {"index": state.cursor},
                        "uri": src,
                    }
                })
                state.cursor += 1  # images are 1 char wide in Docs
            else:
                logger.warning("Skipping local image path (Drive upload required): %s", src)
        else:
            logger.warning("Unhandled inline token type: %s", child.type)

    # Append the trailing newline to plain_parts, then flush everything
    plain_parts.append("\n")
    rel_cursor += 1
    flush_buffer()

    return state.cursor - 1  # end index before the trailing newline


_BULLET_PRESETS = {
    "bullet": "BULLET_DISC_CIRCLE_SQUARE",
    "ordered": "NUMBERED_DECIMAL_ALPHA_ROMAN",
    "checkbox": "BULLET_CHECKBOX",
}


def _is_checkbox_item(inline_token: Token) -> bool:
    """Detect GFM task list items: `[ ]` or `[x]` at the start of inline content."""
    children = inline_token.children or []
    if not children or children[0].type != "text":
        return False
    text = children[0].content
    return text.startswith(("[ ] ", "[x] ", "[X] "))


def _strip_checkbox_marker(inline_token: Token) -> bool:
    """Mutate the inline's first text child to remove the `[ ]`/`[x]` marker.
    Returns True if a checkbox marker was found and stripped."""
    children = inline_token.children or []
    if not children or children[0].type != "text":
        return False
    text = children[0].content
    for prefix in ("[ ] ", "[x] ", "[X] "):
        if text.startswith(prefix):
            children[0].content = text[len(prefix):]
            return True
    return False


def _handle_list(state: _State, tokens: list[Token], i: int, depth: int = 0) -> int:
    """
    Handle bullet_list_open or ordered_list_open. Returns index of token after
    the matching list_close. Supports nesting.
    """
    open_token = tokens[i]
    ordered = open_token.type == "ordered_list_open"
    close_type = "ordered_list_close" if ordered else "bullet_list_close"

    # Detect checkbox list: scan top-level items only (nested lists' items don't
    # count). Track depth to skip over nested list tokens.
    is_checkbox = False
    j = i + 1
    nested = 0
    while j < len(tokens):
        t = tokens[j].type
        if t == close_type and nested == 0:
            break
        if t in ("bullet_list_open", "ordered_list_open"):
            nested += 1
        elif t in ("bullet_list_close", "ordered_list_close"):
            nested -= 1
        if nested == 0 and t == "list_item_open":
            # Find the FIRST inline within this item (not within nested lists)
            k = j + 1
            inner_nested = 0
            while k < len(tokens):
                tt = tokens[k].type
                if tt == "list_item_close" and inner_nested == 0:
                    break
                if tt in ("bullet_list_open", "ordered_list_open"):
                    inner_nested += 1
                elif tt in ("bullet_list_close", "ordered_list_close"):
                    inner_nested -= 1
                if inner_nested == 0 and tt == "inline" and _is_checkbox_item(tokens[k]):
                    is_checkbox = True
                    break
                k += 1
            if is_checkbox:
                break
        j += 1

    preset_key = "checkbox" if is_checkbox else ("ordered" if ordered else "bullet")
    preset = _BULLET_PRESETS[preset_key]

    # Track requests added during this list so we can count tabs consumed by
    # createParagraphBullets and adjust the cursor accordingly. Only the
    # outermost (depth=0) call emits the bullet request and the adjustment.
    requests_start = len(state.requests) if depth == 0 else None

    list_start = state.cursor

    j = i + 1
    while j < len(tokens) and tokens[j].type != close_type:
        if tokens[j].type == "list_item_open":
            # Process item: it contains paragraph(s) and possibly nested lists
            k = j + 1
            indent = "\t" * depth
            while k < len(tokens) and tokens[k].type != "list_item_close":
                if tokens[k].type == "paragraph_open":
                    inline = tokens[k + 1]
                    if is_checkbox:
                        _strip_checkbox_marker(inline)
                    # Insert indent, then inline content (which includes its own \n)
                    if indent:
                        state.insert_text(indent)
                    _render_inline(state, inline)
                    # NOTE: _render_inline already appends \n; no separate insert_text("\n") needed
                    k += 3
                elif tokens[k].type in ("bullet_list_open", "ordered_list_open"):
                    k = _handle_list(state, tokens, k, depth=depth + 1)
                else:
                    k += 1
            j = k + 1  # skip list_item_close
        else:
            j += 1

    list_end = state.cursor

    # Apply bullets to the full list range — but only at the top depth.
    # Nested items are differentiated by their \t prefixes per Docs API convention.
    if depth == 0 and list_end > list_start:
        state.requests.append({
            "createParagraphBullets": {
                "range": {"startIndex": list_start, "endIndex": list_end},
                "bulletPreset": preset,
            }
        })
        # createParagraphBullets CONSUMES the leading whitespace (\t chars) of
        # each paragraph in the range — uses it to compute nesting level, then
        # strips it from content. The document shrinks by the total consumed
        # whitespace, so the cursor needs to track the post-shrink state for
        # subsequent inserts.
        consumed = sum(
            u16len(r["insertText"]["text"])
            for r in state.requests[requests_start:]
            if "insertText" in r
            and r["insertText"]["text"]
            and all(ch == "\t" for ch in r["insertText"]["text"])
        )
        if consumed:
            state.cursor -= consumed

    return j + 1  # skip list_close


# OptionalColor shape: {"color": {"rgbColor": {...}}} — full wrapper required by Docs API.
_CODE_BG = {"color": {"rgbColor": {"red": 0.953, "green": 0.953, "blue": 0.953}}}  # #f3f3f3


def _handle_code_block(state: _State, tokens: list[Token], i: int) -> int:
    """Fenced code block (token type 'fence') or indented ('code_block')."""
    tok = tokens[i]
    code = tok.content
    if not code.endswith("\n"):
        code += "\n"
    start, end = state.insert_text(code)
    state.style_text(
        start, end,
        {"weightedFontFamily": {"fontFamily": "Roboto Mono"}},
        "weightedFontFamily",
    )
    state.style_paragraph(
        start, end,
        {
            "shading": {"backgroundColor": _CODE_BG},
            "indentStart": {"magnitude": 10, "unit": "PT"},
            "indentEnd": {"magnitude": 10, "unit": "PT"},
        },
        "shading.backgroundColor,indentStart,indentEnd",
    )
    return i + 1


def _handle_blockquote(state: _State, tokens: list[Token], i: int) -> int:
    """Tokens: blockquote_open, ... (may contain paragraphs), blockquote_close."""
    quote_start = state.cursor
    j = i + 1
    while j < len(tokens) and tokens[j].type != "blockquote_close":
        if tokens[j].type == "paragraph_open":
            inline = tokens[j + 1]
            # _render_inline includes trailing \n; don't double-add
            _render_inline(state, inline)
            j += 3
        else:
            j += 1
    quote_end = state.cursor
    if quote_end > quote_start:
        state.style_paragraph(
            quote_start, quote_end,
            {
                "indentStart": {"magnitude": 18, "unit": "PT"},
                "borderLeft": {
                    "color": {"color": {"rgbColor": {"red": 0.7, "green": 0.7, "blue": 0.7}}},
                    "width": {"magnitude": 3, "unit": "PT"},
                    "padding": {"magnitude": 8, "unit": "PT"},
                    "dashStyle": "SOLID",
                },
            },
            "indentStart,borderLeft",
        )
    return j + 1


def _handle_hr(state: _State, tokens: list[Token], i: int) -> int:
    """Horizontal rule: insert an empty paragraph with a bottom border."""
    start, end = state.insert_text("\n")
    state.style_paragraph(
        start, end,
        {
            "borderBottom": {
                "color": {"color": {"rgbColor": {"red": 0.7, "green": 0.7, "blue": 0.7}}},
                "width": {"magnitude": 1, "unit": "PT"},
                "padding": {"magnitude": 1, "unit": "PT"},
                "dashStyle": "SOLID",
            }
        },
        "borderBottom",
    )
    return i + 1


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


def _handle_table(state: _State, tokens: list[Token], i: int) -> int:
    """
    GFM table. Tokens: table_open, thead_open, tr_open, th_open*, th_close,
    tr_close, thead_close, tbody_open, (tr_open, td_open*, td_close, tr_close)*,
    tbody_close, table_close.

    Emits insertTable + a _pending_table sentinel to be processed after re-reading
    the doc to learn cell indices.
    """
    cells: list[dict] = []
    rows = 0
    cols = 0

    j = i + 1
    current_row_cells = 0
    in_header = False
    while j < len(tokens) and tokens[j].type != "table_close":
        t = tokens[j].type
        if t == "thead_open":
            in_header = True
        elif t == "thead_close":
            in_header = False
        elif t == "tr_open":
            current_row_cells = 0
        elif t == "tr_close":
            if rows == 0:
                cols = current_row_cells
            rows += 1
        elif t in ("th_open", "td_open"):
            # Find the inline token within this cell
            k = j + 1
            while tokens[k].type != "inline":
                k += 1
            cell_text = tokens[k].content
            cells.append({
                "text": cell_text,
                "row": rows,
                "col": current_row_cells,
                "header": in_header,
            })
            current_row_cells += 1
            # Advance j to the matching th_close / td_close
            close_token = "th_close" if t == "th_open" else "td_close"
            while tokens[j].type != close_token:
                j += 1
        j += 1

    table_insert_index = state.cursor
    state.requests.append({
        "insertTable": {
            "location": {"index": table_insert_index},
            "rows": rows,
            "columns": cols,
        }
    })
    state.requests.append({
        "_pending_table": {
            "insert_index": table_insert_index,
            "rows": rows,
            "cols": cols,
            "cells": cells,
            "header_row": 0,
        }
    })
    # Approximate cursor advance. Post-processor re-reads exact indices,
    # so this only matters if more markdown content follows the table in
    # the same transformer call.
    state.cursor += 1 + rows * cols * 2 + 1

    return j + 1


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
        elif tok.type in ("bullet_list_open", "ordered_list_open"):
            i = _handle_list(state, tokens, i)
        elif tok.type in ("fence", "code_block"):
            i = _handle_code_block(state, tokens, i)
        elif tok.type == "blockquote_open":
            i = _handle_blockquote(state, tokens, i)
        elif tok.type == "hr":
            i = _handle_hr(state, tokens, i)
        elif tok.type == "table_open":
            i = _handle_table(state, tokens, i)
        else:
            logger.debug("Skipping unhandled token: %s", tok.type)
            i += 1

    return state.requests


def render_markdown_to_doc(service: Any, document_id: str, markdown: str,
                           insert_index: int = 1) -> dict:
    """
    Build requests + send batchUpdates, handling tables in a second pass.

    Tables require special handling because the Docs API allocates cell indices
    on insertion (we can't predict them) AND the actual byte-width of the table
    differs from our approximation in `_handle_table`. So:

      1. Flush all requests up to and including the `insertTable` (one batch).
      2. Re-read the doc, build cell-fill requests using real cell indices,
         and compute the shift between approximated and real post-table cursor.
      3. Apply that shift to ALL remaining queued requests so their indices
         line up with the real doc state.
      4. Continue.
    """
    requests = markdown_to_requests(markdown, insert_index=insert_index)
    if not requests:
        return {"replies": [], "documentId": document_id}

    # Fast path: no tables → single atomic batch.
    if not any("_pending_table" in r for r in requests):
        return service.documents().batchUpdate(
            documentId=document_id, body={"requests": requests}
        ).execute()

    response: dict = {"replies": [], "documentId": document_id}
    pending: list[dict] = []
    i = 0
    while i < len(requests):
        req = requests[i]
        if "_pending_table" in req:
            # Flush real requests so far (includes the insertTable that precedes this sentinel)
            if pending:
                r = service.documents().batchUpdate(
                    documentId=document_id, body={"requests": pending}
                ).execute()
                response["replies"].extend(r.get("replies", []))
                pending = []

            # Re-read doc to find the just-inserted table's real position
            doc = service.documents().get(documentId=document_id).execute()
            cell_requests = _build_cell_fill_requests(doc, req["_pending_table"])
            if cell_requests:
                r = service.documents().batchUpdate(
                    documentId=document_id, body={"requests": cell_requests}
                ).execute()
                response["replies"].extend(r.get("replies", []))
                # Filling the cells grew the table. Read it again, or the
                # post-table index below describes the empty table and every
                # later request lands inside a cell.
                doc = service.documents().get(documentId=document_id).execute()

            # Compute index shift: actual post-table index vs approximation.
            real_post_table = _find_post_table_end_index(doc, req["_pending_table"])
            pt = req["_pending_table"]
            approximated_post_table = pt["insert_index"] + 1 + pt["rows"] * pt["cols"] * 2 + 1
            shift = real_post_table - approximated_post_table
            if shift != 0 and i + 1 < len(requests):
                _shift_indices(requests[i + 1:], shift)
        else:
            pending.append(req)
        i += 1

    if pending:
        r = service.documents().batchUpdate(
            documentId=document_id, body={"requests": pending}
        ).execute()
        response["replies"].extend(r.get("replies", []))

    return response


def _find_post_table_end_index(doc: dict, pending: dict) -> int:
    """Return the actual endIndex of the just-inserted table (i.e., where
    content after the table now begins)."""
    insert_index = pending["insert_index"]
    for element in doc.get("body", {}).get("content", []):
        if element.get("startIndex") == insert_index and "table" in element:
            return element["endIndex"]
    # Fallback: take the last table in the document.
    for element in reversed(doc.get("body", {}).get("content", [])):
        if "table" in element:
            return element["endIndex"]
    return insert_index + 1


def _shift_indices(requests: list[dict], shift: int) -> None:
    """In-place: shift any `index`/`startIndex`/`endIndex`/`insert_index` field
    by `shift`, recursively. Used to keep post-table requests aligned with real
    doc state after a table insertion completes.

    `insert_index` belongs to our own `_pending_table` sentinel rather than to
    the Docs API. It has to move with everything else: a later table's sentinel
    is what the shift for THAT table is measured against, and leaving it behind
    makes every following table drift further."""
    _INDEX_KEYS = ("index", "startIndex", "endIndex", "insert_index")

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in _INDEX_KEYS and isinstance(v, int):
                    obj[k] = v + shift
                else:
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    for req in requests:
        walk(req)


def _build_cell_fill_requests(doc: dict, pending: dict) -> list[dict]:
    """
    Find the table at pending['insert_index'] in `doc`, then build insertText
    requests for each cell PLUS bold styling for the header row.
    """
    table = None
    for element in doc.get("body", {}).get("content", []):
        if element.get("startIndex") == pending["insert_index"] and "table" in element:
            table = element["table"]
            break
    if table is None:
        # Fallback: take the last table in the document.
        for element in reversed(doc.get("body", {}).get("content", [])):
            if "table" in element:
                table = element["table"]
                break
    if table is None:
        return []

    # Build cell index map [row][col] -> first content index inside the cell
    cell_first_index: list[list[int]] = []
    for row in table.get("tableRows", []):
        row_indices = []
        for cell in row.get("tableCells", []):
            first = cell.get("content", [{}])[0]
            row_indices.append(first.get("startIndex", cell.get("startIndex", 0) + 1))
        cell_first_index.append(row_indices)

    requests = []
    # Insert text into each cell IN REVERSE ORDER (so earlier inserts don't
    # shift later indices). Reverse over rows AND columns.
    sorted_cells = sorted(pending["cells"], key=lambda c: (c["row"], c["col"]), reverse=True)
    for c in sorted_cells:
        idx = cell_first_index[c["row"]][c["col"]]
        if c["text"]:
            requests.append({
                "insertText": {"location": {"index": idx}, "text": c["text"]},
            })

    # Style header row: bold. These run after every insert above, in the same
    # batch, so each header cell has already been pushed right by the text put
    # into the cells that precede it. Without that offset the bold range lands
    # on the wrong run.
    if pending["cells"]:
        filled = [
            (cell_first_index[c["row"]][c["col"]], u16len(c["text"]))
            for c in pending["cells"] if c["text"]
        ]
        for c in pending["cells"]:
            if c["row"] != pending["header_row"] or not c["text"]:
                continue
            idx = cell_first_index[c["row"]][c["col"]]
            start = idx + sum(length for at, length in filled if at < idx)
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": start, "endIndex": start + u16len(c["text"])},
                    "textStyle": {"bold": True},
                    "fields": "bold",
                }
            })

    return requests
