from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
from typing import Any

from app.core.config import settings


INTENT_LABELS = {
    "booking_inquiry",
    "pricing_request",
    "availability_question",
    "service_question",
    "urgent_change",
    "guest_count_change",
    "complaint",
    "cancellation_request",
    "payment_issue",
    "human_escalation",
    "other",
}


@dataclass(frozen=True)
class IntentClassification:
    label: str
    confidence: float
    used_fallback: bool = False


@dataclass(frozen=True)
class ClassifierStatus:
    loaded: bool
    model_version: str
    artifact_path: str
    artifact_hash: str | None = None


class IntentClassifierService:
    @staticmethod
    def classify(body: str) -> IntentClassification:
        text = body.strip()
        if not text:
            return IntentClassification(label="other", confidence=0.0, used_fallback=True)

        guest_count = _guest_count_operational_classification(text)
        if guest_count is not None:
            return guest_count
        high_risk = _high_risk_operational_classification(text)
        if high_risk is not None:
            return high_risk

        model = _load_model()
        if model is None:
            return _fallback_classify(text)

        try:
            prediction = model.predict([text])[0]
            label = str(prediction)
            if label not in INTENT_LABELS:
                return _fallback_classify(text)
            confidence = _predict_confidence(model, text, label)
            return IntentClassification(label=label, confidence=confidence)
        except Exception:
            # Fallback keeps inbound message creation working if the artifact is incompatible.
            return _fallback_classify(text)


def get_classifier_status() -> ClassifierStatus:
    """Report whether the trained artifact is loadable, for the readiness probe.

    Loading is best-effort by design (FR-012, Spec 006): a missing/incompatible
    artifact never blocks message creation — it only changes what /health reports.
    """
    resolved = _resolved_artifact_path()
    return ClassifierStatus(
        loaded=_load_model() is not None,
        model_version=settings.intent_classifier_model_version,
        artifact_path=str(resolved),
        artifact_hash=_artifact_hash(resolved),
    )


def _resolved_artifact_path() -> Path:
    artifact_path = Path(settings.intent_classifier_artifact_path)
    if not artifact_path.is_absolute():
        artifact_path = _resolve_artifact_path(artifact_path)
    return artifact_path


@lru_cache(maxsize=1)
def _artifact_hash(path: Path) -> str | None:
    try:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        return None


@lru_cache(maxsize=1)
def _load_model() -> Any | None:
    artifact_path = _resolved_artifact_path()

    try:
        import joblib

        return joblib.load(artifact_path)
    except Exception:
        return None


def _resolve_artifact_path(path: Path) -> Path:
    candidates = [
        Path.cwd() / path,
        Path(__file__).resolve().parents[3] / path,
        Path(__file__).resolve().parents[2] / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _predict_confidence(model: Any, text: str, label: str) -> float:
    if not hasattr(model, "predict_proba"):
        return 1.0

    probabilities = model.predict_proba([text])[0]
    classes = [str(item) for item in getattr(model, "classes_", [])]
    if classes and label in classes:
        return _clamp_probability(float(probabilities[classes.index(label)]))
    return _clamp_probability(float(max(probabilities)))


def _clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


_GUEST_COUNT_OPERATIONAL_PATTERNS = (
    r"\bextra\s+guests?\b",
    r"\badditional\s+guests?\b",
    r"\bmore\s+guests?\b",
    r"\badd(?:ing)?\s+\d+\s+(?:more\s+|additional\s+|extra\s+)?guests?\b",
    r"\badd(?:ing)?\s+(?:more\s+|additional\s+|extra\s+)?guests?\b",
    r"\bincrease\s+(?:the\s+)?(?:guest\s+count|guests?)\b",
    r"\bguest\s+count\b",
    r"\bheadcount\b",
    r"\b(?:venue|catering|seating)\s+capacity\b",
    r"\bcapacity\s+for\s+\d+\s+guests?\b",
    r"\bhandle\s+\d+\s+(?:more\s+|additional\s+|extra\s+)?guests?\b",
)


def _guest_count_operational_classification(text: str) -> IntentClassification | None:
    normalized = text.lower()
    if any(re.search(pattern, normalized) for pattern in _GUEST_COUNT_OPERATIONAL_PATTERNS):
        return IntentClassification(label="guest_count_change", confidence=0.9, used_fallback=True)
    return None


_HUMAN_ESCALATION_PATTERNS = (
    r"\bspeak\s+to\s+(?:a\s+)?manager\b",
    r"\btalk\s+to\s+(?:a\s+)?manager\b",
    r"\bmanager\s+(?:directly|immediately|now)\b",
    r"\bhuman\b",
)
_COMPLAINT_PRIORITY_TERMS = (
    "complaint",
    "unhappy",
    "upset",
    "disappointed",
    "unacceptable",
    "bad service",
)


def _high_risk_operational_classification(text: str) -> IntentClassification | None:
    normalized = text.lower()
    if any(re.search(pattern, normalized) for pattern in _HUMAN_ESCALATION_PATTERNS):
        return IntentClassification(label="human_escalation", confidence=0.9, used_fallback=True)
    if any(term in normalized for term in _COMPLAINT_PRIORITY_TERMS):
        return IntentClassification(label="complaint", confidence=0.85, used_fallback=True)
    return None


def _fallback_classify(text: str) -> IntentClassification:
    """Rule-based fallback used only when the trained artifact cannot be used."""
    normalized = text.lower()
    guest_count = _guest_count_operational_classification(text)
    if guest_count is not None:
        return guest_count
    high_risk = _high_risk_operational_classification(text)
    if high_risk is not None:
        return high_risk
    rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("human_escalation", ("human", "manager", "supervisor", "agent", "person")),
        ("cancellation_request", ("cancel", "cancellation")),
        ("payment_issue", ("payment", "deposit", "refund", "invoice", "paid", "charge")),
        ("complaint", ("complaint", "unhappy", "upset", "disappointed", "bad service", "unacceptable")),
        ("guest_count_change", ("guest count", "number of guests", "more guests", "fewer guests")),
        ("urgent_change", ("urgent", "asap", "today", "tomorrow", "change the time", "last minute")),
        ("pricing_request", ("price", "pricing", "cost", "quote", "package", "packages", "how much")),
        ("availability_question", ("available", "availability", "free on", "date open")),
        ("service_question", ("service", "services", "offer", "options", "included")),
        ("booking_inquiry", ("book", "booking", "reserve", "reservation")),
    )
    for label, keywords in rules:
        if any(keyword in normalized for keyword in keywords):
            return IntentClassification(label=label, confidence=0.55, used_fallback=True)
    return IntentClassification(label="other", confidence=0.2, used_fallback=True)
