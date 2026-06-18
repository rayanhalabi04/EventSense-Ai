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
_EVENT_TYPE_TERMS = (
    ("wedding", "wedding"),
    ("reception", "reception"),
    ("engagement", "engagement"),
    ("bridal shower", "bridal shower"),
    ("corporate dinner", "corporate dinner"),
    ("birthday", "birthday"),
    ("ceremony", "ceremony"),
)
_MONTH_DATE_PATTERN = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?\b",
    re.IGNORECASE,
)
_DAY_MONTH_DATE_PATTERN = re.compile(
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|"
    r"apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:,?\s*\d{4})?\b",
    re.IGNORECASE,
)
_NUMERIC_DATE_PATTERN = re.compile(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b")
_RELATIVE_DATE_PATTERN = re.compile(
    r"\b(?:today|tomorrow|tonight|this\s+week|next\s+week|"
    r"(?:this|next)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
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


@dataclass(frozen=True)
class AvailabilityDisplayDetails:
    requested_label: str | None
    reason: str
    reason_label: str | None


def is_availability_question(message_body: str, intent_label: str | None) -> bool:
    if intent_label == "availability_question":
        return True
    normalized = message_body.lower()
    return any(keyword in normalized for keyword in _AVAILABILITY_KEYWORDS)


def describe_inexact_availability_request(message_body: str) -> AvailabilityDisplayDetails:
    if explicit_meeting_request(message_body):
        return AvailabilityDisplayDetails(
            requested_label="Needs preferred time",
            reason="needs_staff_review",
            reason_label="Needs staff review",
        )

    date_phrase = availability_date_phrase(message_body)
    event_type = event_type_phrase(message_body)
    if date_phrase:
        requested_label = _sentence_case(_event_availability_target(event_type, date_phrase))
    else:
        requested_label = "Needs event date/details"

    return AvailabilityDisplayDetails(
        requested_label=requested_label,
        reason="needs_event_details_staff_review",
        reason_label="Needs event details / staff review",
    )


def availability_date_phrase(message_body: str) -> str | None:
    for pattern in (
        _MONTH_DATE_PATTERN,
        _DAY_MONTH_DATE_PATTERN,
        _NUMERIC_DATE_PATTERN,
    ):
        match = pattern.search(message_body)
        if match:
            return _clean_phrase(match.group(0))

    relative_match = _RELATIVE_DATE_PATTERN.search(message_body)
    if relative_match:
        return _clean_phrase(relative_match.group(0))

    return None


def explicit_meeting_request(message_body: str) -> bool:
    normalized = message_body.lower()
    return bool(
        re.search(r"\b(?:meeting|call|appointment)\b", normalized)
        or re.search(r"\bmeet\b", normalized)
    )


def event_type_phrase(message_body: str) -> str | None:
    normalized = message_body.lower()
    for term, label in _EVENT_TYPE_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", normalized):
            return label
    return None


def _event_availability_target(event_type: str | None, date_phrase: str) -> str:
    target = f"{event_type}" if event_type else "event"
    if _date_phrase_reads_with_on(date_phrase):
        return f"{target} on {date_phrase}"
    return f"{target} {date_phrase}"


def _date_phrase_reads_with_on(date_phrase: str) -> bool:
    normalized = date_phrase.lower()
    explicit_date = (
        _MONTH_DATE_PATTERN.fullmatch(date_phrase)
        or _DAY_MONTH_DATE_PATTERN.fullmatch(date_phrase)
        or _NUMERIC_DATE_PATTERN.fullmatch(date_phrase)
    )
    return bool(explicit_date) or normalized in {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    }


def _clean_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ,.!?")


def _sentence_case(value: str) -> str:
    if not value:
        return value
    return value[0].upper() + value[1:]


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
