"""Unit tests for the Telegram client-message safe trimmer.

These guarantee a client never receives a mid-sentence / incomplete reply.
"""
import pytest

from app.services.telegram_auto_reply_service import (
    SAFE_CLIENT_FALLBACK,
    TELEGRAM_HARD_CHAR_LIMIT,
    client_facing_auto_reply_text,
    safe_trim_client_message,
    staff_facing_telegram_text,
)

LIMIT = TELEGRAM_HARD_CHAR_LIMIT


def _ends_with_punctuation(text: str) -> bool:
    return bool(text) and text.rstrip("\"')]”’»").rstrip()[-1] in ".!?"


def test_complete_cancellation_reply_is_preserved_and_ends_cleanly():
    text = (
        "We understand you wish to cancel your booking. According to our deposit "
        "policy, the deposit is non-refundable once the booking has been confirmed. "
        "A member of our team will review your booking details and follow up with "
        "you shortly."
    )
    result = safe_trim_client_message(text, LIMIT)
    assert result == text
    assert "non-refundable" in result  # deposit/refund policy preserved
    assert _ends_with_punctuation(result)


def test_truncated_reply_yields_empty_so_caller_uses_fallback():
    # The exact reported bug: cut mid-sentence after "once a".
    text = "We understand you wish to cancel your booking. Please note that once a"
    assert safe_trim_client_message(text, LIMIT) == ""


@pytest.mark.parametrize(
    "dangling",
    [
        "Your deposit is held securely. The deposit is non-refundable because",
        "Thanks for reaching out. We can help with",
        "Here is some info. According to",
        "We received your message. Please note that",
        "Our policy applies here. This happens once a",
    ],
)
def test_dangling_connector_endings_are_not_delivered(dangling: str):
    result = safe_trim_client_message(dangling, LIMIT)
    # Either nothing complete survives ("") or it ends on real punctuation —
    # never on a dangling connector.
    assert result == "" or _ends_with_punctuation(result)
    for bad_ending in ("because", "with", "according to", "please note that", "once a"):
        assert not result.rstrip().lower().endswith(bad_ending)


def test_max_length_trims_at_sentence_boundary_not_raw_characters():
    text = (
        "Our venue is beautiful and spacious. We host weddings of all sizes. "
        "Catering is fully customizable. Parking is available on site."
    )
    result = safe_trim_client_message(text, 80)
    assert len(result) <= 80
    assert _ends_with_punctuation(result)
    # Whole sentences only — the result is a prefix made of complete sentences,
    # never a mid-word/mid-sentence cut.
    assert text.startswith(result)
    assert result == "Our venue is beautiful and spacious. We host weddings of all sizes."


def test_pricing_lines_stay_complete_and_keep_structure():
    text = (
        "Classic Package: $5,000, up to 80 guests.\n"
        "Premium Package: $9,000, up to 150 guests."
    )
    result = safe_trim_client_message(text, 600)
    assert result == text
    assert _ends_with_punctuation(result)


def test_short_single_clause_staff_message_is_kept():
    # A brief staff reply without terminal punctuation is not mangled.
    assert safe_trim_client_message("Sounds good", LIMIT) == "Sounds good"


def test_empty_input_returns_empty():
    assert safe_trim_client_message("", LIMIT) == ""
    assert safe_trim_client_message("   ", LIMIT) == ""


def test_staff_facing_text_drops_truncated_reply_so_fallback_is_used():
    truncated = "We understand you wish to cancel your booking. Please note that once a"
    # staff_facing returns "" -> the send path substitutes the safe fallback.
    assert staff_facing_telegram_text(truncated) == ""
    assert (staff_facing_telegram_text(truncated) or SAFE_CLIENT_FALLBACK) == SAFE_CLIENT_FALLBACK


def test_staff_facing_text_preserves_complete_policy_reply():
    text = (
        "We understand you wish to cancel your booking. According to our deposit "
        "policy, the deposit is non-refundable once the booking has been confirmed. "
        "A member of our team will review your booking details and follow up with "
        "you shortly."
    )
    assert staff_facing_telegram_text(text) == text


def test_client_facing_text_removes_raw_faq_source_formatting():
    text = (
        "Hi, thank you for your message. According to our Faq: "
        "Q: Can I change my guest count after booking? "
        "A: Guest count changes usually need to be confirmed at least 10 days "
        "before the event."
    )

    result = client_facing_auto_reply_text(text)

    assert "Faq:" not in result
    assert "Q: Can I" not in result
    assert "A:" not in result
    assert "Guest count changes usually need to be confirmed" in result


def test_client_facing_pricing_text_has_one_generic_next_step():
    text = (
        "Thank you for your interest in our wedding packages! "
        "The Classic Package starts at $3,500 for up to 80 guests. "
        "We would be happy to help you choose the best option. "
        "A member of our team can help you choose the best option based on your event needs."
    )

    result = client_facing_auto_reply_text(text, intent_label="pricing_request")
    lowered = result.lower()

    assert "classic package starts at $3,500" in lowered
    assert lowered.count("choose the best option") == 1
    assert "we would be happy to help you choose" not in lowered


def test_staff_facing_text_removes_raw_source_labels_before_manual_send():
    text = (
        "According to our Cancellation Policy: Q: Is my deposit refundable? "
        "A: The booking deposit is non-refundable after booking confirmation."
    )

    result = staff_facing_telegram_text(text)

    assert "Cancellation Policy:" not in result
    assert "Q:" not in result
    assert "A:" not in result
    assert "non-refundable after booking confirmation" in result
