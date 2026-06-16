from app.services.risk_detection_service import detect_message_risk


def test_pricing_request_becomes_low_risk():
    risk = detect_message_risk("Can you send me package pricing?", "pricing_request")

    assert risk.level == "low"
    assert risk.flags == []
    assert risk.reason == "pricing_request is a routine planning request."


def test_complaint_becomes_high_risk():
    risk = detect_message_risk("I am very unhappy with the bad service.", "complaint")

    assert risk.level == "high"
    assert risk.flags == ["complaint"]
    assert "complaint" in risk.reason.lower()


def test_unacceptable_manager_message_counts_as_high_risk_complaint():
    risk = detect_message_risk(
        "This is unacceptable and I want to speak to a manager immediately.",
        "human_escalation",
    )

    assert risk.level == "high"
    assert risk.flags == ["complaint"]


def test_cancellation_request_becomes_high_risk():
    risk = detect_message_risk("We need to cancel our booking.", "cancellation_request")

    assert risk.level == "high"
    assert risk.flags == ["cancellation_risk"]
    assert "cancel" in risk.reason.lower()


def test_guest_count_change_becomes_medium_or_high_based_on_urgency():
    medium = detect_message_risk("We have 15 more guests now.", "guest_count_change")
    high = detect_message_risk(
        "Last minute update for tomorrow: we have 15 more guests.",
        "guest_count_change",
    )

    assert medium.level == "medium"
    assert medium.flags == ["guest_count_change"]
    assert high.level == "high"
    assert high.flags == ["guest_count_change"]


def test_capacity_extra_guest_message_is_guest_count_risk_even_if_mislabeled():
    risk = detect_message_risk(
        "Can the venue and catering team handle 40 extra guests?",
        "availability_question",
    )

    assert risk.level == "medium"
    assert risk.flags == ["guest_count_change"]


def test_true_availability_with_guest_estimate_stays_low_risk():
    risk = detect_message_risk(
        "Are you available for a wedding on August 24 for around 120 guests?",
        "availability_question",
    )

    assert risk.level == "low"
    assert risk.flags == []


def test_payment_issue_becomes_medium_or_high_based_on_language():
    medium = detect_message_risk("Can you check our deposit payment?", "payment_issue")
    high = detect_message_risk(
        "This is urgent, our payment is not confirmed and I am angry.",
        "payment_issue",
    )

    assert medium.level == "medium"
    assert medium.flags == ["payment_risk"]
    assert high.level == "high"
    assert high.flags == ["payment_risk"]


def test_payment_issue_with_explicit_human_escalation_becomes_high_with_both_flags():
    risk = detect_message_risk(
        "My deposit payment failed and I need to speak to a manager now.",
        "payment_issue",
    )

    assert risk.level == "high"
    assert risk.flags == ["payment_risk", "human_escalation_needed"]
    assert "human or manager escalation" in risk.reason


def test_other_unclear_request_becomes_medium_risk():
    risk = detect_message_risk("I am not sure this request makes sense.", "other")

    assert risk.level == "medium"
    assert risk.flags == ["unsupported_or_unclear_request"]
