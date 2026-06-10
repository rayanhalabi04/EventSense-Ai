# EventSense AI — dockerized stack helpers (Spec 017)
.PHONY: help up down logs reset smoke ps

help:
	@echo "EventSense AI — make targets:"
	@echo "  make up      Build + start the stack (postgres, migrate, seed, api)"
	@echo "  make down    Stop the stack (DB volume preserved)"
	@echo "  make reset   Destroy DB volume and rebuild from scratch (re-migrate + re-seed)"
	@echo "  make smoke   Run the smoke test against the running stack"
	@echo "  make logs    Tail stack logs"
	@echo "  make ps      Show service status"

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
