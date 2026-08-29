"""Image insertion — supports URLs and local file paths (uploaded via Drive)."""

import logging
import mimetypes
import os
from typing import Optional

from googleapiclient.http import MediaFileUpload

from app import mcp
from ._common import docs, drive, pt, tool_errors

logger = logging.getLogger(__name__)


def _upload_image_to_drive(local_path: str) -> str:
    """Upload a local image to Drive and return a public-readable URL."""
    if not os.path.isfile(local_path):
        raise ValueError(f"Local image not found: {local_path}")

    mime, _ = mimetypes.guess_type(local_path)
    if not mime or not mime.startswith("image/"):
        raise ValueError(f"Not a recognized image type: {local_path}")

    service = drive()
    file_metadata = {"name": os.path.basename(local_path)}
    media = MediaFileUpload(local_path, mimetype=mime)
    f = service.files().create(
        body=file_metadata, media_body=media, fields="id"
    ).execute()
    file_id = f["id"]
    # Make publicly readable so the Docs API can fetch it
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()
    return f"https://drive.google.com/uc?id={file_id}"


@mcp.tool()
@tool_errors
def insert_image(
    document_id: str,
    index: int,
    source: str,
    width_pt: Optional[float] = None,
    height_pt: Optional[float] = None,
) -> dict:
    """
    Insert an inline image at the given index.

    Args:
        source: A URL (http(s)://...) OR a local file path. Local files are
                uploaded to Drive (made publicly readable) and then embedded.
        width_pt, height_pt: Optional size in points (72pt = 1 inch). If both
                              omitted, Docs sizes to the image's native size.
                              If only one is given, the other is omitted (Docs
                              preserves aspect ratio).
    """
    if source.startswith(("http://", "https://")):
        uri = source
    else:
        uri = _upload_image_to_drive(source)

    request: dict = {
        "insertInlineImage": {
            "location": {"index": index},
            "uri": uri,
        }
    }
    if width_pt or height_pt:
        size: dict = {}
        if width_pt:
            size["width"] = pt(width_pt)
        if height_pt:
            size["height"] = pt(height_pt)
        request["insertInlineImage"]["objectSize"] = size

    docs().documents().batchUpdate(
        documentId=document_id, body={"requests": [request]}
    ).execute()
    return {"id": document_id, "status": f"Image inserted at {index}."}
