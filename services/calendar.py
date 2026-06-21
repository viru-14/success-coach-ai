from datetime import datetime

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from services.googlesheets import secret_credentials, CALENDAR_ID

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = "Asia/Kolkata"


def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str,
    date: str | None = None,
    return_details: bool = False,
):
    
    try:
        creds = Credentials.from_service_account_info(
            secret_credentials,
            scopes=SCOPES,
        )

        calendar_service = build(
            "calendar",
            "v3",
            credentials=creds,
        )

        today = date or datetime.now().strftime("%Y-%m-%d")

        # Accept both "HH:MM AM/PM" and 24-hour "HH:MM"
        def _parse_time(t: str) -> datetime:
            t = t.strip()

            for fmt in ("%I:%M %p", "%H:%M"):
                try:
                    return datetime.strptime(
                        f"{today} {t}",
                        f"%Y-%m-%d {fmt}",
                    )
                except ValueError:
                    continue

            raise ValueError(f"Unrecognised time format: '{t}'")

        start_dt = _parse_time(start_time)
        end_dt = _parse_time(end_time)

        event = {
            "summary": title,
            "description": description,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": TIMEZONE,
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": TIMEZONE,
            },
        }

        created = (
            calendar_service.events()
            .insert(
                calendarId=CALENDAR_ID,
                body=event,
            )
            .execute()
        )

        link = created.get("htmlLink", "N/A") # if no link, just N/A

        if return_details:
            return {
                "ok": True,
                "event_id": created.get("id"),
                "link": link,
                "error": None,
            }

        return f"Calendar event created: {link}"

    except Exception as e:
        if return_details:
            return {
                "ok": False,
                "event_id": None,
                "link": None,
                "error": str(e),
            }

        return f"Failed to create calendar event: {str(e)}"


def delete_calendar_event(event_id: str) -> bool:
    """
    Delete a calendar event by id
    (used when a scheduled student is moved to tomorrow).

    Best-effort: returns True on success,
    False on any failure.
    """
    if not event_id:
        return False

    try:
        creds = Credentials.from_service_account_info(
            secret_credentials,
            scopes=SCOPES,
        )

        calendar_service = build(
            "calendar",
            "v3",
            credentials=creds,
        )

        calendar_service.events().delete(
            calendarId=CALENDAR_ID,
            eventId=event_id,
        ).execute()

        return True

    except Exception as e:
        print(f"Failed to delete calendar event {event_id}: {e}")
        return False