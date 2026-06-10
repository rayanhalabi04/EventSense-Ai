import json
import math
from pathlib import Path

from app.services.embedding_service import embedding_service, tokenize_for_retrieval


ROOT = Path(__file__).resolve().parent
GOLDEN_SET = ROOT / "golden_set.json"

CORPUS = [
    {
        "tenant_slug": "elegant-weddings",
        "document_title": "Elegant Weddings Deposit Policy",
        "text": "Elegant Weddings deposits are refundable within seven days of payment.",
    },
    {
        "tenant_slug": "elegant-weddings",
        "document_title": "Elegant Weddings FAQ",
        "text": "Final guest count is due fourteen days before the wedding.",
    },
    {
        "tenant_slug": "royal-events-agency",
        "document_title": "Royal Events Deposit Policy",
        "text": "Royal Events deposits become non-refundable after thirty days.",
    },
    {
        "tenant_slug": "royal-events-agency",
        "document_title": "Royal Events Packages",
        "text": "The royal package includes venue coordination, lighting, catering, and decor.",
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
