"""
Google Sheets tools — search, read, write, and create spreadsheets.
"""

import logging
from typing import Optional

from googleapiclient.errors import HttpError

from app import mcp
from auth import get_service

logger = logging.getLogger(__name__)


def _sheets():
    return get_service("sheets", "v4")


def _drive():
    return get_service("drive", "v3")


@mcp.tool()
def search_sheets(query: str, max_results: int = 20) -> list[dict]:
    """
    Search Google Drive for spreadsheets by name or content.

    Args:
        query: Search query (matches spreadsheet name and content)
        max_results: Maximum results to return (default 20)
    """
    try:
        service = _drive()
        response = service.files().list(
            q=f"mimeType='application/vnd.google-apps.spreadsheet' and fullText contains '{query}'",
            spaces="drive",
            fields="files(id, name, modifiedTime, owners, webViewLink)",
            pageSize=min(max_results, 100),
        ).execute()

        files = response.get("files", [])
        return [
            {
                "id": f["id"],
                "name": f["name"],
                "modified": f.get("modifiedTime", ""),
                "owner": f.get("owners", [{}])[0].get("emailAddress", "") if f.get("owners") else "",
                "link": f.get("webViewLink", ""),
            }
            for f in files
        ]
    except HttpError as e:
        return [{"error": f"Drive API error {e.status_code}: {e.reason}"}]


@mcp.tool()
def read_sheet(spreadsheet_id: str, range: str) -> dict:
    """
    Read cell values from a Google Sheets spreadsheet.

    Args:
        spreadsheet_id: The spreadsheet ID
        range: Cell range in A1 notation (e.g. 'Sheet1!A1:D10', 'A1:C5')
    """
    try:
        service = _sheets()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range
        ).execute()

        return {
            "spreadsheet_id": spreadsheet_id,
            "range": result.get("range", range),
            "values": result.get("values", []),
            "rows": len(result.get("values", [])),
        }
    except HttpError as e:
        return {"error": f"Sheets API error {e.status_code}: {e.reason}"}


@mcp.tool()
def write_sheet(
    spreadsheet_id: str,
    range: str,
    values: list[list],
) -> dict:
    """
    Write values to cells in a Google Sheets spreadsheet.

    Overwrites existing data in the specified range.

    Args:
        spreadsheet_id: The spreadsheet ID
        range: Target cell range in A1 notation (e.g. 'Sheet1!A1:C3')
        values: 2D array of values (list of rows, each row is a list of cell values)
    """
    try:
        service = _sheets()
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

        return {
            "spreadsheet_id": spreadsheet_id,
            "updated_range": result.get("updatedRange", ""),
            "updated_rows": result.get("updatedRows", 0),
            "updated_columns": result.get("updatedColumns", 0),
            "updated_cells": result.get("updatedCells", 0),
            "status": "Cells updated successfully.",
        }
    except HttpError as e:
        return {"error": f"Sheets API error {e.status_code}: {e.reason}"}


@mcp.tool()
def append_to_sheet(
    spreadsheet_id: str,
    range: str,
    values: list[list],
) -> dict:
    """
    Append rows after existing data in a Google Sheets spreadsheet.

    The range determines which table to append to. Data is added after
    the last row with content in that range.

    Args:
        spreadsheet_id: The spreadsheet ID
        range: Table range in A1 notation (e.g. 'Sheet1!A:D')
        values: 2D array of rows to append
    """
    try:
        service = _sheets()
        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()

        updates = result.get("updates", {})
        return {
            "spreadsheet_id": spreadsheet_id,
            "updated_range": updates.get("updatedRange", ""),
            "updated_rows": updates.get("updatedRows", 0),
            "updated_cells": updates.get("updatedCells", 0),
            "status": "Rows appended successfully.",
        }
    except HttpError as e:
        return {"error": f"Sheets API error {e.status_code}: {e.reason}"}


@mcp.tool()
def create_spreadsheet(
    title: str,
    sheet_names: Optional[list[str]] = None,
) -> dict:
    """
    Create a new Google Sheets spreadsheet.

    Args:
        title: Spreadsheet title
        sheet_names: Optional list of sheet/tab names (default: one sheet named 'Sheet1')
    """
    try:
        service = _sheets()
        body: dict = {"properties": {"title": title}}

        if sheet_names:
            body["sheets"] = [
                {"properties": {"title": name}} for name in sheet_names
            ]

        result = service.spreadsheets().create(body=body).execute()

        return {
            "id": result["spreadsheetId"],
            "title": result["properties"]["title"],
            "sheets": [s["properties"]["title"] for s in result.get("sheets", [])],
            "link": result.get("spreadsheetUrl", ""),
            "status": "Spreadsheet created successfully.",
        }
    except HttpError as e:
        return {"error": f"Sheets API error {e.status_code}: {e.reason}"}


@mcp.tool()
def list_sheet_names(spreadsheet_id: str) -> dict:
    """
    List all sheet/tab names in a Google Sheets spreadsheet.

    Args:
        spreadsheet_id: The spreadsheet ID
    """
    try:
        service = _sheets()
        result = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="spreadsheetId,properties.title,sheets.properties",
        ).execute()

        sheets = result.get("sheets", [])
        return {
            "spreadsheet_id": spreadsheet_id,
            "title": result.get("properties", {}).get("title", ""),
            "sheets": [
                {
                    "id": s["properties"]["sheetId"],
                    "name": s["properties"]["title"],
                    "index": s["properties"]["index"],
                    "rows": s["properties"].get("gridProperties", {}).get("rowCount", 0),
                    "columns": s["properties"].get("gridProperties", {}).get("columnCount", 0),
                }
                for s in sheets
            ],
        }
    except HttpError as e:
        return {"error": f"Sheets API error {e.status_code}: {e.reason}"}
