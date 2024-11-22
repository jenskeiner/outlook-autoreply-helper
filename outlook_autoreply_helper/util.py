from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo
import logging
import requests

log = logging.getLogger(__name__)


def get_datetime(obj):
    """
    Convert a Microsoft Graph API datetime object to a timezone-aware datetime.

    Args:
        obj (dict): A dictionary containing 'dateTime' and 'timeZone' keys

    Returns:
        datetime: A timezone-aware datetime object
    """
    return datetime.fromisoformat(obj["dateTime"]).replace(
        tzinfo=ZoneInfo(obj["timeZone"])
    )


def get_tz(name: str) -> ZoneInfo:
    """
    Convert Windows timezone name to IANA timezone.

    Attempts to map Windows timezone names to IANA timezones using
    the provided XML mapping file. Falls back to UTC if no mapping found.

    Args:
        name (str): Windows timezone name
        windows_zones_file (Path): Path to Windows timezone mapping XML

    Returns:
        ZoneInfo: Corresponding IANA timezone
    """
    try:
        return ZoneInfo(name)
    except Exception:
        try:
            tree = ET.parse(Path(__file__).parent / "windowsZones.xml")
            root = tree.getroot()

            for mapZone in root.findall(".//mapZone"):
                if mapZone.get("other") == name:
                    iana_name = mapZone.get("type").split()[0]
                    return ZoneInfo(iana_name)

            return ZoneInfo("UTC")
        except Exception as e:
            log.warning(f"Failed to parse Windows time zone: {e}")
            return ZoneInfo("UTC")


def get_adjacent_events(mailbox_timezone, settings, headers, start_event):
    """
    Recursively finds all adjacent or overlapping events, starting with the given event.

    Searches for consecutive absence events to create a continuous absence period.

    Args:
        mailbox_timezone (ZoneInfo): User's mailbox timezone
        settings (Settings): Application settings
        headers (dict): API request headers
        start_event (dict): Initial absence event

    Returns:
        list: Adjacent or overlapping absence events
    """
    adjacent_events = []
    current_event = start_event

    while True:
        # Get the end time of the current event
        current_start = get_datetime(current_event["start"]).replace(
            tzinfo=mailbox_timezone
        )
        current_end = get_datetime(current_event["end"]).replace(
            tzinfo=mailbox_timezone
        )

        # Look for events starting from the end of the current event
        calendar_view_response = requests.get(
            f"{settings.app.base_url}/me/calendar/calendarView",
            headers=headers,
            params={
                "startDateTime": current_start.isoformat(),
                "endDateTime": (
                    current_start + timedelta(days=365)
                ).isoformat(),  # Look up to a year ahead
                "$filter": f"subject eq '{settings.absence.keyword}' and isAllDay eq true",
                "$orderby": "start/dateTime",
                "$top": 10,  # Get multiple events to check for adjacency/overlap
            },
        )

        calendar_events = calendar_view_response.json().get("value", [])
        calendar_events = [x for x in calendar_events if x not in adjacent_events]

        # Find the next adjacent or overlapping event
        next_event = None
        for event in calendar_events:
            event_start = get_datetime(event["start"]).replace(tzinfo=mailbox_timezone)

            # Check if this event is adjacent (starts on the same day or the next day)
            # or overlaps with the current event
            if event_start <= current_end:
                next_event = event
                break

        if next_event is None:
            break

        adjacent_events.append(next_event)
        current_event = next_event

    return adjacent_events