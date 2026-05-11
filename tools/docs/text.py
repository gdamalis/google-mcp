"""Document text tools — read, append, insert, markdown bulk ops, find/replace."""

import logging
from typing import Literal

from app import mcp
from ._common import docs, end_index, tool_errors

logger = logging.getLogger(__name__)


def _extract_text(document: dict) -> str:
    """Extract plain text from a Docs JSON structure (legacy behavior)."""
    body = document.get("body", {})
    content = body.get("content", [])
    text_parts = []
    for element in content:
        paragraph = element.get("paragraph")
        if paragraph:
            for text_run in paragraph.get("elements", []):
                text_parts.append(text_run.get("textRun", {}).get("content", ""))
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
@tool_errors
def read_doc(
    document_id: str,
    format: Literal["markdown", "text", "json"] = "markdown",
) -> dict:
    """
    Read a Google Doc.

    Args:
        document_id: The Google Docs document ID.
        format: "markdown" (default — structured export with headings, lists, bold, etc.)
                "text" (legacy plain-text; preserves old behavior without formatting)
                "json" (raw Docs structure with indices — use this before
                        calling apply_text_style or other index-based tools)
    """
    service = docs()
    doc = service.documents().get(documentId=document_id).execute()

    result = {
        "id": doc["documentId"],
        "title": doc.get("title", ""),
        "link": f"https://docs.google.com/document/d/{doc['documentId']}/edit",
    }

    if format == "text":
        text = _extract_text(doc)
        result["content"] = text[:10000]
        result["content_length"] = len(text)
    elif format == "json":
        result["document"] = doc
    else:  # markdown
        from ._reader import docs_to_markdown
        md = docs_to_markdown(doc)
        result["content"] = md
        result["content_length"] = len(md)

    return result


@mcp.tool()
@tool_errors
def append_to_doc(document_id: str, text: str) -> dict:
    """
    Append plain text to the end of a Google Doc.

    For richly formatted appends, use `append_markdown` instead.
    """
    service = docs()
    doc = service.documents().get(documentId=document_id).execute()
    idx = end_index(doc)
    service.documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"insertText": {"location": {"index": idx}, "text": text}}]},
    ).execute()
    return {"id": document_id, "status": f"Appended {len(text)} characters."}


@mcp.tool()
@tool_errors
def insert_in_doc(document_id: str, text: str, index: int) -> dict:
    """
    Insert plain text at a specific character index.

    Index 1 is the start of the document. Use `read_doc(format="json")` to
    find indices for surgical edits.
    """
    service = docs()
    service.documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"insertText": {"location": {"index": index}, "text": text}}]},
    ).execute()
    return {"id": document_id, "status": f"Inserted {len(text)} characters at {index}."}


@mcp.tool()
@tool_errors
def append_markdown(document_id: str, markdown: str) -> dict:
    """
    Append markdown-rendered content to the end of a Google Doc.

    Supports headings (#–######), bold/italic/strikethrough/inline code, links,
    bulleted/numbered/checkbox lists (with nesting), tables, images from URLs,
    code blocks, blockquotes, horizontal rules.

    For images from local files, use `insert_image` after appending.
    """
    from ._markdown import render_markdown_to_doc
    service = docs()
    doc = service.documents().get(documentId=document_id).execute()
    idx = end_index(doc)
    render_markdown_to_doc(service, document_id, markdown, insert_index=idx)
    return {"id": document_id, "status": f"Appended markdown ({len(markdown)} chars)."}


@mcp.tool()
@tool_errors
def replace_doc_markdown(document_id: str, markdown: str) -> dict:
    """
    Replace the entire body of a Google Doc with markdown-rendered content.

    Existing body content is deleted first; markdown is then inserted at index 1.
    Headers, footers, and document metadata are preserved.
    """
    from ._markdown import render_markdown_to_doc
    service = docs()
    doc = service.documents().get(documentId=document_id).execute()
    body_end = end_index(doc)
    if body_end > 1:
        service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"deleteContentRange": {
                "range": {"startIndex": 1, "endIndex": body_end},
            }}]},
        ).execute()
    if markdown:
        render_markdown_to_doc(service, document_id, markdown, insert_index=1)
    return {"id": document_id, "status": "Document body replaced."}


@mcp.tool()
@tool_errors
def replace_range_markdown(
    document_id: str,
    start_index: int,
    end_index_param: int,
    markdown: str,
) -> dict:
    """
    Replace content between start_index and end_index_param with markdown.

    Use `read_doc(format='json')` to find the right indices first.
    """
    from ._markdown import render_markdown_to_doc
    service = docs()
    if end_index_param > start_index:
        service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"deleteContentRange": {
                "range": {"startIndex": start_index, "endIndex": end_index_param},
            }}]},
        ).execute()
    if markdown:
        render_markdown_to_doc(service, document_id, markdown, insert_index=start_index)
    return {"id": document_id, "status": f"Replaced range with markdown."}
