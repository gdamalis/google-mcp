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


@mcp.tool()
@tool_errors
def update_section_columns(
    document_id: str,
    section_start_index: int,
    column_count: int,
    separator: bool = False,
) -> dict:
    """
    Set the column count for a section.

    A section's start is at a section break (or document start). Use
    `read_doc(format='json')` to find sectionBreak elements and their indices.

    Args:
        section_start_index: Index of the section break that begins the section
                             (or 0 for the first section).
        column_count: Number of columns (1, 2, 3, ...).
        separator: Draw a vertical line between columns.
    """
    if column_count < 1:
        raise ValueError("column_count must be >= 1")

    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"updateSectionStyle": {
            "range": {"startIndex": section_start_index, "endIndex": section_start_index + 1},
            "sectionStyle": {
                "columnProperties": [{} for _ in range(column_count)],
                "columnSeparatorStyle": "BETWEEN_EACH_COLUMN" if separator else "NONE",
            },
            "fields": "columnProperties,columnSeparatorStyle",
        }}]},
    ).execute()
    return {"id": document_id, "status": f"Section at {section_start_index} set to {column_count} columns."}


@mcp.tool()
@tool_errors
def update_page_setup(
    document_id: str,
    top_margin_pt: Optional[float] = None,
    bottom_margin_pt: Optional[float] = None,
    left_margin_pt: Optional[float] = None,
    right_margin_pt: Optional[float] = None,
    page_width_pt: Optional[float] = None,
    page_height_pt: Optional[float] = None,
    orientation: Optional[str] = None,
) -> dict:
    """
    Update document-wide page setup.

    Args:
        margins: in points (72pt = 1 inch).
        page_width_pt, page_height_pt: e.g. Letter = 612x792, A4 = 595x842.
        orientation: "portrait" or "landscape". If set, swaps width/height
                     as needed (uses Letter dimensions if width/height not given).
    """
    style: dict = {}
    fields: list[str] = []

    if top_margin_pt is not None:
        style["marginTop"] = pt(top_margin_pt)
        fields.append("marginTop")
    if bottom_margin_pt is not None:
        style["marginBottom"] = pt(bottom_margin_pt)
        fields.append("marginBottom")
    if left_margin_pt is not None:
        style["marginLeft"] = pt(left_margin_pt)
        fields.append("marginLeft")
    if right_margin_pt is not None:
        style["marginRight"] = pt(right_margin_pt)
        fields.append("marginRight")

    if orientation is not None:
        if orientation not in ("portrait", "landscape"):
            raise ValueError("orientation must be 'portrait' or 'landscape'")
        w, h = page_width_pt or 612, page_height_pt or 792
        if orientation == "landscape" and w < h:
            w, h = h, w
        elif orientation == "portrait" and w > h:
            w, h = h, w
        style["pageSize"] = {"width": pt(w), "height": pt(h)}
        fields.append("pageSize")
    elif page_width_pt is not None or page_height_pt is not None:
        style["pageSize"] = {
            "width": pt(page_width_pt or 612),
            "height": pt(page_height_pt or 792),
        }
        fields.append("pageSize")

    if not fields:
        return {"id": document_id, "status": "No page setup changes specified."}

    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"updateDocumentStyle": {
            "documentStyle": style,
            "fields": ",".join(fields),
        }}]},
    ).execute()
    return {"id": document_id, "status": "Page setup updated."}


@mcp.tool()
@tool_errors
def update_header_footer(
    document_id: str,
    header_markdown: Optional[str] = None,
    footer_markdown: Optional[str] = None,
    include_page_numbers: bool = False,
    first_page_different: bool = False,
) -> dict:
    """
    Set the document header and/or footer.

    Note: The Docs API does NOT support inserting auto-updating page numbers.
    When `include_page_numbers=True`, the literal text " Page " is appended
    to the footer (or header if no footer_markdown) as a placeholder. To get
    a live page number, the user must add it via Insert > Page Number in the
    Google Docs UI after this call.

    Args:
        header_markdown: Plain text or simple markdown for the header.
                         Full markdown rendering inside headers is limited by
                         the Docs API; complex markdown may not work.
        footer_markdown: Same for footer.
        include_page_numbers: Adds " Page " text placeholder.
        first_page_different: First page has its own header/footer.
    """
    service = docs()

    if first_page_different:
        service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"updateDocumentStyle": {
                "documentStyle": {"useFirstPageHeaderFooter": True},
                "fields": "useFirstPageHeaderFooter",
            }}]},
        ).execute()

    doc = service.documents().get(documentId=document_id).execute()
    header_id = doc.get("documentStyle", {}).get("defaultHeaderId")
    footer_id = doc.get("documentStyle", {}).get("defaultFooterId")

    if header_markdown is not None and header_id is None:
        r = service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"createHeader": {"type": "DEFAULT"}}]},
        ).execute()
        header_id = r["replies"][0]["createHeader"]["headerId"]

    if (footer_markdown is not None or include_page_numbers) and footer_id is None:
        r = service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"createFooter": {"type": "DEFAULT"}}]},
        ).execute()
        footer_id = r["replies"][0]["createFooter"]["footerId"]

    def _fill_segment(segment_id: str, markdown: str, *, with_page_number: bool = False) -> None:
        d = service.documents().get(documentId=document_id).execute()
        segments = d.get("headers", {}) if segment_id == header_id else d.get("footers", {})
        seg = segments.get(segment_id)
        if not seg:
            return
        content = seg.get("content", [])
        if content:
            seg_end = content[-1]["endIndex"]
            if seg_end > 1:
                service.documents().batchUpdate(
                    documentId=document_id,
                    body={"requests": [{"deleteContentRange": {
                        "range": {
                            "segmentId": segment_id,
                            "startIndex": 0,
                            "endIndex": seg_end - 1,
                        },
                    }}]},
                ).execute()
        if markdown:
            service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{"insertText": {
                    "location": {"segmentId": segment_id, "index": 0},
                    "text": markdown,
                }}]},
            ).execute()
        if with_page_number:
            d = service.documents().get(documentId=document_id).execute()
            segments = d.get("headers", {}) if segment_id == header_id else d.get("footers", {})
            seg = segments.get(segment_id, {})
            content = seg.get("content", [])
            end = content[-1]["endIndex"] - 1 if content else 0
            service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [
                    {"insertText": {
                        "location": {"segmentId": segment_id, "index": end},
                        "text": " Page ",
                    }},
                ]},
            ).execute()

    if header_markdown is not None and header_id:
        _fill_segment(header_id, header_markdown)
    if (footer_markdown is not None or include_page_numbers) and footer_id:
        _fill_segment(footer_id, footer_markdown or "", with_page_number=include_page_numbers)

    return {"id": document_id, "status": "Header/footer updated."}
