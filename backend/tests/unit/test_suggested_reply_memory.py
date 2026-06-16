from uuid import uuid4

import pytest

from app.services.llm_service import FakeLLMClient, _user_prompt
from app.services.rag_service import RagResult, RagSource
from app.services.conversation_memory_service import ConversationMemoryMessage
from app.services.suggested_reply_service import (
    build_contextual_rag_query,
    generate_reply_text_with_optional_llm,
)


pytestmark = pytest.mark.asyncio


async def test_contextual_rag_query_rewrites_price_followup_from_recent_memory() -> None:
    memory = [
        ConversationMemoryMessage(
            message_id=str(uuid4()),
            direction="inbound",
            body="Can we add 30 more guests to our wedding package?",
            sent_at="2026-06-16T10:00:00+00:00",
        ),
        ConversationMemoryMessage(
            message_id="current",
            direction="inbound",
            body="Will that change the price?",
            sent_at="2026-06-16T10:01:00+00:00",
        ),
    ]

    query = build_contextual_rag_query(
        "Will that change the price?",
        memory,
        current_message_id="current",
    )

    assert query == "Will adding 30 more guests to our wedding package change the price?"


async def test_contextual_rag_query_does_not_rewrite_without_prior_context() -> None:
    memory = [
        ConversationMemoryMessage(
            message_id="current",
            direction="inbound",
            body="Will that change the price?",
            sent_at="2026-06-16T10:01:00+00:00",
        )
    ]

    query = build_contextual_rag_query(
        "Will that change the price?",
        memory,
        current_message_id="current",
    )

    assert query == "Will that change the price?"


async def test_memory_is_passed_to_llm_request_and_prompt() -> None:
    document_id = uuid4()
    fake = FakeLLMClient(
        "Hi, thank you for your message. According to the deposit policy, the booking deposit is non-refundable after booking confirmation. Staff must review this before sending."
    )
    rag_result = RagResult(
        query="Is the deposit refundable?",
        answer_supported=True,
        sources=[
            RagSource(
                document_id=document_id,
                document_title="Deposit Policy",
                document_type="deposit_policy",
                content="The booking deposit is non-refundable after booking confirmation.",
                score=0.9,
                chunk_index=0,
                metadata={},
            )
        ],
    )
    memory = [
        {
            "message_id": str(uuid4()),
            "direction": "inbound",
            "body": "Earlier I asked about the outdoor venue.",
            "sent_at": "2026-06-11T10:00:00+00:00",
        }
    ]

    generated = await generate_reply_text_with_optional_llm(
        rag_result=rag_result,
        message_body="Is the deposit refundable after booking confirmation?",
        intent_label="payment_policy",
        risk_level="low",
        risk_reason=None,
        tenant_slug="elegant-weddings",
        conversation_memory=memory,
        llm_client_factory=lambda: fake,
    )

    assert generated.generation_method == "llm_v1"
    assert len(fake.requests) == 1
    assert fake.requests[0].conversation_memory == memory
    prompt = _user_prompt(fake.requests[0])
    assert "Recent conversation memory:" in prompt
    assert "Earlier I asked about the outdoor venue." in prompt
