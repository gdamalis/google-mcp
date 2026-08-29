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


_NAMED_STYLES = {
    "TITLE", "SUBTITLE",
    "HEADING_1", "HEADING_2", "HEADING_3",
    "HEADING_4", "HEADING_5", "HEADING_6",
    "NORMAL_TEXT",
}
_ALIGNMENTS = {"START", "CENTER", "END", "JUSTIFIED"}


@mcp.tool()
@tool_errors
def apply_paragraph_style(
    document_id: str,
    start_index: int,
    end_index: int,
    named_style: Optional[str] = None,
    alignment: Optional[str] = None,
    line_spacing: Optional[float] = None,
    indent_first_line_pt: Optional[float] = None,
    indent_start_pt: Optional[float] = None,
    space_above_pt: Optional[float] = None,
    space_below_pt: Optional[float] = None,
    keep_with_next: Optional[bool] = None,
) -> dict:
    """
    Apply paragraph styling to a range.

    Args:
        named_style: One of TITLE, SUBTITLE, HEADING_1..6, NORMAL_TEXT.
                     Applies Google Docs' built-in named style — best for
                     ensuring a polished, consistent visual hierarchy.
        alignment: START | CENTER | END | JUSTIFIED.
        line_spacing: Multiplier. 1.0=single, 1.15, 1.5, 2.0 typical.
        indent_first_line_pt, indent_start_pt: Indentation in points.
        space_above_pt, space_below_pt: Paragraph spacing in points.
        keep_with_next: Prevent page break between this paragraph and the next.
    """
    style: dict = {}
    fields: list[str] = []

    if named_style is not None:
        if named_style not in _NAMED_STYLES:
            raise ValueError(f"named_style must be one of {sorted(_NAMED_STYLES)}; got {named_style!r}")
        style["namedStyleType"] = named_style
        fields.append("namedStyleType")
    if alignment is not None:
        if alignment not in _ALIGNMENTS:
            raise ValueError(f"alignment must be one of {sorted(_ALIGNMENTS)}; got {alignment!r}")
        style["alignment"] = alignment
        fields.append("alignment")
    if line_spacing is not None:
        # Docs API expects percentage: 1.5x = 150
        style["lineSpacing"] = float(line_spacing) * 100
        fields.append("lineSpacing")
    if indent_first_line_pt is not None:
        style["indentFirstLine"] = pt(indent_first_line_pt)
        fields.append("indentFirstLine")
    if indent_start_pt is not None:
        style["indentStart"] = pt(indent_start_pt)
        fields.append("indentStart")
    if space_above_pt is not None:
        style["spaceAbove"] = pt(space_above_pt)
        fields.append("spaceAbove")
    if space_below_pt is not None:
        style["spaceBelow"] = pt(space_below_pt)
        fields.append("spaceBelow")
    if keep_with_next is not None:
        style["keepWithNext"] = keep_with_next
        fields.append("keepWithNext")

    if not fields:
        return {"id": document_id, "status": "No style changes specified."}

    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"updateParagraphStyle": {
            "range": {"startIndex": start_index, "endIndex": end_index},
            "paragraphStyle": style,
            "fields": ",".join(fields),
        }}]},
    ).execute()
    return {"id": document_id, "status": f"Applied paragraph style to range {start_index}–{end_index}."}
