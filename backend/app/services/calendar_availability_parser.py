from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Sequence
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
_WEEKDAY_TIME_PATTERN = re.compile(
    r"\b(?:on\s+)?(?:(?P<modifier>this|next)\s+)?"
    r"(?P<weekday>monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"\b(?:\s+at)?\s+"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<meridiem>am|pm)?\b",
    re.IGNORECASE,
)
_WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
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
_CONSULTATION_TERM_PATTERN = re.compile(r"\b(?:consultation|consult)\b", re.IGNORECASE)
_EVENT_DATE_AVAILABILITY_PATTERN = re.compile(
    r"\b(?:wedding|event)\s+date\b|\bmy\s+wedding\s+date\b",
    re.IGNORECASE,
)
_BOOKING_CONFIRMATION_PATTERNS = (
    re.compile(
        r"\byes\b[^.!?]{0,80}\b(?:please\s+)?(?:book|schedule|reserve|confirm)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bthat\s+works\b[^.!?]{0,80}\b(?:please\s+)?(?:book|schedule|reserve)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:please\s+)?(?:book|schedule|reserve)\s+(?:it|that\s+time|this\s+time)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bconfirm\s+(?:the\s+)?consultation\b", re.IGNORECASE),
    re.compile(
        r"\byes\b[^.!?]{0,80}\b(?:today|tomorrow|monday|tuesday|wednesday|thursday|"
        r"friday|saturday|sunday)\b[^.!?]{0,80}\bworks\b",
        re.IGNORECASE,
    ),
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
class ParsedConsultationBookingConfirmation:
    is_confirmation: bool
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
        re.search(r"\b(?:meeting|call|appointment|consultation|consult)\b", normalized)
        or re.search(r"\bmeet\b", normalized)
    )


def should_check_exact_availability(message_body: str) -> bool:
    """Return whether an exact date/time should be checked on the calendar.

    Wedding/event availability often needs operational details before staff can
    confirm the date. Consultation-style requests are just appointments, even
    when the client says "wedding consultation".
    """
    return explicit_meeting_request(message_body) or event_type_phrase(message_body) is None


def is_consultation_booking_confirmation(message_body: str) -> bool:
    normalized = message_body.lower()
    if (
        _EVENT_DATE_AVAILABILITY_PATTERN.search(normalized)
        and not _CONSULTATION_TERM_PATTERN.search(normalized)
    ):
        return False
    if (
        (
            normalized.strip().endswith("?")
            or re.search(r"^\s*(?:can|could|would|do|does|is|are)\b", normalized)
        )
        and "yes" not in normalized
        and "that works" not in normalized
    ):
        return False
    if any(pattern.search(message_body) for pattern in _BOOKING_CONFIRMATION_PATTERNS):
        return True
    if _CONSULTATION_TERM_PATTERN.search(normalized) and re.search(
        r"\b(?:book|schedule|reserve|confirm)\b",
        normalized,
    ):
        return True
    return False


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

    if not should_check_exact_availability(message_body):
        return ParsedAvailabilityRequest(None, None, timezone_name, "needs_event_details_staff_review")

    match = _TODAY_TOMORROW_PATTERN.search(message_body)
    if match:
        day_offset = 0 if match.group("day").lower() == "today" else 1
        parsed_time = _parse_time_match(match)
        if parsed_time is None:
            return ParsedAvailabilityRequest(None, None, timezone_name, "needs_staff_review")
        hour, minute = parsed_time

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

    match = _WEEKDAY_TIME_PATTERN.search(message_body)
    if match:
        parsed_time = _parse_time_match(match)
        if parsed_time is None:
            return ParsedAvailabilityRequest(None, None, timezone_name, "needs_staff_review")
        hour, minute = parsed_time

        requested_date = _resolve_weekday_date(
            weekday=match.group("weekday"),
            modifier=match.group("modifier"),
            reference=reference,
            hour=hour,
            minute=minute,
        )
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


def parse_consultation_booking_confirmation(
    message_body: str,
    *,
    reference_time: datetime | None = None,
    timezone_name: str = DEFAULT_CALENDAR_TIMEZONE,
) -> ParsedConsultationBookingConfirmation:
    if not is_consultation_booking_confirmation(message_body):
        return ParsedConsultationBookingConfirmation(
            False,
            None,
            None,
            timezone_name,
            "not_consultation_booking_confirmation",
        )

    parsed_slot = parse_availability_request(
        message_body,
        reference_time=reference_time,
        timezone_name=timezone_name,
    )
    if parsed_slot.has_exact_time:
        return ParsedConsultationBookingConfirmation(
            True,
            parsed_slot.start_time,
            parsed_slot.end_time,
            parsed_slot.timezone,
        )

    return ParsedConsultationBookingConfirmation(
        True,
        None,
        None,
        timezone_name,
        "needs_prior_consultation_slot",
    )


def recent_consultation_slot_from_memory(
    messages: Sequence[Any],
    *,
    current_message_id: str | None = None,
    reference_time: datetime | None = None,
    timezone_name: str = DEFAULT_CALENDAR_TIMEZONE,
) -> ParsedAvailabilityRequest | None:
    for memory in reversed(messages):
        if (
            current_message_id is not None
            and str(getattr(memory, "message_id", "")) == current_message_id
        ):
            continue
        body = str(getattr(memory, "body", "") or "")
        if not body:
            continue
        if not explicit_meeting_request(body):
            continue
        sent_at = _parse_memory_sent_at(getattr(memory, "sent_at", None)) or reference_time
        parsed = parse_availability_request(
            body,
            reference_time=sent_at,
            timezone_name=timezone_name,
        )
        if parsed.has_exact_time:
            return parsed
    return None


def _parse_time_match(match: re.Match[str]) -> tuple[int, int] | None:
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or "0")
    meridiem = (match.group("meridiem") or "").lower()
    if minute > 59 or hour > 23:
        return None
    if meridiem:
        if hour < 1 or hour > 12:
            return None
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
    elif 1 <= hour <= 7:
        hour += 12
    return hour, minute


def _resolve_weekday_date(
    *,
    weekday: str,
    modifier: str | None,
    reference: datetime,
    hour: int,
    minute: int,
):
    target_weekday = _WEEKDAY_INDEX[weekday.lower()]
    days_ahead = (target_weekday - reference.weekday()) % 7
    modifier = (modifier or "").lower()
    if modifier == "next" and days_ahead == 0:
        days_ahead = 7
    if not modifier and days_ahead == 0:
        requested_time = reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if requested_time <= reference:
            days_ahead = 7
    return reference.date() + timedelta(days=days_ahead)


def _parse_memory_sent_at(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
