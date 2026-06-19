from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Reuse credentials and calendar ID already loaded in googlesheets.py
from services.googlesheets import secret_credentials, CALENDAR_ID

SCOPES   = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = "Asia/Kolkata"


def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str,
    date: str | None = None,
) -> str:
    """
    Creates a coaching session event on the coach's Google Calendar.

    Args:
        title       – Event title, e.g. "STU001 – Concept Review Session"
        start_time  – "HH:MM AM/PM" or 24-hour "HH:MM", e.g. "09:00 AM" or "09:00"
        end_time    – same format as start_time
        description – Plain-text agenda / reason for the session
        date        – "YYYY-MM-DD"; defaults to today if None

    Returns:
        Confirmation string, or an error message.
    """
    try:
        creds = Credentials.from_service_account_info(
            secret_credentials,
            scopes=SCOPES
        )
        calendar_service = build("calendar", "v3", credentials=creds)

        today = date or datetime.now().strftime("%Y-%m-%d")

        # Accept both "HH:MM AM/PM" and 24-hour "HH:MM"
        def _parse_time(t: str) -> datetime:
            t = t.strip()
            for fmt in ("%I:%M %p", "%H:%M"):
                try:
                    return datetime.strptime(f"{today} {t}", f"%Y-%m-%d {fmt}")
                except ValueError:
                    continue
            raise ValueError(f"Unrecognised time format: '{t}'")

        start_dt = _parse_time(start_time)
        end_dt   = _parse_time(end_time)

        event = {
            "summary":     title,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
            "end":   {"dateTime": end_dt.isoformat(),   "timeZone": TIMEZONE},
        }

        created = calendar_service.events().insert(
            calendarId=CALENDAR_ID,
            body=event
        ).execute()

        link = created.get("htmlLink", "N/A")
        return f"Calendar event created: {link}"

    except Exception as e:
        return f"Failed to create calendar event: {str(e)}"