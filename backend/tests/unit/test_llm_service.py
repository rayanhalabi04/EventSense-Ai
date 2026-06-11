from app.services import llm_service
from app.services.llm_service import GeminiClient, OpenAIChatClient


def test_llm_client_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "llm_enabled", False)

    assert llm_service.get_llm_client() is None


def test_llm_client_selects_gemini(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "llm_enabled", True)
    monkeypatch.setattr(llm_service.settings, "llm_provider", "gemini")
    monkeypatch.setattr(llm_service.settings, "gemini_api_key", "test-gemini-key")
    monkeypatch.setattr(llm_service.settings, "gemini_model", "gemini-test-model")

    client = llm_service.get_llm_client()

    assert isinstance(client, GeminiClient)
    assert client.model == "gemini-test-model"


def test_llm_client_selects_groq(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "llm_enabled", True)
    monkeypatch.setattr(llm_service.settings, "llm_provider", "groq")
    monkeypatch.setattr(llm_service.settings, "groq_api_key", "test-groq-key")
    monkeypatch.setattr(llm_service.settings, "groq_model", "groq-test-model")

    client = llm_service.get_llm_client()

    assert isinstance(client, OpenAIChatClient)
    assert client.model == "groq-test-model"
    assert client.base_url == "https://api.groq.com/openai/v1"


def test_llm_client_selects_openai(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "llm_enabled", True)
    monkeypatch.setattr(llm_service.settings, "llm_provider", "openai")
    monkeypatch.setattr(llm_service.settings, "openai_api_key", "test-openai-key")
    monkeypatch.setattr(llm_service.settings, "openai_model", "openai-test-model")

    client = llm_service.get_llm_client()

    assert isinstance(client, OpenAIChatClient)
    assert client.model == "openai-test-model"
    assert client.base_url == "https://api.openai.com/v1"


def test_llm_client_unknown_or_missing_config_returns_none(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "llm_enabled", True)
    monkeypatch.setattr(llm_service.settings, "llm_provider", "unknown")

    assert llm_service.get_llm_client() is None

    monkeypatch.setattr(llm_service.settings, "llm_provider", "gemini")
    monkeypatch.setattr(llm_service.settings, "gemini_api_key", "")
    monkeypatch.setattr(llm_service.settings, "gemini_model", "gemini-test-model")

    assert llm_service.get_llm_client() is None
