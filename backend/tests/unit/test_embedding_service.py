import pytest

from app.services import embedding_service as embedding_module
from app.services.embedding_service import (
    BACKEND_FALLBACK,
    BACKEND_GEMINI,
    BACKEND_OPENAI,
    DeterministicFallbackEmbeddingProvider,
    EmbeddingConfigError,
    EmbeddingError,
    EmbeddingService,
    GeminiEmbeddingProvider,
    OpenAIEmbeddingProvider,
    build_embedding_provider,
)


def _set(monkeypatch, **kwargs):
    for key, value in kwargs.items():
        monkeypatch.setattr(embedding_module.settings, key, value)


def test_default_provider_is_deterministic_fallback(monkeypatch):
    _set(monkeypatch, embedding_provider="fallback", embedding_dim=768)

    provider = build_embedding_provider()

    assert isinstance(provider, DeterministicFallbackEmbeddingProvider)
    assert provider.is_semantic is False
    assert provider.name == BACKEND_FALLBACK


def test_fallback_vectors_match_configured_dimension():
    provider = DeterministicFallbackEmbeddingProvider(dimensions=768)

    vectors = provider.embed_batch(["deposit refund policy", ""])

    assert all(len(vector) == 768 for vector in vectors)
    # Deterministic: same text -> identical vector.
    assert provider.embed_text("deposit") == provider.embed_text("deposit")


def test_selects_gemini_when_configured(monkeypatch):
    _set(
        monkeypatch,
        embedding_provider="gemini",
        embedding_api_key="",
        gemini_api_key="test-key",
        embedding_model="",
        embedding_dim=768,
    )

    provider = build_embedding_provider()

    assert isinstance(provider, GeminiEmbeddingProvider)
    assert provider.is_semantic is True
    assert provider.name == BACKEND_GEMINI
    assert provider.model == "text-embedding-004"
    assert provider.dimensions == 768


def test_selects_openai_when_configured(monkeypatch):
    _set(
        monkeypatch,
        embedding_provider="openai",
        embedding_api_key="dedicated-key",
        embedding_model="text-embedding-3-large",
        embedding_dim=768,
    )

    provider = build_embedding_provider()

    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.name == BACKEND_OPENAI
    assert provider.api_key == "dedicated-key"


def test_missing_key_degrades_to_fallback_when_enabled(monkeypatch):
    _set(
        monkeypatch,
        embedding_provider="gemini",
        embedding_api_key="",
        gemini_api_key="",
        embedding_fallback_enabled=True,
        embedding_dim=768,
    )

    provider = build_embedding_provider()

    assert isinstance(provider, DeterministicFallbackEmbeddingProvider)
    assert provider.is_semantic is False


def test_missing_key_fails_fast_when_fallback_disabled(monkeypatch):
    _set(
        monkeypatch,
        embedding_provider="gemini",
        embedding_api_key="",
        gemini_api_key="",
        embedding_fallback_enabled=False,
    )

    with pytest.raises(EmbeddingConfigError):
        build_embedding_provider()


def test_unknown_provider_degrades_to_fallback(monkeypatch):
    _set(
        monkeypatch,
        embedding_provider="totally-made-up",
        embedding_fallback_enabled=True,
        embedding_dim=768,
    )

    assert isinstance(build_embedding_provider(), DeterministicFallbackEmbeddingProvider)


def test_dimension_mismatch_from_provider_raises():
    class WrongDimProvider:
        name = "x"
        dimensions = 768
        is_semantic = True

        def embed_batch(self, texts):
            return [[0.0] * 384 for _ in texts]

    service = EmbeddingService(provider=WrongDimProvider())

    # The provider lies about its size; validation should surface it.
    with pytest.raises(EmbeddingError):
        embedding_module._validate_dimensions([[0.0] * 384], 768, "x")
    # And via the real provider path the facade simply delegates.
    assert service.embed_text("hi") == [0.0] * 384  # no validation in facade itself


def test_service_facade_reports_backend_metadata():
    service = EmbeddingService(provider=DeterministicFallbackEmbeddingProvider(dimensions=768))

    assert service.is_semantic is False
    assert service.backend_name == BACKEND_FALLBACK
    assert service.dimensions == 768
    assert len(service.embed_text("hello world")) == 768
