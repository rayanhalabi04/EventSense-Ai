"""Readiness/health endpoint for the dockerized stack (Spec 017).

Reports overall status plus per-subsystem checks (db, pgvector, migration head,
classifier artifact). Returns 200 when ready, 503 when a hard dependency is
unhealthy. Never exposes secrets or env values — only subsystem states.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.services.conversation_memory_service import get_memory_status
from app.services.intent_classifier_service import get_classifier_status


router = APIRouter()

# Subsystem states that should fail the overall readiness check.
_HARD_FAIL_STATES = {"error", "missing", "stale"}


@router.get("/health")
async def health(session: AsyncSession = Depends(get_async_session)) -> JSONResponse:
    checks: dict[str, str] = {
        "db": await _check_db(session),
        "pgvector": await _check_pgvector(session),
        "migration": await _check_migration(session),
        "classifier": _check_classifier(),
        "memory": await get_memory_status(),
    }
    ready = not any(state in _HARD_FAIL_STATES for state in checks.values())
    body = {"status": "ok" if ready else "degraded", **checks}
    return JSONResponse(status_code=200 if ready else 503, content=body)


async def _check_db(session: AsyncSession) -> str:
    try:
        await session.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


async def _check_pgvector(session: AsyncSession) -> str:
    # Only meaningful on PostgreSQL; skip on other dialects (e.g. sqlite in tests).
    if _dialect(session) != "postgresql":
        return "skipped"
    try:
        result = await session.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        return "ok" if result.first() is not None else "missing"
    except Exception:
        return "error"


async def _check_migration(session: AsyncSession) -> str:
    # Compare the DB's applied revision to the latest script head.
    if _dialect(session) != "postgresql":
        return "skipped"
    try:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        applied = {row[0] for row in result.fetchall()}
    except Exception:
        return "unknown"
    if not applied:
        return "unknown"
    head = _script_head()
    if head is None:
        return "unknown"
    return "head" if head in applied else "stale"


def _check_classifier() -> str:
    return "loaded" if get_classifier_status().loaded else "missing"


def _dialect(session: AsyncSession) -> str:
    bind = session.get_bind()
    return bind.dialect.name


def _script_head() -> str | None:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        backend_dir = Path(__file__).resolve().parents[3]
        cfg = Config(str(backend_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(backend_dir / "alembic"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:
        return None
