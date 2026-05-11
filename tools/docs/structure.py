"""Structural tools — page breaks, sections, headers/footers, page setup."""

import logging
from typing import Optional

from app import mcp
from ._common import docs, parse_color, pt, tool_errors

logger = logging.getLogger(__name__)


@mcp.tool()
@tool_errors
def insert_page_break(document_id: str, index: int) -> dict:
    """Insert a page break at the given index."""
    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"insertPageBreak": {"location": {"index": index}}}]},
    ).execute()
    return {"id": document_id, "status": f"Page break at {index}."}


@mcp.tool()
@tool_errors
def insert_horizontal_rule(document_id: str, index: int) -> dict:
    """
    Insert a horizontal rule (divider line) at the given index.

    Implemented as a paragraph with a bottom border, since the Docs API has
    no native horizontal-rule request.
    """
    requests = [
        {"insertText": {"location": {"index": index}, "text": "\n"}},
        {"updateParagraphStyle": {
            "range": {"startIndex": index, "endIndex": index + 1},
            "paragraphStyle": {
                "borderBottom": {
                    "color": {"color": {"rgbColor": {"red": 0.7, "green": 0.7, "blue": 0.7}}},
                    "width": {"magnitude": 1, "unit": "PT"},
                    "padding": {"magnitude": 1, "unit": "PT"},
                    "dashStyle": "SOLID",
                }
            },
            "fields": "borderBottom",
        }},
    ]
    docs().documents().batchUpdate(
        documentId=document_id, body={"requests": requests}
    ).execute()
    return {"id": document_id, "status": f"Horizontal rule at {index}."}


@mcp.tool()
@tool_errors
def insert_section_break(
    document_id: str,
    index: int,
    type: str = "NEXT_PAGE",
) -> dict:
    """
    Insert a section break. Sections allow varying margins, columns, page
    orientation per region.

    Args:
        type: "NEXT_PAGE" (default — starts a new page) or "CONTINUOUS".
    """
    if type not in ("NEXT_PAGE", "CONTINUOUS"):
        raise ValueError(f"type must be NEXT_PAGE or CONTINUOUS; got {type!r}")
    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"insertSectionBreak": {
            "location": {"index": index},
            "sectionType": type,
        }}]},
    ).execute()
    return {"id": document_id, "status": f"{type} section break at {index}."}
