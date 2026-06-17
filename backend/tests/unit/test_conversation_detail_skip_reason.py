from uuid import uuid4

from app.models.audit_log import AuditLog
from app.models.suggested_reply import SuggestedReply, SuggestedReplyStatus
from app.services.audit_log_service import AUDIT_EVENT_TELEGRAM_AUTO_REPLY_SKIPPED
from app.services.conversation_service import _latest_auto_reply_skip_reason


def _reply(reply_id=None) -> SuggestedReply:
    return SuggestedReply(
        id=reply_id or uuid4(),
        tenant_id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        suggested_text="Draft",
        status=SuggestedReplyStatus.draft,
        source_document_ids=[],
        rag_sources=[],
        answer_supported=False,
        generation_method="template_v1",
    )


def _skip_log(reply_id, reason: str) -> AuditLog:
    return AuditLog(
        tenant_id=uuid4(),
        event_type=AUDIT_EVENT_TELEGRAM_AUTO_REPLY_SKIPPED,
        resource_type="message",
        resource_id=str(uuid4()),
        details={"suggested_reply_id": str(reply_id), "reason": reason},
    )


def test_latest_auto_reply_skip_reason_matches_current_pending_reply_only():
    old_reply_id = uuid4()
    current = _reply()

    reason = _latest_auto_reply_skip_reason(
        current,
        [
            _skip_log(old_reply_id, "no_rag_source"),
            _skip_log(current.id, "rag_provider_unavailable"),
        ],
    )

    assert reason == "rag_provider_unavailable"


def test_latest_auto_reply_skip_reason_ignores_stale_skip_for_newer_draft():
    current = _reply()

    reason = _latest_auto_reply_skip_reason(
        current,
        [_skip_log(uuid4(), "no_rag_source")],
    )

    assert reason is None
