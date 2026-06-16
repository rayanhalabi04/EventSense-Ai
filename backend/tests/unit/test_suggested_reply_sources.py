"""Unit tests for RAG-source deduplication in suggested-reply generation.

RAG retrieval can return several chunks from the same document. The suggested
reply should surface each document only once (keeping the highest-scoring chunk)
while still listing every *distinct* document and preserving ranking order.
"""
from uuid import uuid4

from app.services.rag_service import RagResult, RagSource
from app.services.suggested_reply_service import generate_reply_text


def _source(
    *,
    document_id,
    title: str,
    content: str,
    score: float,
    document_type: str = "deposit_policy",
    chunk_index: int = 0,
) -> RagSource:
    return RagSource(
        document_id=document_id,
        document_title=title,
        document_type=document_type,
        content=content,
        score=score,
        chunk_index=chunk_index,
        metadata={},
    )


def test_repeated_document_collapses_to_single_source() -> None:
    document_id = uuid4()
    rag_result = RagResult(
        query="Is the deposit refundable after booking confirmation?",
        answer_supported=True,
        sources=[
            _source(document_id=document_id, title="Deposit Policy", content="chunk one", score=0.91, chunk_index=0),
            _source(document_id=document_id, title="Deposit Policy", content="chunk two", score=0.74, chunk_index=1),
            _source(document_id=document_id, title="Deposit Policy", content="chunk three", score=0.61, chunk_index=2),
        ],
    )

    generated = generate_reply_text(
        rag_result=rag_result,
        message_body="Is the deposit refundable after booking confirmation?",
        risk_level="low",
    )

    assert generated.answer_supported is True
    # Requirement 1: each document appears once in rag_sources.
    assert len(generated.rag_sources) == 1
    assert generated.rag_sources[0]["document_id"] == str(document_id)


def test_source_document_ids_are_unique() -> None:
    document_id = uuid4()
    rag_result = RagResult(
        query="deposit",
        answer_supported=True,
        sources=[
            _source(document_id=document_id, title="Deposit Policy", content="a", score=0.9),
            _source(document_id=document_id, title="Deposit Policy", content="b", score=0.8),
            _source(document_id=document_id, title="Deposit Policy", content="c", score=0.7),
        ],
    )

    generated = generate_reply_text(
        rag_result=rag_result,
        message_body="deposit question",
        risk_level=None,
    )

    # Requirement 2: source_document_ids contains unique document IDs.
    assert generated.source_document_ids == [str(document_id)]
    assert len(generated.source_document_ids) == len(set(generated.source_document_ids))


def test_highest_scoring_chunk_is_kept_for_each_document() -> None:
    document_id = uuid4()
    rag_result = RagResult(
        query="deposit",
        answer_supported=True,
        sources=[
            # Deliberately out of score order to prove we keep the *best*, not the first.
            _source(document_id=document_id, title="Deposit Policy", content="low score chunk", score=0.40),
            _source(document_id=document_id, title="Deposit Policy", content="best score chunk", score=0.95),
            _source(document_id=document_id, title="Deposit Policy", content="mid score chunk", score=0.60),
        ],
    )

    generated = generate_reply_text(
        rag_result=rag_result,
        message_body="deposit question",
        risk_level=None,
    )

    # Requirement 3: the kept source is the highest-score source for the document.
    assert len(generated.rag_sources) == 1
    assert generated.rag_sources[0]["score"] == 0.95
    assert generated.rag_sources[0]["content"] == "best score chunk"


def test_distinct_documents_are_all_kept_in_best_score_order() -> None:
    doc_a = uuid4()
    doc_b = uuid4()
    doc_c = uuid4()
    rag_result = RagResult(
        query="deposit and cancellation",
        answer_supported=True,
        sources=[
            _source(document_id=doc_a, title="Deposit Policy", content="a1", score=0.90),
            _source(document_id=doc_b, title="Cancellation Policy", content="b1", score=0.80, document_type="cancellation_policy"),
            _source(document_id=doc_a, title="Deposit Policy", content="a2", score=0.70),  # duplicate of A
            _source(document_id=doc_c, title="FAQ", content="c1", score=0.85, document_type="faq"),
        ],
    )

    generated = generate_reply_text(
        rag_result=rag_result,
        message_body="deposit and cancellation question",
        risk_level=None,
    )

    # Requirement 4: distinct documents are all preserved (one entry each)...
    kept_ids = [source["document_id"] for source in generated.rag_sources]
    assert kept_ids == [str(doc_a), str(doc_c), str(doc_b)]  # ordered by best score desc
    assert generated.source_document_ids == [str(doc_a), str(doc_c), str(doc_b)]
    assert len(kept_ids) == len(set(kept_ids))


def test_refusal_behavior_is_unchanged_when_unsupported() -> None:
    # Requirement 5: existing refusal behavior is unchanged.
    rag_result = RagResult(
        query="book my honeymoon flight",
        answer_supported=False,
        sources=[],
        refusal_reason="No supporting documents.",
    )

    generated = generate_reply_text(
        rag_result=rag_result,
        message_body="Can you book my honeymoon flight?",
        risk_level=None,
    )

    assert generated.answer_supported is False
    assert generated.rag_sources == []
    assert generated.source_document_ids == []
    assert generated.refusal_reason is not None


def test_single_source_grounded_reply_is_unchanged() -> None:
    # Requirement 5: a normal single-document grounded reply is unaffected.
    document_id = uuid4()
    rag_result = RagResult(
        query="Is the deposit refundable after booking confirmation?",
        answer_supported=True,
        sources=[
            _source(
                document_id=document_id,
                title="Deposit Policy",
                content="The booking deposit is non-refundable after booking confirmation.",
                score=0.92,
            )
        ],
    )

    generated = generate_reply_text(
        rag_result=rag_result,
        message_body="Is the deposit refundable after booking confirmation?",
        risk_level="low",
    )

    assert generated.answer_supported is True
    assert generated.source_document_ids == [str(document_id)]
    assert len(generated.rag_sources) == 1
    assert "non-refundable after booking confirmation" in generated.suggested_text.lower()


def test_faq_question_heading_is_not_exposed_in_guest_count_reply() -> None:
    document_id = uuid4()
    rag_result = RagResult(
        query="Can someone confirm if venue and catering can handle extra guests?",
        answer_supported=True,
        sources=[
            _source(
                document_id=document_id,
                title="Faq",
                document_type="faq",
                content=(
                    "Q: Can I change my guest count after booking? A: Guest count "
                    "changes usually need to be confirmed at least 10 days before "
                    "the event."
                ),
                score=0.92,
            )
        ],
    )

    generated = generate_reply_text(
        rag_result=rag_result,
        message_body="Can someone confirm if venue and catering can handle extra guests?",
        risk_level="medium",
    )

    assert generated.answer_supported is True
    assert "guest count changes usually need to be confirmed" in generated.suggested_text.lower()
    assert "according to our" not in generated.suggested_text.lower()
    assert "faq:" not in generated.suggested_text.lower()
    assert "q: can i" not in generated.suggested_text.lower()
    assert "a:" not in generated.suggested_text.lower()


def test_package_reply_uses_source_content_without_document_label() -> None:
    document_id = uuid4()
    rag_result = RagResult(
        query="What does the premium package include?",
        answer_supported=True,
        sources=[
            _source(
                document_id=document_id,
                title="Wedding Package FAQ",
                document_type="package",
                content=(
                    "Q: What does the Premium Package include? A: Our Premium "
                    "Package includes venue decoration, catering coordination, "
                    "and photography coordination."
                ),
                score=0.91,
            )
        ],
    )

    generated = generate_reply_text(
        rag_result=rag_result,
        message_body="Hi, can you send me your wedding package prices for 150 guests?",
        risk_level="low",
    )

    assert generated.answer_supported is True
    assert "premium package includes venue decoration" in generated.suggested_text.lower()
    assert "based on our" not in generated.suggested_text.lower()
    assert "wedding package faq:" not in generated.suggested_text.lower()
    assert "q:" not in generated.suggested_text.lower()
