import json
import math
from pathlib import Path

from app.services.embedding_service import embedding_service, tokenize_for_retrieval


ROOT = Path(__file__).resolve().parent
GOLDEN_SET = ROOT / "golden_set.json"

# Offline retrieval corpus. These short, fictional snippets mirror the demo RAG
# document packs in demo_data/rag_documents/ so the golden set can be scored
# without a running database. They are intentionally different between tenants to
# exercise tenant-scoped isolation.
CORPUS = [
    {
        "tenant_slug": "elegant-weddings",
        "document_title": "Elegant Weddings Deposit Policy",
        "text": (
            "The Elegant Weddings booking deposit is non-refundable after booking "
            "confirmation. The deposit confirms the wedding date only after payment "
            "is received and recorded."
        ),
    },
    {
        "tenant_slug": "elegant-weddings",
        "document_title": "Elegant Weddings Guest Count Policy",
        "text": (
            "Elegant Weddings guest count changes must be confirmed at least ten "
            "days before the event. Increases after the deadline require manager "
            "approval and may affect catering availability."
        ),
    },
    {
        "tenant_slug": "elegant-weddings",
        "document_title": "Elegant Weddings Pricing & Packages",
        "text": (
            "The Elegant Weddings Premium package includes decoration, catering "
            "coordination, and photography coordination. The Gold package includes "
            "planning support and vendor coordination."
        ),
    },
    {
        "tenant_slug": "elegant-weddings",
        "document_title": "Elegant Weddings FAQ",
        "text": (
            "Elegant Weddings does not provide guest airport transportation unless "
            "it is added as a custom service. The final balance is due fourteen days "
            "before the wedding."
        ),
    },
    {
        "tenant_slug": "royal-events-agency",
        "document_title": "Royal Events Deposit Policy",
        "text": (
            "The Royal Events deposit is partially refundable if cancellation "
            "happens more than thirty days before the event, and non-refundable if "
            "cancellation happens within thirty days of the event."
        ),
    },
    {
        "tenant_slug": "royal-events-agency",
        "document_title": "Royal Events Guest Count Policy",
        "text": (
            "Royal Events guest count changes are allowed up to seven days before "
            "the event. Increases after the seven day deadline require catering and "
            "venue approval."
        ),
    },
    {
        "tenant_slug": "royal-events-agency",
        "document_title": "Royal Events Pricing & Packages",
        "text": (
            "The Royal Events Luxury package includes decoration, catering, "
            "lighting, and bridal entrance setup. The Royal Signature package "
            "includes premium theme design and stage lighting."
        ),
    },
    {
        "tenant_slug": "royal-events-agency",
        "document_title": "Royal Events FAQ",
        "text": (
            "Royal Events can arrange VIP guest airport transportation only as a "
            "paid add-on. The final balance is due ten days before the event."
        ),
    },
]


def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def retrieve(question: str, tenant_slug: str, top_k: int = 3) -> list[dict[str, object]]:
    query_embedding = embedding_service.embed_text(question)
    query_tokens = tokenize_for_retrieval(question)
    ranked = sorted(
        (
            {
                **doc,
                "score": cosine(query_embedding, embedding_service.embed_text(doc["text"])),
            }
            for doc in CORPUS
            if doc["tenant_slug"] == tenant_slug
            and query_tokens.intersection(tokenize_for_retrieval(doc["text"]))
        ),
        key=lambda item: item["score"],
        reverse=True,
    )
    return [item for item in ranked[:top_k] if item["score"] >= 0.08]


def main() -> None:
    cases = json.loads(GOLDEN_SET.read_text())
    hits = 0
    reciprocal_rank_total = 0.0
    refusal_correct = 0
    isolation_correct = 0

    for case in cases:
        sources = retrieve(case["question"], case["tenant_slug"])
        titles = [source["document_title"] for source in sources]
        expected = case["expected_document_title"]
        refused = not sources

        if case["should_refuse"]:
            refusal_correct += int(refused)
        elif expected in titles:
            rank = titles.index(expected) + 1
            hits += 1
            reciprocal_rank_total += 1 / rank

        isolation_correct += int(
            all(source["tenant_slug"] == case["tenant_slug"] for source in sources)
        )

    answerable = [case for case in cases if not case["should_refuse"]]
    print(
        json.dumps(
            {
                "hit_at_3": hits / len(answerable),
                "mrr": reciprocal_rank_total / len(answerable),
                "refusal_accuracy": refusal_correct
                / len([case for case in cases if case["should_refuse"]]),
                "tenant_isolation_accuracy": isolation_correct / len(cases),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
