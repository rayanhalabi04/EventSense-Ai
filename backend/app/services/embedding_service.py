"""Embedding backends for tenant-scoped RAG.

Two clearly separated families of embeddings live here:

* **Semantic embeddings** — produced by a real provider (Gemini or OpenAI).
  These capture meaning, so retrieval is true semantic search.
* **Deterministic fallback embeddings** — a local, offline keyword/hash vector.
  It needs no API key and keeps the demo running, but it is explicitly
  *non-semantic*: it is closer to keyword matching than to meaning. The code
  never pretends these are semantic (`is_semantic` is `False`).

The active backend is chosen once at process start from settings. The default
(`EMBEDDING_PROVIDER=fallback`) is fully offline so the app runs with no setup.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


# Backend identifiers surfaced to callers, audits and evals so it is always
# obvious whether retrieval ran on semantic or non-semantic vectors.
BACKEND_FALLBACK = "local-keyword-fallback"  # deterministic, NON-semantic
BACKEND_GEMINI = "gemini-semantic"
BACKEND_OPENAI = "openai-semantic"

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "do",
    "does",
    "for",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "the",
    "to",
    "we",
    "what",
    "when",
    "with",
    "you",
    "your",
}


class EmbeddingError(RuntimeError):
    """Raised when a semantic embedding provider cannot return a vector."""


class EmbeddingConfigError(EmbeddingError):
    """Raised when a semantic provider is selected but mis/under-configured."""


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int
    is_semantic: bool

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class DeterministicFallbackEmbeddingProvider:
    """Offline, deterministic keyword/hash embedding — NOT semantic.

    Each non-stopword token is hashed into a fixed bucket. Retrieval over these
    vectors behaves like normalized keyword matching, which is why it is only a
    safe fallback for offline/demo mode, never a substitute for real semantics.
    """

    name = BACKEND_FALLBACK
    is_semantic = False

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _TOKEN_RE.findall(text.lower()):
            if token in _STOP_WORDS:
                continue
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % self.dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(item * item for item in vector))
        if norm == 0:
            return vector
        return [item / norm for item in vector]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]


class GeminiEmbeddingProvider:
    """Semantic embeddings via the Gemini `batchEmbedContents` API (httpx)."""

    name = BACKEND_GEMINI
    is_semantic = True

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        timeout_seconds: float,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model_path = self.model if self.model.startswith("models/") else f"models/{self.model}"
        payload = {
            "requests": [
                {
                    "model": model_path,
                    "content": {"parts": [{"text": text}]},
                    "outputDimensionality": self.dimensions,
                }
                for text in texts
            ]
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/{model_path}:batchEmbedContents",
                    params={"key": self.api_key},
                    json=payload,
                )
                response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:  # network / API failure
            raise EmbeddingError(f"Gemini embedding request failed: {exc}") from exc
        vectors = [list(map(float, item.get("values", []))) for item in data.get("embeddings", [])]
        _validate_dimensions(vectors, self.dimensions, self.name)
        return vectors


class OpenAIEmbeddingProvider:
    """Semantic embeddings via the OpenAI `/embeddings` API (httpx)."""

    name = BACKEND_OPENAI
    is_semantic = True

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        timeout_seconds: float,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self.model, "input": texts, "dimensions": self.dimensions}
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"OpenAI embedding request failed: {exc}") from exc
        ordered = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [list(map(float, item.get("embedding", []))) for item in ordered]
        _validate_dimensions(vectors, self.dimensions, self.name)
        return vectors


def _validate_dimensions(vectors: list[list[float]], expected: int, provider: str) -> None:
    for vector in vectors:
        if len(vector) != expected:
            raise EmbeddingError(
                f"{provider} returned a {len(vector)}-dim vector but EMBEDDING_DIM={expected}. "
                "Set EMBEDDING_DIM to match the model and re-embed document chunks."
            )


def build_embedding_provider() -> EmbeddingProvider:
    """Select the active embedding backend from settings.

    Falls back to the deterministic (non-semantic) provider when a semantic
    provider is mis/under-configured and `EMBEDDING_FALLBACK_ENABLED` is true.
    """
    dimensions = settings.embedding_dim
    fallback = DeterministicFallbackEmbeddingProvider(dimensions)
    provider = settings.embedding_provider.strip().lower()

    if provider in ("", "fallback", "deterministic", "keyword", "local", "none"):
        return fallback

    try:
        if provider == "gemini":
            api_key = (settings.embedding_api_key or settings.gemini_api_key).strip()
            if not api_key:
                raise EmbeddingConfigError("EMBEDDING_PROVIDER=gemini but no API key configured")
            return GeminiEmbeddingProvider(
                api_key=api_key,
                model=(settings.embedding_model.strip() or "text-embedding-004"),
                dimensions=dimensions,
                timeout_seconds=settings.embedding_timeout_seconds,
            )
        if provider == "openai":
            api_key = (settings.embedding_api_key or settings.openai_api_key).strip()
            if not api_key:
                raise EmbeddingConfigError("EMBEDDING_PROVIDER=openai but no API key configured")
            return OpenAIEmbeddingProvider(
                api_key=api_key,
                model=(settings.embedding_model.strip() or "text-embedding-3-small"),
                dimensions=dimensions,
                timeout_seconds=settings.embedding_timeout_seconds,
            )
        raise EmbeddingConfigError(f"Unknown EMBEDDING_PROVIDER={provider!r}")
    except EmbeddingConfigError as exc:
        if settings.embedding_fallback_enabled:
            logger.warning(
                "Semantic embeddings unavailable (%s); using deterministic NON-semantic "
                "fallback. Set EMBEDDING_FALLBACK_ENABLED=false to fail fast instead.",
                exc,
            )
            return fallback
        raise


class EmbeddingService:
    """Thin facade over the active embedding provider."""

    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self._provider = provider or build_embedding_provider()

    @property
    def dimensions(self) -> int:
        return self._provider.dimensions

    @property
    def is_semantic(self) -> bool:
        return self._provider.is_semantic

    @property
    def backend_name(self) -> str:
        return self._provider.name

    def embed_text(self, text: str) -> list[float]:
        return self._provider.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._provider.embed_batch(list(texts))


def tokenize_for_retrieval(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOP_WORDS}


embedding_service = EmbeddingService()
