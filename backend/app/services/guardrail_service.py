import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


SAFE_REFUSAL = "The request cannot be handled because it violates safety or tenant-isolation rules."

ACTION_ALLOW = "allow"
ACTION_BLOCK = "block"
ACTION_REDACT = "redact"
ACTION_REFUSE = "refuse"

FLAG_PROMPT_INJECTION = "prompt_injection"
FLAG_SYSTEM_PROMPT_REQUEST = "system_prompt_request"
FLAG_CROSS_TENANT_REQUEST = "cross_tenant_request"
FLAG_UNSUPPORTED_OR_OFF_TOPIC = "unsupported_or_off_topic"
FLAG_PII_DETECTED = "pii_detected"

FLAG_PII_IN_RETRIEVED_CONTEXT = "pii_in_retrieved_context"
FLAG_SUSPICIOUS_RETRIEVED_INSTRUCTION = "suspicious_retrieved_instruction"
FLAG_CROSS_TENANT_CONTEXT_DETECTED = "cross_tenant_context_detected"

FLAG_PII_IN_OUTPUT = "pii_in_output"
FLAG_UNSUPPORTED_CLAIM = "unsupported_claim"
FLAG_SYSTEM_PROMPT_LEAK = "system_prompt_leak"
FLAG_CROSS_TENANT_LEAK = "cross_tenant_leak"

@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    action: str
    reason: str | None = None
    flags: list[str] | None = None
    sanitized_text: str | None = None

    def with_flag(self, flag: str) -> "GuardrailResult":
        flags = list(self.flags or [])
        if flag not in flags:
            flags.append(flag)
        return replace(self, flags=flags)


@dataclass(frozen=True)
class RetrievalGuardrailResult:
    result: GuardrailResult
    sources: list[dict[str, object]]


_PROMPT_INJECTION_PATTERNS = (
    r"\bignore (all )?(previous|prior|above) instructions\b",
    r"\bignore your rules\b",
    r"\bbypass your instructions\b",
    r"\bjailbreak\b",
    r"\bdeveloper message\b",
    r"\byou are now\b",
)

_SYSTEM_PROMPT_PATTERNS = (
    r"\bsystem prompt\b",
    r"\breveal your prompt\b",
    r"\bshow me your hidden instructions\b",
    r"\bhidden system prompt\b",
    r"\bhidden instructions\b",
)

_UNSUPPORTED_OR_DANGEROUS_PATTERNS = (
    r"\bexport all client data\b",
    r"\bdelete all records\b",
    r"\bdelete every record\b",
    r"\bdrop (the )?database\b",
    r"\bsend (all )?data to\b",
)

_SUSPICIOUS_RETRIEVED_PATTERNS = (
    r"\bignore (all )?(previous|prior|above) instructions\b",
    r"\byou are now\b",
    r"\breveal (the )?system prompt\b",
    r"\bsend data to\b",
    r"\bdeveloper message\b",
)

_EMAIL_RE = re.compile(r"(?:mailto:)?[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?961[\s.-]?)?(?:0?3|0?7[01689]|0?8[18]|0?9|01|04|05|06)[\s.-]?\d{3}[\s.-]?\d{3,4}(?!\w)"
)
_LONG_NUMBER_RE = re.compile(r"(?<!\w)(?:\d[\s-]?){12,19}(?!\w)")

_TENANT_ALIASES = {
    "elegant-weddings": ("elegant weddings", "elegant"),
    "royal-events-agency": ("royal events agency", "royal events", "royal"),
}


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _append_flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def sanitize_text(text: str) -> tuple[str, list[str]]:
    redacted = _EMAIL_RE.sub("<EMAIL>", text)
    redacted = _PHONE_RE.sub("<PHONE>", redacted)
    redacted = _LONG_NUMBER_RE.sub("<NUMBER>", redacted)
    flags: list[str] = []
    if redacted != text:
        flags.append(FLAG_PII_DETECTED)
    return redacted, flags


def redact_pii(text: str) -> str:
    return sanitize_text(text)[0]


def is_prompt_injection(text: str) -> bool:
    return _matches_any(text, _PROMPT_INJECTION_PATTERNS)


def is_system_prompt_request(text: str) -> bool:
    return _matches_any(text, _SYSTEM_PROMPT_PATTERNS)


def contains_cross_tenant_request(text: str, tenant_slug: str | None = None) -> bool:
    lower = text.lower()
    if any(
        phrase in lower
        for phrase in (
            "act as another tenant",
            "another agency's clients",
            "another agency clients",
            "tenant b policy",
            "other tenant",
            "cross tenant",
        )
    ):
        return True

    for slug, aliases in _TENANT_ALIASES.items():
        if tenant_slug == slug:
            continue
        if any(alias in lower for alias in aliases) and any(
            keyword in lower for keyword in ("document", "policy", "client", "deposit", "cancellation")
        ):
            return True
    return False


def _tenant_leak_flag(text: str, tenant_slug: str | None) -> bool:
    return contains_cross_tenant_request(text, tenant_slug)


def check_input_guardrails(text: str, tenant_slug: str | None = None) -> GuardrailResult:
    sanitized, sanitize_flags = sanitize_text(text)
    flags = list(sanitize_flags)

    if is_prompt_injection(text):
        _append_flag(flags, FLAG_PROMPT_INJECTION)
    if is_system_prompt_request(text):
        _append_flag(flags, FLAG_SYSTEM_PROMPT_REQUEST)
    if contains_cross_tenant_request(text, tenant_slug):
        _append_flag(flags, FLAG_CROSS_TENANT_REQUEST)
    if _matches_any(text, _UNSUPPORTED_OR_DANGEROUS_PATTERNS):
        _append_flag(flags, FLAG_UNSUPPORTED_OR_OFF_TOPIC)

    block_flags = {
        FLAG_PROMPT_INJECTION,
        FLAG_SYSTEM_PROMPT_REQUEST,
        FLAG_CROSS_TENANT_REQUEST,
        FLAG_UNSUPPORTED_OR_OFF_TOPIC,
    }
    if any(flag in block_flags for flag in flags):
        return GuardrailResult(
            allowed=False,
            action=ACTION_REFUSE,
            reason=SAFE_REFUSAL,
            flags=flags,
            sanitized_text=sanitized,
        )
    if sanitized != text:
        return GuardrailResult(
            allowed=True,
            action=ACTION_REDACT,
            reason="PII was redacted before processing.",
            flags=flags,
            sanitized_text=sanitized,
        )
    return GuardrailResult(allowed=True, action=ACTION_ALLOW, flags=[], sanitized_text=text)


def check_retrieval_guardrails(
    sources: list[dict[str, object]],
    tenant_slug: str | None = None,
) -> RetrievalGuardrailResult:
    flags: list[str] = []
    sanitized_sources: list[dict[str, object]] = []

    for source in sources:
        content = str(source.get("content", ""))
        if _matches_any(content, _SUSPICIOUS_RETRIEVED_PATTERNS):
            _append_flag(flags, FLAG_SUSPICIOUS_RETRIEVED_INSTRUCTION)
            continue
        if _tenant_leak_flag(content, tenant_slug):
            _append_flag(flags, FLAG_CROSS_TENANT_CONTEXT_DETECTED)
            continue

        redacted, pii_flags = sanitize_text(content)
        if pii_flags:
            _append_flag(flags, FLAG_PII_IN_RETRIEVED_CONTEXT)
        copied = dict(source)
        copied["content"] = redacted
        sanitized_sources.append(copied)

    if not sanitized_sources and sources:
        return RetrievalGuardrailResult(
            result=GuardrailResult(
                allowed=False,
                action=ACTION_REFUSE,
                reason="Retrieved context was blocked by retrieval guardrails.",
                flags=flags,
            ),
            sources=[],
        )
    if flags:
        return RetrievalGuardrailResult(
            result=GuardrailResult(
                allowed=True,
                action=ACTION_REDACT if FLAG_PII_IN_RETRIEVED_CONTEXT in flags else ACTION_BLOCK,
                reason="Retrieved context was sanitized by retrieval guardrails.",
                flags=flags,
            ),
            sources=sanitized_sources,
        )
    return RetrievalGuardrailResult(
        result=GuardrailResult(allowed=True, action=ACTION_ALLOW, flags=[]),
        sources=sanitized_sources,
    )


def check_output_guardrails(
    text: str,
    rag_sources: list[dict[str, object]] | None = None,
    tenant_slug: str | None = None,
) -> GuardrailResult:
    sanitized, sanitize_flags = sanitize_text(text)
    flags: list[str] = []
    if sanitize_flags:
        _append_flag(flags, FLAG_PII_IN_OUTPUT)
    if is_system_prompt_request(text) or "developer message" in text.lower():
        _append_flag(flags, FLAG_SYSTEM_PROMPT_LEAK)
    if _tenant_leak_flag(text, tenant_slug):
        _append_flag(flags, FLAG_CROSS_TENANT_LEAK)

    blocking_flags = {FLAG_SYSTEM_PROMPT_LEAK, FLAG_CROSS_TENANT_LEAK, FLAG_UNSUPPORTED_CLAIM}
    if any(flag in blocking_flags for flag in flags):
        return GuardrailResult(
            allowed=False,
            action=ACTION_REFUSE,
            reason=SAFE_REFUSAL,
            flags=flags,
            sanitized_text=sanitized,
        )
    if FLAG_PII_IN_OUTPUT in flags:
        return GuardrailResult(
            allowed=True,
            action=ACTION_REDACT,
            reason="PII was redacted from output.",
            flags=flags,
            sanitized_text=sanitized,
        )
    return GuardrailResult(allowed=True, action=ACTION_ALLOW, flags=[], sanitized_text=text)


def apply_guardrails_to_suggested_reply(
    *,
    suggested_text: str,
    rag_sources: list[dict[str, object]],
    answer_supported: bool,
    refusal_reason: str | None,
    tenant_slug: str | None = None,
) -> tuple[str, list[dict[str, object]], bool, str | None, list[GuardrailResult]]:
    retrieval = check_retrieval_guardrails(rag_sources, tenant_slug)
    events = [retrieval.result] if retrieval.result.flags else []
    if not retrieval.result.allowed:
        return SAFE_REFUSAL, [], False, retrieval.result.reason, events

    output = check_output_guardrails(suggested_text, retrieval.sources, tenant_slug)
    if output.flags:
        events.append(output)
    if not output.allowed:
        return SAFE_REFUSAL, retrieval.sources, False, output.reason, events
    return (
        output.sanitized_text or suggested_text,
        retrieval.sources,
        answer_supported,
        refusal_reason,
        events,
    )


def audit_guardrail_event(
    session: "AsyncSession",
    *,
    tenant_id: UUID,
    rail_type: str,
    result: GuardrailResult,
    actor_user_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: UUID | str | None = None,
    conversation_id: UUID | None = None,
    message_id: UUID | None = None,
    suggested_reply_id: UUID | None = None,
    original_text: str | None = None,
) -> None:
    from app.services.audit_log_service import AuditLogService

    if not result.flags:
        return
    event_type = _event_type_for(rail_type, result)
    AuditLogService.record(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        resource_type=resource_type or "guardrail",
        resource_id=resource_id,
        details={
            "rail_type": rail_type,
            "action": result.action,
            "flags": result.flags,
            "reason": result.reason,
            "redacted": result.sanitized_text is not None and result.sanitized_text != original_text,
            "sanitized_text": result.sanitized_text,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "suggested_reply_id": suggested_reply_id,
        },
    )


def _event_type_for(rail_type: str, result: GuardrailResult) -> str:
    from app.services.audit_log_service import (
        AUDIT_EVENT_GUARDRAIL_CROSS_TENANT_BLOCKED,
        AUDIT_EVENT_GUARDRAIL_INPUT_BLOCKED,
        AUDIT_EVENT_GUARDRAIL_INPUT_REDACTED,
        AUDIT_EVENT_GUARDRAIL_OUTPUT_BLOCKED,
        AUDIT_EVENT_GUARDRAIL_OUTPUT_REDACTED,
        AUDIT_EVENT_GUARDRAIL_RETRIEVAL_BLOCKED,
        AUDIT_EVENT_GUARDRAIL_RETRIEVAL_REDACTED,
        AUDIT_EVENT_GUARDRAIL_SYSTEM_PROMPT_BLOCKED,
    )

    flags = set(result.flags or [])
    if FLAG_CROSS_TENANT_REQUEST in flags or FLAG_CROSS_TENANT_LEAK in flags:
        return AUDIT_EVENT_GUARDRAIL_CROSS_TENANT_BLOCKED
    if FLAG_SYSTEM_PROMPT_REQUEST in flags or FLAG_SYSTEM_PROMPT_LEAK in flags:
        return AUDIT_EVENT_GUARDRAIL_SYSTEM_PROMPT_BLOCKED
    if rail_type == "input":
        return (
            AUDIT_EVENT_GUARDRAIL_INPUT_REDACTED
            if result.action == ACTION_REDACT
            else AUDIT_EVENT_GUARDRAIL_INPUT_BLOCKED
        )
    if rail_type == "retrieval":
        return (
            AUDIT_EVENT_GUARDRAIL_RETRIEVAL_REDACTED
            if FLAG_PII_IN_RETRIEVED_CONTEXT in flags
            else AUDIT_EVENT_GUARDRAIL_RETRIEVAL_BLOCKED
        )
    return (
        AUDIT_EVENT_GUARDRAIL_OUTPUT_REDACTED
        if result.action == ACTION_REDACT
        else AUDIT_EVENT_GUARDRAIL_OUTPUT_BLOCKED
    )
