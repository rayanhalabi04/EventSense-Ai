# RAG Evaluation Scaffold

This folder contains a small golden set and an offline evaluation script for the
Feature 009 retrieval foundation.

Current metrics:

- `hit@k`: whether the expected document appears in the top-k sources
- `MRR`: reciprocal rank of the expected document
- no-source/refusal correctness
- tenant isolation correctness

Later RAGAS-style metrics can be added once answer generation exists:

- context precision
- context recall
- faithfulness
- response relevancy

Run from the repository root:

```bash
PYTHONPATH=backend:. python evals/rag/evaluate.py
```
