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


def test_extra_guest_capacity_message_routes_to_guest_count_even_with_model(monkeypatch):
    class AvailabilityModel:
        def predict(self, texts):
            return ["availability_question"]

        def predict_proba(self, texts):
            return [[0.99]]

        classes_ = ["availability_question"]

    monkeypatch.setattr(intent_classifier_service, "_load_model", lambda: AvailabilityModel())

    result = IntentClassifierService.classify(
        "Can someone confirm if the venue and catering team can handle 40 extra guests?"
    )

    assert result.label == "guest_count_change"
    assert result.confidence >= 0.9


def test_true_date_availability_question_stays_availability(monkeypatch):
    monkeypatch.setattr(intent_classifier_service, "_load_model", lambda: None)

    result = IntentClassifierService.classify(
        "Are you available for a wedding on August 24 for around 120 guests?"
    )

    assert result.label == "availability_question"
