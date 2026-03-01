"""
Google Drive tools — folder browsing and file search.
"""

import logging
from typing import Optional

from googleapiclient.errors import HttpError

from app import mcp
from auth import get_service

logger = logging.getLogger(__name__)


def _drive():
    return get_service("drive", "v3")


# Mapping of common MIME types to human-readable names
_MIME_LABELS = {
    "application/vnd.google-apps.folder": "folder",
    "application/vnd.google-apps.document": "Google Doc",
    "application/vnd.google-apps.spreadsheet": "Google Sheet",
    "application/vnd.google-apps.presentation": "Google Slides",
    "application/vnd.google-apps.form": "Google Form",
    "application/pdf": "PDF",
    "image/png": "PNG image",
    "image/jpeg": "JPEG image",
    "video/mp4": "MP4 video",
}


def _format_file(f: dict) -> dict:
    """Format a Drive file entry for display."""
    mime = f.get("mimeType", "")
    return {
        "id": f["id"],
        "name": f["name"],
        "type": _MIME_LABELS.get(mime, mime),
        "mime_type": mime,
        "modified": f.get("modifiedTime", ""),
        "size": f.get("size", ""),
        "owner": (
            f.get("owners", [{}])[0].get("emailAddress", "")
            if f.get("owners")
            else ""
        ),
        "link": f.get("webViewLink", ""),
    }


@mcp.tool()
def list_folder(
    folder_id: str = "root",
    max_results: int = 50,
) -> list[dict]:
    """
    List files and subfolders in a Google Drive folder.

    Args:
        folder_id: The folder ID to browse (default 'root' for My Drive root).
                   Use a folder ID from search results or previous list_folder calls.
        max_results: Maximum items to return (default 50)
    """
    try:
        service = _drive()
        response = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            spaces="drive",
            fields="files(id, name, mimeType, modifiedTime, size, owners, webViewLink)",
            pageSize=min(max_results, 100),
            orderBy="folder,name",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        ).execute()

        return [_format_file(f) for f in response.get("files", [])]
    except HttpError as e:
        return [{"error": f"Drive API error {e.status_code}: {e.reason}"}]


@mcp.tool()
def search_drive(
    query: str,
    file_type: Optional[str] = None,
    max_results: int = 20,
) -> list[dict]:
    """
    Search Google Drive for any file type by name or content.

    Unlike search_docs/search_sheets, this searches ALL file types
    including PDFs, images, slides, folders, etc.

    Args:
        query: Search query (matches file name and content)
        file_type: Optional filter — 'folder', 'document', 'spreadsheet',
                   'presentation', 'pdf', 'image', or any MIME type
        max_results: Maximum results to return (default 20)
    """
    try:
        service = _drive()

        q_parts = [f"fullText contains '{query}'", "trashed = false"]

        type_map = {
            "folder": "application/vnd.google-apps.folder",
            "document": "application/vnd.google-apps.document",
            "spreadsheet": "application/vnd.google-apps.spreadsheet",
            "presentation": "application/vnd.google-apps.presentation",
            "form": "application/vnd.google-apps.form",
            "pdf": "application/pdf",
            "image": "image/",
        }

        if file_type:
            mime = type_map.get(file_type, file_type)
            if mime.endswith("/"):
                q_parts.append(f"mimeType contains '{mime}'")
            else:
                q_parts.append(f"mimeType = '{mime}'")

        response = service.files().list(
            q=" and ".join(q_parts),
            spaces="drive",
            fields="files(id, name, mimeType, modifiedTime, size, owners, webViewLink)",
            pageSize=min(max_results, 100),
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        ).execute()

        return [_format_file(f) for f in response.get("files", [])]
    except HttpError as e:
        return [{"error": f"Drive API error {e.status_code}: {e.reason}"}]


@mcp.tool()
def find_folder(name: str, max_results: int = 10) -> list[dict]:
    """
    Find a folder by name in Google Drive (including shared drives).

    Returns matching folders with their IDs, which can be used
    with list_folder to browse contents.

    Args:
        name: Folder name to search for
        max_results: Maximum results to return (default 10)
    """
    try:
        service = _drive()
        response = service.files().list(
            q=f"mimeType = 'application/vnd.google-apps.folder' and name contains '{name}' and trashed = false",
            spaces="drive",
            fields="files(id, name, mimeType, modifiedTime, owners, webViewLink)",
            pageSize=min(max_results, 50),
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        ).execute()

        return [_format_file(f) for f in response.get("files", [])]
    except HttpError as e:
        return [{"error": f"Drive API error {e.status_code}: {e.reason}"}]
