from dataclasses import dataclass


RISK_LEVEL_LOW = "low"
RISK_LEVEL_MEDIUM = "medium"
RISK_LEVEL_HIGH = "high"

RISK_FLAG_URGENT_CHANGE = "urgent_change"
RISK_FLAG_COMPLAINT = "complaint"
RISK_FLAG_CANCELLATION_RISK = "cancellation_risk"
RISK_FLAG_PAYMENT_RISK = "payment_risk"
RISK_FLAG_GUEST_COUNT_CHANGE = "guest_count_change"
RISK_FLAG_HUMAN_ESCALATION_NEEDED = "human_escalation_needed"
RISK_FLAG_UNSUPPORTED_OR_UNCLEAR_REQUEST = "unsupported_or_unclear_request"


@dataclass(frozen=True)
class RiskAssessment:
    level: str
    flags: list[str]
    reason: str


LOW_RISK_INTENTS = {
    "booking_inquiry",
    "pricing_request",
    "availability_question",
    "service_question",
}

URGENT_TERMS = (
    "urgent",
    "asap",
    "right now",
    "immediately",
    "today",
    "tomorrow",
    "tonight",
    "last minute",
    "last-minute",
    "emergency",
)
ANGRY_TERMS = (
    "angry",
    "furious",
    "unacceptable",
    "terrible",
    "awful",
    "disappointed",
    "upset",
    "bad service",
)
UNCONFIRMED_PAYMENT_TERMS = (
    "not confirmed",
    "unconfirmed",
    "not received",
    "missing payment",
    "charged twice",
    "double charged",
    "refund",
    "failed payment",
)
GUEST_COUNT_TERMS = (
    "guest count",
    "number of guests",
    "more guests",
    "fewer guests",
    "less guests",
    "additional guests",
    "extra guests",
    "headcount",
    "people attending",
    "add guests",
    "increase guests",
    "increase the guest count",
    "venue capacity",
    "catering capacity",
    "seating capacity",
)
PAYMENT_TERMS = ("payment", "deposit", "invoice", "paid", "charge", "refund")
CANCELLATION_TERMS = ("cancel", "cancellation", "call off")
COMPLAINT_TERMS = (
    "complaint",
    "complain",
    "unhappy",
    "upset",
    "disappointed",
    "bad service",
    "unacceptable",
)
HUMAN_ESCALATION_TERMS = ("human", "manager", "supervisor", "agent", "person")
EXPLICIT_HUMAN_ESCALATION_PHRASES = (
    "speak to a manager",
    "talk to a manager",
    "manager now",
    "call me now",
    "human",
)
UNCLEAR_TERMS = ("unclear", "confused", "not sure", "unsupported", "doesn't make sense")


def detect_message_risk(text: str, intent_label: str | None) -> RiskAssessment:
    normalized = text.lower()
    label = intent_label or "other"

    has_payment_risk = label == "payment_issue" or _contains_any(normalized, PAYMENT_TERMS)
    has_explicit_human_escalation = (
        label == "human_escalation" or _contains_any(normalized, EXPLICIT_HUMAN_ESCALATION_PHRASES)
    )
    if has_payment_risk and has_explicit_human_escalation:
        return RiskAssessment(
            level=RISK_LEVEL_HIGH,
            flags=[RISK_FLAG_PAYMENT_RISK, RISK_FLAG_HUMAN_ESCALATION_NEEDED],
            reason="Payment issue includes an explicit request for human or manager escalation.",
        )

    if label == "complaint" or _contains_any(normalized, COMPLAINT_TERMS):
        return RiskAssessment(
            level=RISK_LEVEL_HIGH,
            flags=[RISK_FLAG_COMPLAINT],
            reason="Message indicates dissatisfaction or a complaint.",
        )

    if label == "cancellation_request" or _contains_any(normalized, CANCELLATION_TERMS):
        return RiskAssessment(
            level=RISK_LEVEL_HIGH,
            flags=[RISK_FLAG_CANCELLATION_RISK],
            reason="Message indicates the client may cancel the booking.",
        )

    if has_payment_risk:
        high_payment_terms = URGENT_TERMS + ANGRY_TERMS + UNCONFIRMED_PAYMENT_TERMS
        is_high = _contains_any(normalized, high_payment_terms)
        return RiskAssessment(
            level=RISK_LEVEL_HIGH if is_high else RISK_LEVEL_MEDIUM,
            flags=[RISK_FLAG_PAYMENT_RISK],
            reason=(
                "Payment issue includes urgent, angry, or unconfirmed payment language."
                if is_high
                else "Message mentions a payment issue that needs follow-up."
            ),
        )

    if label == "guest_count_change" or _contains_any(normalized, GUEST_COUNT_TERMS):
        is_high = _contains_any(normalized, URGENT_TERMS)
        return RiskAssessment(
            level=RISK_LEVEL_HIGH if is_high else RISK_LEVEL_MEDIUM,
            flags=[RISK_FLAG_GUEST_COUNT_CHANGE],
            reason=(
                "Guest count change is urgent or last-minute."
                if is_high
                else "Guest count change may affect planning and vendor capacity."
            ),
        )

    if label == "human_escalation" or _contains_any(normalized, HUMAN_ESCALATION_TERMS):
        return RiskAssessment(
            level=RISK_LEVEL_HIGH,
            flags=[RISK_FLAG_HUMAN_ESCALATION_NEEDED],
            reason="Client is asking for human or manager escalation.",
        )

    if label == "urgent_change" or _contains_any(normalized, URGENT_TERMS):
        return RiskAssessment(
            level=RISK_LEVEL_HIGH,
            flags=[RISK_FLAG_URGENT_CHANGE],
            reason="Message contains urgent or last-minute change language.",
        )

    if label in LOW_RISK_INTENTS:
        return RiskAssessment(
            level=RISK_LEVEL_LOW,
            flags=[],
            reason=f"{label} is a routine planning request.",
        )

    if label == "other" or _contains_any(normalized, UNCLEAR_TERMS):
        return RiskAssessment(
            level=RISK_LEVEL_MEDIUM,
            flags=[RISK_FLAG_UNSUPPORTED_OR_UNCLEAR_REQUEST],
            reason="Request is unclear or unsupported and needs review.",
        )

    return RiskAssessment(
        level=RISK_LEVEL_MEDIUM,
        flags=[RISK_FLAG_UNSUPPORTED_OR_UNCLEAR_REQUEST],
        reason="Intent is not covered by routine low-risk planning rules.",
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)
