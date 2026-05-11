"""Text and paragraph styling tools."""

import logging
from typing import Optional

from app import mcp
from ._common import docs, parse_color, pt, tool_errors

logger = logging.getLogger(__name__)


@mcp.tool()
@tool_errors
def apply_text_style(
    document_id: str,
    start_index: int,
    end_index: int,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    underline: Optional[bool] = None,
    strikethrough: Optional[bool] = None,
    font_family: Optional[str] = None,
    font_size_pt: Optional[float] = None,
    foreground_color: Optional[str] = None,
    background_color: Optional[str] = None,
    link_url: Optional[str] = None,
) -> dict:
    """
    Apply text styling to a range. Only the parameters you pass are changed;
    others are left untouched.

    Range indices come from `read_doc(format='json')`.

    Args:
        document_id: The Google Docs document ID.
        start_index, end_index: Range to style.
        bold/italic/underline/strikethrough: Toggle these styles.
        font_family: e.g. "Roboto", "Roboto Mono", "Georgia", "Calibri".
        font_size_pt: Font size in points (e.g. 12, 18).
        foreground_color, background_color: "#rrggbb", "#rgb", or named color.
        link_url: Set as a hyperlink. Pass empty string "" to remove.
    """
    style: dict = {}
    fields: list[str] = []

    if bold is not None:
        style["bold"] = bold
        fields.append("bold")
    if italic is not None:
        style["italic"] = italic
        fields.append("italic")
    if underline is not None:
        style["underline"] = underline
        fields.append("underline")
    if strikethrough is not None:
        style["strikethrough"] = strikethrough
        fields.append("strikethrough")
    if font_family is not None:
        style["weightedFontFamily"] = {"fontFamily": font_family}
        fields.append("weightedFontFamily")
    if font_size_pt is not None:
        style["fontSize"] = pt(font_size_pt)
        fields.append("fontSize")
    if foreground_color is not None:
        style["foregroundColor"] = {"color": {"rgbColor": parse_color(foreground_color)}}
        fields.append("foregroundColor")
    if background_color is not None:
        style["backgroundColor"] = {"color": {"rgbColor": parse_color(background_color)}}
        fields.append("backgroundColor")
    if link_url is not None:
        style["link"] = {"url": link_url} if link_url else {}
        fields.append("link")

    if not fields:
        return {"id": document_id, "status": "No style changes specified."}

    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"updateTextStyle": {
            "range": {"startIndex": start_index, "endIndex": end_index},
            "textStyle": style,
            "fields": ",".join(fields),
        }}]},
    ).execute()
    return {"id": document_id, "status": f"Applied text style to range {start_index}–{end_index}."}
