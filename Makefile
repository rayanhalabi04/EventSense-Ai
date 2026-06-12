# EventSense AI — dockerized stack helpers (Spec 017)
.PHONY: help up down logs reset smoke ps \
	eval-ai eval-classifier eval-agent eval-guardrails eval-rag

help:
	@echo "EventSense AI — make targets:"
	@echo "  make up               Build + start the stack (postgres, migrate, seed, api)"
	@echo "  make down             Stop the stack (DB volume preserved)"
	@echo "  make reset            Destroy DB volume and rebuild from scratch (re-migrate + re-seed)"
	@echo "  make smoke            Run the smoke test against the running stack"
	@echo "  make logs             Tail stack logs"
	@echo "  make ps               Show service status"
	@echo "  make eval-ai          Run gated AI evals (classifier + agent + guardrails)"
	@echo "  make eval-classifier  Run the intent classifier eval"
	@echo "  make eval-agent       Run the dry-run agent decision eval"
	@echo "  make eval-guardrails  Run the guardrail red-team eval"
	@echo "  make eval-rag         Run the RAG retrieval eval (informational, not gated)"

up:
	docker compose up --build -d

down:
	docker compose down

reset:
	docker compose down -v
	docker compose up --build -d

smoke:
	./scripts/smoke_test.sh

logs:
	docker compose logs -f

ps:
	docker compose ps

# --- AI evaluations -------------------------------------------------------
# Run an offline eval inside the API image with the repo mounted; --no-deps
# avoids starting postgres/redis since the evals need neither. Artifacts (when a
# runner writes them) land in ./eval-artifacts on the host (gitignored).
EVAL_RUN = docker compose run --rm --no-deps -v "$(CURDIR)":/repo -w /repo api bash -lc

eval-classifier:
	$(EVAL_RUN) 'PYTHONPATH=backend:. python evals/classifier/evaluate.py'

eval-agent:
	$(EVAL_RUN) 'PYTHONPATH=backend:. python evals/agent/evaluate.py'

eval-guardrails:
	$(EVAL_RUN) 'PYTHONPATH=backend:. python evals/guardrails/evaluate.py'

eval-rag:
	$(EVAL_RUN) 'PYTHONPATH=backend:. python evals/rag/evaluate.py'

# Gated AI evals: each prerequisite exits non-zero on failure, so make stops at
# the first failing eval. (RAG is excluded — it prints metrics but does not gate.)
eval-ai: eval-classifier eval-agent eval-guardrails
