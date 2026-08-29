"""Doc management — search, create, copy from template, rename."""

import logging
from typing import Optional

from app import mcp
from ._common import docs, drive, tool_errors

logger = logging.getLogger(__name__)


@mcp.tool()
@tool_errors
def search_docs(query: str, max_results: int = 20) -> list[dict]:
    """
    Search Google Drive for Google Docs by name or content.

    Args:
        query: Search query (matches document name and content)
        max_results: Maximum results to return (default 20)
    """
    service = drive()
    response = service.files().list(
        q=f"mimeType='application/vnd.google-apps.document' and fullText contains '{query}'",
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


@mcp.tool()
@tool_errors
def create_doc(
    title: str,
    markdown: Optional[str] = None,
    content: Optional[str] = None,
    folder_id: Optional[str] = None,
) -> dict:
    """
    Create a new Google Doc.

    Args:
        title: Document title.
        markdown: Optional markdown to render as initial content.
                  Takes precedence over `content` when both are provided.
                  Supports headings, bold/italic/code, lists, tables, links,
                  images, code blocks, blockquotes, horizontal rules.
        content: Optional plain text to insert (legacy; prefer `markdown`).
        folder_id: Optional destination folder. The Docs API always creates in
                   My Drive root, so the doc is moved there afterwards. Accepts
                   a shared drive ID to land at that drive's top level.
    """
    service = docs()
    doc = service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]

    if markdown:
        from ._markdown import render_markdown_to_doc
        render_markdown_to_doc(service, doc_id, markdown, insert_index=1)
    elif content:
        service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
        ).execute()

    result = {
        "id": doc_id,
        "title": title,
        "link": f"https://docs.google.com/document/d/{doc_id}/edit",
        "status": "Document created successfully.",
    }

    if folder_id:
        from googleapiclient.errors import HttpError
        from tools.drive import move_to_folder
        try:
            moved = move_to_folder(doc_id, folder_id)
            result["parents"] = moved.get("parents", [])
        except HttpError as e:
            # The doc exists either way. Say so, or the caller goes looking for
            # a document it thinks was never created.
            result["status"] = (
                f"Document created in My Drive root, but moving it to {folder_id} "
                f"failed ({e.status_code}: {e.reason}). Move it by hand or with move_file."
            )

    return result


@mcp.tool()
@tool_errors
def copy_doc_from_template(template_id: str, new_title: str) -> dict:
    """
    Duplicate a Google Doc. Useful for branded templates (proposals, reports).

    The new doc lives in the user's Drive. Requires drive.file scope.
    """
    new_file = drive().files().copy(
        fileId=template_id,
        body={"name": new_title},
        fields="id, name, webViewLink",
    ).execute()
    return {
        "id": new_file["id"],
        "title": new_file["name"],
        "link": new_file.get("webViewLink", f"https://docs.google.com/document/d/{new_file['id']}/edit"),
    }


@mcp.tool()
@tool_errors
def rename_doc(document_id: str, new_title: str) -> dict:
    """Rename a Google Doc. Requires drive.file scope."""
    f = drive().files().update(
        fileId=document_id,
        body={"name": new_title},
        fields="id, name",
    ).execute()
    return {"id": f["id"], "title": f["name"]}
