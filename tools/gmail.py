"""
Gmail tools — search, read, drafts, label management, and trash.
"""

import base64
import logging
from email.mime.text import MIMEText
from typing import Optional

from googleapiclient.errors import HttpError

from app import mcp
from auth import get_service

logger = logging.getLogger(__name__)


def _gmail():
    return get_service("gmail", "v1")


def _extract_headers(message: dict) -> dict:
    """Extract common headers from a Gmail message."""
    headers = {
        h["name"]: h["value"]
        for h in message.get("payload", {}).get("headers", [])
    }
    return {
        "id": message["id"],
        "thread_id": message.get("threadId", ""),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "subject": headers.get("Subject", "(no subject)"),
        "date": headers.get("Date", ""),
        "snippet": message.get("snippet", ""),
        "labels": message.get("labelIds", []),
    }


def _extract_body(message: dict) -> str:
    """Extract plain text body from a Gmail message payload."""
    payload = message.get("payload", {})

    def decode_part(part):
        data = part.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        return ""

    # Single-part message
    if payload.get("mimeType", "").startswith("text/"):
        return decode_part(payload)

    # Multipart: prefer text/plain
    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain":
            return decode_part(part)

    # Fallback to text/html
    for part in parts:
        if part.get("mimeType") == "text/html":
            return decode_part(part)

    # Check nested multipart (e.g., multipart/alternative inside multipart/mixed)
    for part in parts:
        if part.get("mimeType", "").startswith("multipart/"):
            sub_parts = part.get("parts", [])
            for sub in sub_parts:
                if sub.get("mimeType") == "text/plain":
                    return decode_part(sub)
            for sub in sub_parts:
                if sub.get("mimeType") == "text/html":
                    return decode_part(sub)

    return "(body not available)"


def _collect_message_ids(query: str, max_results: int = 5000) -> list[str]:
    """Paginate through messages.list and collect all matching IDs."""
    service = _gmail()
    ids = []
    page_token = None

    while len(ids) < max_results:
        batch_size = min(500, max_results - len(ids))
        kwargs = {"userId": "me", "q": query, "maxResults": batch_size}
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.users().messages().list(**kwargs).execute()
        messages = response.get("messages", [])
        ids.extend(m["id"] for m in messages)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return ids


def _build_mime_message(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
) -> dict:
    """Build a raw RFC 2822 message for the Gmail API."""
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    return {"raw": raw}


# ---------------------------------------------------------------------------
# Reading & Searching
# ---------------------------------------------------------------------------


@mcp.tool()
def search_emails(query: str, max_results: int = 20) -> list[dict]:
    """
    Search Gmail using any Gmail search query and return message summaries.

    Supports standard Gmail search syntax:
    - 'from:newsletters@example.com'
    - 'subject:sale older_than:30d'
    - 'category:promotions after:2024/01/01'
    - 'is:unread label:INBOX'
    - 'has:attachment larger:5M'

    Args:
        query: Gmail search query string
        max_results: Maximum messages to return (default 20, max 100)
    """
    try:
        service = _gmail()
        max_results = min(max_results, 100)

        response = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()

        messages = response.get("messages", [])
        if not messages:
            return []

        results = []
        for msg in messages:
            full = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            ).execute()
            results.append(_extract_headers(full))

        return results
    except HttpError as e:
        return [{"error": f"Gmail API error {e.status_code}: {e.reason}"}]


@mcp.tool()
def get_email(message_id: str) -> dict:
    """
    Fetch the full content of a specific email by its ID.

    Returns headers, plain text body (capped at 3000 chars), labels,
    and a list of attachment filenames.

    Args:
        message_id: Gmail message ID (from search_emails results)
    """
    try:
        service = _gmail()
        message = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        headers = {
            h["name"]: h["value"]
            for h in message.get("payload", {}).get("headers", [])
        }

        body = _extract_body(message)

        # Collect attachment filenames
        attachments = []
        for part in message.get("payload", {}).get("parts", []):
            filename = part.get("filename")
            if filename:
                attachments.append(filename)

        return {
            "id": message["id"],
            "thread_id": message.get("threadId", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "cc": headers.get("Cc", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "labels": message.get("labelIds", []),
            "snippet": message.get("snippet", ""),
            "body": body[:3000],
            "attachments": attachments,
        }
    except HttpError as e:
        return {"error": f"Gmail API error {e.status_code}: {e.reason}"}


@mcp.tool()
def list_labels() -> list[dict]:
    """
    List all Gmail labels (system and custom) with message and thread counts.

    Returns a list of labels with id, name, type, and counts.
    """
    try:
        service = _gmail()
        response = service.users().labels().list(userId="me").execute()
        labels = response.get("labels", [])

        results = []
        for label in labels:
            # Get detailed info with counts
            detail = service.users().labels().get(
                userId="me", id=label["id"]
            ).execute()
            results.append({
                "id": detail["id"],
                "name": detail["name"],
                "type": detail.get("type", ""),
                "messages_total": detail.get("messagesTotal", 0),
                "messages_unread": detail.get("messagesUnread", 0),
                "threads_total": detail.get("threadsTotal", 0),
                "threads_unread": detail.get("threadsUnread", 0),
            })

        return results
    except HttpError as e:
        return [{"error": f"Gmail API error {e.status_code}: {e.reason}"}]


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------


@mcp.tool()
def create_draft(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    reply_to_message_id: Optional[str] = None,
) -> dict:
    """
    Create a draft email for review before sending.

    Args:
        to: Recipient email address(es), comma-separated for multiple
        subject: Email subject line
        body: Email body text
        cc: CC recipients, comma-separated
        bcc: BCC recipients, comma-separated
        reply_to_message_id: If replying, the message ID to reply to (sets threading headers)
    """
    try:
        service = _gmail()
        mime_msg = _build_mime_message(to, subject, body, cc, bcc)
        draft_body = {"message": mime_msg}

        if reply_to_message_id:
            # Get the original message to set thread ID
            original = service.users().messages().get(
                userId="me", id=reply_to_message_id, format="metadata",
                metadataHeaders=["Message-ID"],
            ).execute()
            draft_body["message"]["threadId"] = original.get("threadId", "")

        draft = service.users().drafts().create(
            userId="me", body=draft_body
        ).execute()

        return {
            "draft_id": draft["id"],
            "message_id": draft["message"]["id"],
            "status": "Draft created successfully. Review and send from Gmail.",
        }
    except HttpError as e:
        return {"error": f"Gmail API error {e.status_code}: {e.reason}"}


@mcp.tool()
def update_draft(
    draft_id: str,
    to: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
) -> dict:
    """
    Update an existing draft email.

    All fields are optional — only provided fields are updated.
    Note: the Gmail API replaces the entire draft, so this reads the current
    draft first and merges changes.

    Args:
        draft_id: The draft ID to update
        to: New recipient(s)
        subject: New subject
        body: New body text
        cc: New CC recipients
        bcc: New BCC recipients
    """
    try:
        service = _gmail()

        # Get current draft to preserve unchanged fields
        current = service.users().drafts().get(
            userId="me", id=draft_id, format="full"
        ).execute()
        current_msg = current.get("message", {})
        current_headers = {
            h["name"]: h["value"]
            for h in current_msg.get("payload", {}).get("headers", [])
        }

        final_to = to or current_headers.get("To", "")
        final_subject = subject or current_headers.get("Subject", "")
        final_body = body or _extract_body(current_msg)
        final_cc = cc if cc is not None else current_headers.get("Cc")
        final_bcc = bcc if bcc is not None else current_headers.get("Bcc")

        mime_msg = _build_mime_message(final_to, final_subject, final_body, final_cc, final_bcc)

        updated = service.users().drafts().update(
            userId="me", id=draft_id, body={"message": mime_msg}
        ).execute()

        return {
            "draft_id": updated["id"],
            "status": "Draft updated successfully.",
        }
    except HttpError as e:
        return {"error": f"Gmail API error {e.status_code}: {e.reason}"}


@mcp.tool()
def list_drafts(max_results: int = 20) -> list[dict]:
    """
    List all email drafts with summaries.

    Args:
        max_results: Maximum drafts to return (default 20)
    """
    try:
        service = _gmail()
        response = service.users().drafts().list(
            userId="me", maxResults=min(max_results, 100)
        ).execute()

        drafts = response.get("drafts", [])
        if not drafts:
            return []

        results = []
        for draft in drafts:
            detail = service.users().drafts().get(
                userId="me", id=draft["id"], format="metadata"
            ).execute()
            msg = detail.get("message", {})
            headers = {
                h["name"]: h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            results.append({
                "draft_id": detail["id"],
                "message_id": msg.get("id", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", "(no subject)"),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
            })

        return results
    except HttpError as e:
        return [{"error": f"Gmail API error {e.status_code}: {e.reason}"}]


@mcp.tool()
def delete_draft(draft_id: str) -> dict:
    """
    Delete a draft email.

    Args:
        draft_id: The draft ID to delete
    """
    try:
        service = _gmail()
        service.users().drafts().delete(userId="me", id=draft_id).execute()
        return {"status": "Draft deleted successfully.", "draft_id": draft_id}
    except HttpError as e:
        return {"error": f"Gmail API error {e.status_code}: {e.reason}"}


# ---------------------------------------------------------------------------
# Label Management
# ---------------------------------------------------------------------------


@mcp.tool()
def create_label(
    name: str,
    text_color: Optional[str] = None,
    bg_color: Optional[str] = None,
) -> dict:
    """
    Create a custom Gmail label.

    Args:
        name: Label name (use '/' for nesting, e.g. 'Projects/Active')
        text_color: Hex color for text (e.g. '#ffffff')
        bg_color: Hex color for background (e.g. '#4986e7')
    """
    try:
        service = _gmail()
        label_body: dict = {
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        if text_color and bg_color:
            label_body["color"] = {
                "textColor": text_color,
                "backgroundColor": bg_color,
            }

        result = service.users().labels().create(
            userId="me", body=label_body
        ).execute()

        return {
            "id": result["id"],
            "name": result["name"],
            "status": "Label created successfully.",
        }
    except HttpError as e:
        return {"error": f"Gmail API error {e.status_code}: {e.reason}"}


@mcp.tool()
def update_label(
    label_id: str,
    name: Optional[str] = None,
    text_color: Optional[str] = None,
    bg_color: Optional[str] = None,
) -> dict:
    """
    Update a custom Gmail label (rename or change color).

    Args:
        label_id: The label ID to update
        name: New label name
        text_color: New hex text color
        bg_color: New hex background color
    """
    try:
        service = _gmail()
        body: dict = {}
        if name:
            body["name"] = name
        if text_color and bg_color:
            body["color"] = {
                "textColor": text_color,
                "backgroundColor": bg_color,
            }

        result = service.users().labels().update(
            userId="me", id=label_id, body=body
        ).execute()

        return {
            "id": result["id"],
            "name": result["name"],
            "status": "Label updated successfully.",
        }
    except HttpError as e:
        return {"error": f"Gmail API error {e.status_code}: {e.reason}"}


@mcp.tool()
def delete_label(label_id: str) -> dict:
    """
    Delete a custom Gmail label.

    System labels (INBOX, SENT, etc.) cannot be deleted.

    Args:
        label_id: The label ID to delete
    """
    try:
        service = _gmail()
        service.users().labels().delete(userId="me", id=label_id).execute()
        return {"status": "Label deleted successfully.", "label_id": label_id}
    except HttpError as e:
        return {"error": f"Gmail API error {e.status_code}: {e.reason}"}


@mcp.tool()
def modify_email_labels(
    message_ids: list[str],
    add_labels: Optional[list[str]] = None,
    remove_labels: Optional[list[str]] = None,
) -> dict:
    """
    Add or remove labels on one or more emails.

    Uses batchModify for efficiency (up to 1000 messages per call).
    Labels can be system labels (INBOX, UNREAD, STARRED, IMPORTANT, SPAM, TRASH)
    or custom label IDs.

    Args:
        message_ids: List of message IDs to modify
        add_labels: Label IDs to add
        remove_labels: Label IDs to remove
    """
    if not message_ids:
        return {"error": "No message IDs provided."}

    try:
        service = _gmail()
        body: dict = {"ids": message_ids}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels

        BATCH_SIZE = 1000
        total_modified = 0

        for i in range(0, len(message_ids), BATCH_SIZE):
            chunk = message_ids[i:i + BATCH_SIZE]
            chunk_body = {**body, "ids": chunk}
            service.users().messages().batchModify(
                userId="me", body=chunk_body
            ).execute()
            total_modified += len(chunk)

        return {
            "modified_count": total_modified,
            "added_labels": add_labels or [],
            "removed_labels": remove_labels or [],
        }
    except HttpError as e:
        return {"error": f"Gmail API error {e.status_code}: {e.reason}"}


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------


@mcp.tool()
def trash_messages(message_ids: list[str]) -> dict:
    """
    Move specific messages to Trash by their IDs.

    Messages are moved to Trash (recoverable for 30 days), not permanently deleted.
    Uses batchModify for efficiency.

    Args:
        message_ids: List of Gmail message ID strings
    """
    if not message_ids:
        return {"trashed_count": 0}

    try:
        service = _gmail()
        BATCH_SIZE = 1000
        total_trashed = 0

        for i in range(0, len(message_ids), BATCH_SIZE):
            chunk = message_ids[i:i + BATCH_SIZE]
            service.users().messages().batchModify(
                userId="me",
                body={
                    "ids": chunk,
                    "addLabelIds": ["TRASH"],
                    "removeLabelIds": ["INBOX"],
                },
            ).execute()
            total_trashed += len(chunk)
            logger.info("Trashed batch of %d (%d total)", len(chunk), total_trashed)

        return {"trashed_count": total_trashed}
    except HttpError as e:
        return {"error": f"Gmail API error {e.status_code}: {e.reason}"}


@mcp.tool()
def trash_by_search(query: str, dry_run: bool = True) -> dict:
    """
    Search for emails matching a query and trash them all.

    SAFETY: dry_run defaults to True. Always preview before executing.

    Typical workflow:
    1. trash_by_search(query='category:promotions older_than:3m') → see count
    2. Confirm the results look right
    3. trash_by_search(query='category:promotions older_than:3m', dry_run=False) → execute

    Args:
        query: Gmail search query (e.g. 'category:promotions older_than:30d')
        dry_run: If True (default), only count and preview — do not trash
    """
    try:
        all_ids = _collect_message_ids(query, max_results=5000)

        # Fetch preview of first 5
        service = _gmail()
        preview = []
        for msg_id in all_ids[:5]:
            msg = service.users().messages().get(
                userId="me",
                id=msg_id,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            preview.append(_extract_headers(msg))

        result = {
            "dry_run": dry_run,
            "query": query,
            "total_found": len(all_ids),
            "trashed_count": 0,
            "preview": preview,
        }

        if dry_run:
            result["message"] = (
                f"DRY RUN: Would trash {len(all_ids)} messages matching '{query}'. "
                "Set dry_run=False to execute."
            )
            return result

        trashed = trash_messages(all_ids)
        result["trashed_count"] = trashed.get("trashed_count", 0)
        result["message"] = f"Trashed {result['trashed_count']} messages."
        return result
    except HttpError as e:
        return {"error": f"Gmail API error {e.status_code}: {e.reason}"}
