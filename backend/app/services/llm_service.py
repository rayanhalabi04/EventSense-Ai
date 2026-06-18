from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import settings
from app.services.guardrail_service import redact_pii


@dataclass(frozen=True)
class LLMReplyRequest:
    client_message: str
    intent_label: str | None
    risk_level: str | None
    risk_reason: str | None
    rag_sources: list[dict[str, object]]
    conversation_memory: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class LLMReplyResponse:
    text: str
    model: str


@dataclass(frozen=True)
class LLMSmallTalkRequest:
    client_message: str


class LLMClient(Protocol):
    async def generate_suggested_reply(self, request: LLMReplyRequest) -> LLMReplyResponse:
        ...

    async def generate_safe_small_talk_reply(
        self,
        request: LLMSmallTalkRequest,
    ) -> LLMReplyResponse:
        ...


class OpenAIChatClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")

    async def generate_suggested_reply(self, request: LLMReplyRequest) -> LLMReplyResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_prompt(request)},
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        return LLMReplyResponse(text=str(text).strip(), model=self.model)

    async def generate_safe_small_talk_reply(
        self,
        request: LLMSmallTalkRequest,
    ) -> LLMReplyResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _safe_small_talk_system_prompt()},
                {"role": "user", "content": _safe_small_talk_user_prompt(request)},
            ],
            "temperature": 0.2,
            "max_tokens": 60,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        return LLMReplyResponse(text=str(text).strip(), model=self.model)


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")

    async def generate_suggested_reply(self, request: LLMReplyRequest) -> LLMReplyResponse:
        payload = {
            "systemInstruction": {"parts": [{"text": _system_prompt()}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": _user_prompt(request)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 800,
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                json=payload,
            )
            response.raise_for_status()
        data = response.json()
        parts = data["candidates"][0]["content"].get("parts", [])
        text = "".join(str(part.get("text", "")) for part in parts).strip()
        return LLMReplyResponse(text=text, model=self.model)

    async def generate_safe_small_talk_reply(
        self,
        request: LLMSmallTalkRequest,
    ) -> LLMReplyResponse:
        payload = {
            "systemInstruction": {"parts": [{"text": _safe_small_talk_system_prompt()}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": _safe_small_talk_user_prompt(request)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 60,
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                json=payload,
            )
            response.raise_for_status()
        data = response.json()
        parts = data["candidates"][0]["content"].get("parts", [])
        text = "".join(str(part.get("text", "")) for part in parts).strip()
        return LLMReplyResponse(text=text, model=self.model)


class FakeLLMClient:
    def __init__(self, text: str, *, model: str = "fake-llm") -> None:
        self.text = text
        self.model = model
        self.requests: list[LLMReplyRequest] = []
        self.small_talk_requests: list[LLMSmallTalkRequest] = []

    async def generate_suggested_reply(self, request: LLMReplyRequest) -> LLMReplyResponse:
        self.requests.append(request)
        return LLMReplyResponse(text=self.text, model=self.model)

    async def generate_safe_small_talk_reply(
        self,
        request: LLMSmallTalkRequest,
    ) -> LLMReplyResponse:
        self.small_talk_requests.append(request)
        return LLMReplyResponse(text=self.text, model=self.model)


def get_llm_client() -> LLMClient | None:
    if not settings.llm_enabled:
        return None
    provider = settings.llm_provider.strip().lower()
    if provider == "gemini":
        if not settings.gemini_api_key.strip() or not settings.gemini_model.strip():
            return None
        return GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    if provider == "groq":
        if not settings.groq_api_key.strip() or not settings.groq_model.strip():
            return None
        return OpenAIChatClient(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            timeout_seconds=settings.llm_timeout_seconds,
            base_url="https://api.groq.com/openai/v1",
        )
    if provider == "openai":
        if not settings.openai_api_key.strip() or not settings.openai_model.strip():
            return None
        return OpenAIChatClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return None


def _system_prompt() -> str:
    return (
        "You are the client-facing assistant for EventSense AI, a wedding and event agency. "
        "Your reply is delivered directly to the client, so write it as a warm, professional "
        "message addressed to them. "
        "Use only the provided tenant document sources. Do not invent policy details, prices, "
        "dates, exceptions, availability, or commitments that are not supported by the sources. "
        "If the sources do not support a confident answer, reassure the client and let them know "
        "a member of our team will follow up. "
        "For sensitive matters (cancellations, refunds, payments, complaints), answer carefully "
        "from the sources and, where appropriate, mention that a member of our team will review "
        "their booking and follow up. "
        "Keep the message short and mobile-friendly — a few sentences at most. For pricing or "
        "package questions, summarize only the main packages by name, price, and guest limit; do "
        "not list every add-on, overtime fee, or fine-print detail unless the client specifically "
        "asks for it. "
        "Always write complete sentences and finish every sentence — never stop mid-sentence or "
        "leave a dangling clause. End the message with proper punctuation. "
        "End with one short follow-up sentence that fits the detected intent: pricing/package "
        "questions can mention helping choose the best option; cancellations should mention "
        "cancellation next steps; payment issues should mention verifying payment status; "
        "complaints should mention careful manager or team review; guest-count or urgent changes "
        "should mention reviewing what changes are possible or next steps. "
        "Never mention drafts, internal notes, staff review, approval, or that the reply was sent "
        "automatically. Do not include source citations or labels — phrase any details naturally."
    )


def _safe_small_talk_system_prompt() -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "safe_small_talk_reply.txt"
    try:
        return prompt_path.read_text(encoding="utf-8").strip()
    except OSError:
        return (
            "The message is casual/small-talk and does not require company documents. "
            "Reply as event agency staff. Keep the reply short, warm, and professional. "
            "Maximum 1 sentence. Do not mention prices, packages, availability, policies, "
            "deposits, refunds, contracts, or commitments. Do not invent facts. "
            "If unsure, return a generic polite reply."
        )


def _safe_small_talk_user_prompt(request: LLMSmallTalkRequest) -> str:
    return (
        "Client casual message:\n"
        f"{redact_pii(request.client_message)}\n\n"
        "Write only the client-facing reply."
    )


def _user_prompt(request: LLMReplyRequest) -> str:
    source_blocks = []
    for index, source in enumerate(request.rag_sources, start=1):
        source_blocks.append(
            "\n".join(
                [
                    f"Source {index}: {source.get('document_title', 'Untitled')}",
                    f"Type: {source.get('document_type', '')}",
                    f"Content: {redact_pii(str(source.get('content', '')))}",
                ]
            )
        )
    memory_blocks = []
    for index, message in enumerate(request.conversation_memory, start=1):
        memory_blocks.append(
            "\n".join(
                [
                    f"Message {index} ({message.get('direction', 'unknown')}):",
                    redact_pii(str(message.get("body", ""))),
                ]
            )
        )
    return "\n\n".join(
        [
            f"Client message:\n{redact_pii(request.client_message)}",
            f"Detected intent: {request.intent_label or 'unknown'}",
            f"Risk level: {request.risk_level or 'unknown'}",
            f"Risk reason: {redact_pii(request.risk_reason or 'none')}",
            "Recent conversation memory:\n"
            + ("\n\n".join(memory_blocks) if memory_blocks else "No recent memory available."),
            "Tenant document sources:\n" + "\n\n".join(source_blocks),
            "Write one reply to the client using only these sources. Address the client directly in a warm, professional tone, and do not mention drafts, staff review, or approval.",
        ]
    )
