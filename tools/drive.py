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


def move_to_folder(file_id: str, folder_id: str) -> dict:
    """
    Reparent a Drive file, detaching it from every folder it currently sits in.

    Shared helper — not an MCP tool. `create_doc(folder_id=...)` uses it to file
    a freshly created doc, since the Docs API cannot set a parent itself.

    Raises HttpError; callers decide how to report it.
    """
    service = _drive()

    current = service.files().get(
        fileId=file_id,
        fields="parents",
        supportsAllDrives=True,
    ).execute()
    old_parents = current.get("parents", [])

    return service.files().update(
        fileId=file_id,
        addParents=folder_id,
        removeParents=",".join(old_parents) if old_parents else None,
        fields="id, name, parents, webViewLink",
        supportsAllDrives=True,
    ).execute()


@mcp.tool()
def list_shared_drives(max_results: int = 50) -> list[dict]:
    """
    List the shared drives (Unidades compartidas) this account can reach.

    A shared drive's ID doubles as the ID of its root folder, so the value
    returned here is what you pass as `parent_id` to create_folder when you
    want a folder at the top level of that drive.

    Args:
        max_results: Maximum drives to return (default 50)
    """
    try:
        response = _drive().drives().list(
            pageSize=min(max_results, 100),
            fields="drives(id, name, createdTime)",
        ).execute()

        return [
            {
                "id": d["id"],
                "name": d["name"],
                "created": d.get("createdTime", ""),
                "link": f"https://drive.google.com/drive/folders/{d['id']}",
            }
            for d in response.get("drives", [])
        ]
    except HttpError as e:
        return [{"error": f"Drive API error {e.status_code}: {e.reason}"}]


@mcp.tool()
def create_folder(name: str, parent_id: Optional[str] = None) -> dict:
    """
    Create a folder in Google Drive.

    Args:
        name: Folder name.
        parent_id: Where to create it. A folder ID, or a shared drive ID to
                   land at that drive's top level. Omit for My Drive root.
    """
    try:
        body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            body["parents"] = [parent_id]

        folder = _drive().files().create(
            body=body,
            fields="id, name, mimeType, modifiedTime, owners, webViewLink",
            supportsAllDrives=True,
        ).execute()

        return _format_file(folder)
    except HttpError as e:
        return {"error": f"Drive API error {e.status_code}: {e.reason}"}


@mcp.tool()
def move_file(file_id: str, folder_id: str) -> dict:
    """
    Move a file or folder into another folder.

    The file is detached from every folder it currently sits in, so this is a
    move and not a second placement. Works across My Drive and shared drives.

    Args:
        file_id: The file or folder to move.
        folder_id: Destination folder ID (or shared drive ID for its root).
    """
    try:
        moved = move_to_folder(file_id, folder_id)
        return {
            "id": moved["id"],
            "name": moved.get("name", ""),
            "parents": moved.get("parents", []),
            "link": moved.get("webViewLink", ""),
        }
    except HttpError as e:
        return {"error": f"Drive API error {e.status_code}: {e.reason}"}
