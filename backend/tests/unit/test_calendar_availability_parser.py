from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.calendar_availability_parser import (
    describe_inexact_availability_request,
    is_consultation_booking_confirmation,
    parse_consultation_booking_confirmation,
    parse_availability_request,
)


REFERENCE = datetime(2026, 6, 19, 10, 0, tzinfo=ZoneInfo("Asia/Beirut"))


def test_consultation_tomorrow_at_4_pm_parses_exact_slot() -> None:
    parsed = parse_availability_request(
        "Can we schedule a consultation tomorrow at 4 PM?",
        reference_time=REFERENCE,
    )

    assert parsed.has_exact_time
    assert parsed.start_time == datetime(2026, 6, 20, 16, 0, tzinfo=ZoneInfo("Asia/Beirut"))
    assert parsed.end_time == datetime(2026, 6, 20, 16, 45, tzinfo=ZoneInfo("Asia/Beirut"))


def test_consultation_monday_at_12_pm_parses_exact_slot() -> None:
    parsed = parse_availability_request(
        "Is Monday at 12 PM available for a consultation?",
        reference_time=REFERENCE,
    )

    assert parsed.has_exact_time
    assert parsed.start_time == datetime(2026, 6, 22, 12, 0, tzinfo=ZoneInfo("Asia/Beirut"))


def test_wedding_consultation_next_monday_keeps_12_pm_time() -> None:
    parsed = parse_availability_request(
        "Can we schedule a wedding consultation next Monday at 12:00 PM?",
        reference_time=REFERENCE,
    )

    assert parsed.has_exact_time
    assert parsed.start_time == datetime(2026, 6, 22, 12, 0, tzinfo=ZoneInfo("Asia/Beirut"))


def test_wedding_event_date_request_still_needs_event_details() -> None:
    parsed = parse_availability_request(
        "Is my wedding date available next Monday at 12 PM?",
        reference_time=REFERENCE,
    )
    display = describe_inexact_availability_request("Is my wedding date available next Monday at 12 PM?")

    assert not parsed.has_exact_time
    assert parsed.reason == "needs_event_details_staff_review"
    assert display.requested_label == "Wedding next Monday"
    assert display.reason_label == "Needs event details / staff review"


def test_explicit_consultation_booking_confirmation_parses_requested_slot() -> None:
    parsed = parse_consultation_booking_confirmation(
        "Yes, please book the consultation next Monday at 12:00 PM.",
        reference_time=REFERENCE,
    )

    assert parsed.is_confirmation
    assert parsed.has_exact_time
    assert parsed.start_time == datetime(2026, 6, 22, 12, 0, tzinfo=ZoneInfo("Asia/Beirut"))


def test_vague_consultation_booking_confirmation_needs_prior_slot() -> None:
    parsed = parse_consultation_booking_confirmation(
        "Yes, please book it.",
        reference_time=REFERENCE,
    )

    assert parsed.is_confirmation
    assert not parsed.has_exact_time
    assert parsed.reason == "needs_prior_consultation_slot"


def test_availability_check_is_not_booking_confirmation() -> None:
    assert not is_consultation_booking_confirmation(
        "Can we schedule a consultation next Monday at 12:00 PM?"
    )


def test_wedding_date_availability_is_not_consultation_booking_confirmation() -> None:
    assert not is_consultation_booking_confirmation("Is my wedding date available next Monday?")
