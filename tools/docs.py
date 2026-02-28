"""
Google Docs tools — search, read, create, and edit documents.
"""

import logging
from typing import Optional

from googleapiclient.errors import HttpError

from app import mcp
from auth import get_service

logger = logging.getLogger(__name__)


def _docs():
    return get_service("docs", "v1")


def _drive():
    return get_service("drive", "v3")


def _extract_text(document: dict) -> str:
    """Extract plain text from a Google Docs document structure."""
    body = document.get("body", {})
    content = body.get("content", [])
    text_parts = []

    for element in content:
        paragraph = element.get("paragraph")
        if paragraph:
            for text_run in paragraph.get("elements", []):
                text_content = text_run.get("textRun", {}).get("content", "")
                text_parts.append(text_content)

        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                row_texts = []
                for cell in row.get("tableCells", []):
                    cell_text = ""
                    for cell_content in cell.get("content", []):
                        cell_para = cell_content.get("paragraph")
                        if cell_para:
                            for text_run in cell_para.get("elements", []):
                                cell_text += text_run.get("textRun", {}).get("content", "")
                    row_texts.append(cell_text.strip())
                text_parts.append("\t".join(row_texts) + "\n")

    return "".join(text_parts)


@mcp.tool()
def search_docs(query: str, max_results: int = 20) -> list[dict]:
    """
    Search Google Drive for Google Docs by name or content.

    Args:
        query: Search query (matches document name and content)
        max_results: Maximum results to return (default 20)
    """
    try:
        service = _drive()
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
    except HttpError as e:
        return [{"error": f"Drive API error {e.status_code}: {e.reason}"}]


@mcp.tool()
def read_doc(document_id: str) -> dict:
    """
    Read a Google Doc and return its content as plain text.

    Extracts text from paragraphs and tables. Formatting is not preserved.

    Args:
        document_id: The Google Docs document ID
    """
    try:
        service = _docs()
        doc = service.documents().get(documentId=document_id).execute()

        text = _extract_text(doc)

        return {
            "id": doc["documentId"],
            "title": doc.get("title", ""),
            "content": text[:10000],  # Cap at 10k chars
            "content_length": len(text),
            "link": f"https://docs.google.com/document/d/{doc['documentId']}/edit",
        }
    except HttpError as e:
        return {"error": f"Docs API error {e.status_code}: {e.reason}"}


@mcp.tool()
def create_doc(title: str, content: Optional[str] = None) -> dict:
    """
    Create a new Google Doc, optionally with initial text content.

    Args:
        title: Document title
        content: Initial text content to insert (optional)
    """
    try:
        service = _docs()
        doc = service.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]

        if content:
            service.documents().batchUpdate(
                documentId=doc_id,
                body={
                    "requests": [
                        {
                            "insertText": {
                                "location": {"index": 1},
                                "text": content,
                            }
                        }
                    ]
                },
            ).execute()

        return {
            "id": doc_id,
            "title": title,
            "link": f"https://docs.google.com/document/d/{doc_id}/edit",
            "status": "Document created successfully.",
        }
    except HttpError as e:
        return {"error": f"Docs API error {e.status_code}: {e.reason}"}


@mcp.tool()
def append_to_doc(document_id: str, text: str) -> dict:
    """
    Append text to the end of a Google Doc.

    Args:
        document_id: The Google Docs document ID
        text: Text to append
    """
    try:
        service = _docs()

        # Get current document to find the end index
        doc = service.documents().get(documentId=document_id).execute()
        body = doc.get("body", {})
        content = body.get("content", [])

        # The last element's endIndex minus 1 is the insertion point
        end_index = content[-1]["endIndex"] - 1 if content else 1

        service.documents().batchUpdate(
            documentId=document_id,
            body={
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": end_index},
                            "text": text,
                        }
                    }
                ]
            },
        ).execute()

        return {
            "id": document_id,
            "status": f"Appended {len(text)} characters to document.",
        }
    except HttpError as e:
        return {"error": f"Docs API error {e.status_code}: {e.reason}"}


@mcp.tool()
def insert_in_doc(document_id: str, text: str, index: int) -> dict:
    """
    Insert text at a specific character index in a Google Doc.

    Index 1 is the beginning of the document. Use read_doc to see the
    current content and determine the right insertion point.

    Args:
        document_id: The Google Docs document ID
        text: Text to insert
        index: Character index for insertion (1-based, 1 = start of doc)
    """
    try:
        service = _docs()
        service.documents().batchUpdate(
            documentId=document_id,
            body={
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": index},
                            "text": text,
                        }
                    }
                ]
            },
        ).execute()

        return {
            "id": document_id,
            "status": f"Inserted {len(text)} characters at index {index}.",
        }
    except HttpError as e:
        return {"error": f"Docs API error {e.status_code}: {e.reason}"}
