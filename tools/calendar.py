"""
Google Calendar tools — event CRUD and calendar listing.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from googleapiclient.errors import HttpError

from app import mcp
from auth import get_service

logger = logging.getLogger(__name__)


def _calendar():
    return get_service("calendar", "v3")


def _format_event(event: dict) -> dict:
    """Format a Calendar event for display."""
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event["id"],
        "summary": event.get("summary", "(no title)"),
        "start": start.get("dateTime", start.get("date", "")),
        "end": end.get("dateTime", end.get("date", "")),
        "location": event.get("location", ""),
        "description": event.get("description", ""),
        "status": event.get("status", ""),
        "html_link": event.get("htmlLink", ""),
        "attendees": [
            {
                "email": a.get("email", ""),
                "name": a.get("displayName", ""),
                "response": a.get("responseStatus", ""),
            }
            for a in event.get("attendees", [])
        ],
        "organizer": event.get("organizer", {}).get("email", ""),
    }


@mcp.tool()
def list_events(
    days_ahead: int = 7,
    days_behind: int = 0,
    calendar_id: str = "primary",
    query: Optional[str] = None,
    max_results: int = 50,
) -> list[dict]:
    """
    List calendar events within a time window.

    Args:
        days_ahead: Number of days to look ahead (default 7)
        days_behind: Number of days to look back (default 0)
        calendar_id: Calendar ID (default 'primary')
        query: Free text search query to filter events
        max_results: Maximum events to return (default 50)
    """
    try:
        service = _calendar()
        now = datetime.now(timezone.utc)
        time_min = (now - timedelta(days=days_behind)).isoformat()
        time_max = (now + timedelta(days=days_ahead)).isoformat()

        kwargs = {
            "calendarId": calendar_id,
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": min(max_results, 250),
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if query:
            kwargs["q"] = query

        response = service.events().list(**kwargs).execute()
        events = response.get("items", [])

        return [_format_event(e) for e in events]
    except HttpError as e:
        return [{"error": f"Calendar API error {e.status_code}: {e.reason}"}]


@mcp.tool()
def get_event(event_id: str, calendar_id: str = "primary") -> dict:
    """
    Get full details of a specific calendar event.

    Args:
        event_id: The event ID
        calendar_id: Calendar ID (default 'primary')
    """
    try:
        service = _calendar()
        event = service.events().get(
            calendarId=calendar_id, eventId=event_id
        ).execute()
        return _format_event(event)
    except HttpError as e:
        return {"error": f"Calendar API error {e.status_code}: {e.reason}"}


@mcp.tool()
def create_event(
    summary: str,
    start: str,
    end: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[list[str]] = None,
    timezone: Optional[str] = None,
    calendar_id: str = "primary",
) -> dict:
    """
    Create a new calendar event.

    Args:
        summary: Event title
        start: Start time as ISO 8601 string (e.g. '2024-03-15T10:00:00-05:00')
        end: End time as ISO 8601 string
        description: Event description/notes
        location: Event location
        attendees: List of attendee email addresses
        timezone: Timezone (e.g. 'America/New_York'). If not set, uses calendar default
        calendar_id: Calendar ID (default 'primary')
    """
    try:
        service = _calendar()

        event_body: dict = {
            "summary": summary,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
        }

        if timezone:
            event_body["start"]["timeZone"] = timezone
            event_body["end"]["timeZone"] = timezone
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": e} for e in attendees]

        result = service.events().insert(
            calendarId=calendar_id, body=event_body
        ).execute()

        return {
            "id": result["id"],
            "summary": result.get("summary", ""),
            "html_link": result.get("htmlLink", ""),
            "status": "Event created successfully.",
        }
    except HttpError as e:
        return {"error": f"Calendar API error {e.status_code}: {e.reason}"}


@mcp.tool()
def update_event(
    event_id: str,
    summary: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[list[str]] = None,
    calendar_id: str = "primary",
) -> dict:
    """
    Update an existing calendar event. Only provided fields are changed.

    Args:
        event_id: The event ID to update
        summary: New event title
        start: New start time (ISO 8601)
        end: New end time (ISO 8601)
        description: New description
        location: New location
        attendees: New list of attendee emails (replaces existing)
        calendar_id: Calendar ID (default 'primary')
    """
    try:
        service = _calendar()

        # Get current event
        current = service.events().get(
            calendarId=calendar_id, eventId=event_id
        ).execute()

        if summary is not None:
            current["summary"] = summary
        if start is not None:
            current["start"] = {"dateTime": start}
        if end is not None:
            current["end"] = {"dateTime": end}
        if description is not None:
            current["description"] = description
        if location is not None:
            current["location"] = location
        if attendees is not None:
            current["attendees"] = [{"email": e} for e in attendees]

        result = service.events().update(
            calendarId=calendar_id, eventId=event_id, body=current
        ).execute()

        return {
            "id": result["id"],
            "summary": result.get("summary", ""),
            "status": "Event updated successfully.",
        }
    except HttpError as e:
        return {"error": f"Calendar API error {e.status_code}: {e.reason}"}


@mcp.tool()
def delete_event(event_id: str, calendar_id: str = "primary") -> dict:
    """
    Delete a calendar event.

    Args:
        event_id: The event ID to delete
        calendar_id: Calendar ID (default 'primary')
    """
    try:
        service = _calendar()
        service.events().delete(
            calendarId=calendar_id, eventId=event_id
        ).execute()
        return {"status": "Event deleted successfully.", "event_id": event_id}
    except HttpError as e:
        return {"error": f"Calendar API error {e.status_code}: {e.reason}"}


@mcp.tool()
def list_calendars() -> list[dict]:
    """
    List all calendars the user has access to.

    Returns calendar ID, name, description, and access role.
    """
    try:
        service = _calendar()
        response = service.calendarList().list().execute()
        calendars = response.get("items", [])

        return [
            {
                "id": cal["id"],
                "summary": cal.get("summary", ""),
                "description": cal.get("description", ""),
                "primary": cal.get("primary", False),
                "access_role": cal.get("accessRole", ""),
                "time_zone": cal.get("timeZone", ""),
            }
            for cal in calendars
        ]
    except HttpError as e:
        return [{"error": f"Calendar API error {e.status_code}: {e.reason}"}]
