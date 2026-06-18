from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.calendar_service import DEFAULT_CALENDAR_TIMEZONE, DEFAULT_MEETING_DURATION_MINUTES


_AVAILABILITY_KEYWORDS = (
    "availability",
    "available",
    "free on",
    "meet",
    "meeting",
    "schedule",
    "appointment",
    "calendar",
)
_TODAY_TOMORROW_PATTERN = re.compile(
    r"\b(?P<day>today|tomorrow)\b(?:\s+at)?\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<meridiem>am|pm)?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedAvailabilityRequest:
    start_time: datetime | None
    end_time: datetime | None
    timezone: str
    reason: str | None = None

    @property
    def has_exact_time(self) -> bool:
        return self.start_time is not None and self.end_time is not None


def is_availability_question(message_body: str, intent_label: str | None) -> bool:
    if intent_label == "availability_question":
        return True
    normalized = message_body.lower()
    return any(keyword in normalized for keyword in _AVAILABILITY_KEYWORDS)


def parse_availability_request(
    message_body: str,
    *,
    reference_time: datetime | None = None,
    timezone_name: str = DEFAULT_CALENDAR_TIMEZONE,
) -> ParsedAvailabilityRequest:
    tz = ZoneInfo(timezone_name)
    reference = reference_time or datetime.now(tz)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=tz)
    else:
        reference = reference.astimezone(tz)

    match = _TODAY_TOMORROW_PATTERN.search(message_body)
    if match:
        day_offset = 0 if match.group("day").lower() == "today" else 1
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or "0")
        meridiem = (match.group("meridiem") or "").lower()
        if minute > 59 or hour > 23:
            return ParsedAvailabilityRequest(None, None, timezone_name, "needs_staff_review")
        if meridiem:
            if hour < 1 or hour > 12:
                return ParsedAvailabilityRequest(None, None, timezone_name, "needs_staff_review")
            if meridiem == "pm" and hour != 12:
                hour += 12
            if meridiem == "am" and hour == 12:
                hour = 0
        elif 1 <= hour <= 7:
            hour += 12

        requested_date = reference.date() + timedelta(days=day_offset)
        start_time = datetime(
            requested_date.year,
            requested_date.month,
            requested_date.day,
            hour,
            minute,
            tzinfo=tz,
        )
        return ParsedAvailabilityRequest(
            start_time,
            start_time + timedelta(minutes=DEFAULT_MEETING_DURATION_MINUTES),
            timezone_name,
        )

    if re.search(r"\bnext\s+week\b", message_body, flags=re.IGNORECASE):
        return ParsedAvailabilityRequest(None, None, timezone_name, "needs_staff_review")

    return ParsedAvailabilityRequest(None, None, timezone_name, "needs_staff_review")
