from app.services import intent_classifier_service
from app.services.intent_classifier_service import INTENT_LABELS, IntentClassifierService


def test_intent_classifier_predicts_valid_label():
    result = IntentClassifierService.classify("How much does your gold wedding package cost?")

    assert result.label in INTENT_LABELS
    assert result.label == "pricing_request"
    assert 0.0 <= result.confidence <= 1.0


def test_intent_classifier_fallback_predicts_valid_label(monkeypatch):
    monkeypatch.setattr(intent_classifier_service, "_load_model", lambda: None)

    result = IntentClassifierService.classify("I need to cancel my wedding booking")

    assert result.label == "cancellation_request"
    assert 0.0 <= result.confidence <= 1.0
    assert result.used_fallback is True
