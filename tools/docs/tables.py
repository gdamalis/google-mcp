"""Table styling tools."""

import logging
from typing import Optional

from app import mcp
from ._common import docs, parse_color, pt, tool_errors

logger = logging.getLogger(__name__)


_TEXT_ALIGN = {"START", "CENTER", "END"}
_V_ALIGN = {"TOP", "MIDDLE", "BOTTOM"}


@mcp.tool()
@tool_errors
def style_table_cells(
    document_id: str,
    table_start_index: int,
    row_range: list,                       # [start_row, end_row] inclusive 0-based
    col_range: list,                       # [start_col, end_col] inclusive 0-based
    background_color: Optional[str] = None,
    text_alignment: Optional[str] = None,
    vertical_alignment: Optional[str] = None,
    padding_pt: Optional[float] = None,
    border_color: Optional[str] = None,
    border_width_pt: Optional[float] = None,
) -> dict:
    """
    Apply cell-level styling to a rectangular range within a table.

    Args:
        table_start_index: The Docs index where the table starts (from
                           `read_doc(format='json')`).
        row_range: [start_row, end_row] inclusive, 0-based.
        col_range: [start_col, end_col] inclusive, 0-based.
        background_color: Cell background.
        text_alignment: START / CENTER / END.
        vertical_alignment: TOP / MIDDLE / BOTTOM.
        padding_pt: Cell padding on all sides in points.
        border_color, border_width_pt: Cell border color and width.
                                       Sets all four sides.
    """
    if not (isinstance(row_range, list) and len(row_range) == 2):
        raise ValueError("row_range must be [start_row, end_row]")
    if not (isinstance(col_range, list) and len(col_range) == 2):
        raise ValueError("col_range must be [start_col, end_col]")

    cell_style: dict = {}
    fields: list[str] = []

    if background_color is not None:
        cell_style["backgroundColor"] = {"color": {"rgbColor": parse_color(background_color)}}
        fields.append("backgroundColor")
    if padding_pt is not None:
        p = pt(padding_pt)
        cell_style.update({
            "paddingTop": p, "paddingBottom": p,
            "paddingLeft": p, "paddingRight": p,
        })
        fields.extend(["paddingTop", "paddingBottom", "paddingLeft", "paddingRight"])
    if border_color is not None or border_width_pt is not None:
        border = {
            "color": {"color": {"rgbColor": parse_color(border_color or "#999999")}},
            "width": pt(border_width_pt or 1),
            "dashStyle": "SOLID",
        }
        for side in ("borderTop", "borderBottom", "borderLeft", "borderRight"):
            cell_style[side] = border
            fields.append(side)
    if vertical_alignment is not None:
        if vertical_alignment not in _V_ALIGN:
            raise ValueError(f"vertical_alignment must be one of {sorted(_V_ALIGN)}")
        cell_style["contentAlignment"] = vertical_alignment
        fields.append("contentAlignment")

    requests: list[dict] = []

    if fields:
        requests.append({
            "updateTableCellStyle": {
                "tableRange": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": table_start_index},
                        "rowIndex": row_range[0],
                        "columnIndex": col_range[0],
                    },
                    "rowSpan": row_range[1] - row_range[0] + 1,
                    "columnSpan": col_range[1] - col_range[0] + 1,
                },
                "tableCellStyle": cell_style,
                "fields": ",".join(fields),
            }
        })

    if text_alignment is not None:
        if text_alignment not in _TEXT_ALIGN:
            raise ValueError(f"text_alignment must be one of {sorted(_TEXT_ALIGN)}")
        service = docs()
        doc = service.documents().get(documentId=document_id).execute()
        table = None
        for element in doc.get("body", {}).get("content", []):
            if element.get("startIndex") == table_start_index and "table" in element:
                table = element["table"]
                break
        if table:
            for r in range(row_range[0], row_range[1] + 1):
                for c in range(col_range[0], col_range[1] + 1):
                    cell = table["tableRows"][r]["tableCells"][c]
                    for p in cell.get("content", []):
                        para = p.get("paragraph")
                        if para:
                            start = p["startIndex"]
                            end = p["endIndex"]
                            requests.append({
                                "updateParagraphStyle": {
                                    "range": {"startIndex": start, "endIndex": end},
                                    "paragraphStyle": {"alignment": text_alignment},
                                    "fields": "alignment",
                                }
                            })

    if not requests:
        return {"id": document_id, "status": "No style changes specified."}

    docs().documents().batchUpdate(
        documentId=document_id, body={"requests": requests}
    ).execute()
    return {"id": document_id, "status": "Table cells styled."}


@mcp.tool()
@tool_errors
def merge_table_cells(
    document_id: str,
    table_start_index: int,
    row_start: int,
    col_start: int,
    row_end: int,
    col_end: int,
) -> dict:
    """
    Merge a rectangular block of cells. row_end and col_end are inclusive
    0-based indices.
    """
    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"mergeTableCells": {
            "tableRange": {
                "tableCellLocation": {
                    "tableStartLocation": {"index": table_start_index},
                    "rowIndex": row_start,
                    "columnIndex": col_start,
                },
                "rowSpan": row_end - row_start + 1,
                "columnSpan": col_end - col_start + 1,
            },
        }}]},
    ).execute()
    return {"id": document_id, "status": f"Merged cells ({row_start},{col_start}) to ({row_end},{col_end})."}
