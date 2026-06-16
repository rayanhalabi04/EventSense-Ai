import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_ok_with_subsystem_checks(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()

    # Overall readiness plus each subsystem state is reported.
    assert body["status"] == "ok"
    for key in ("db", "pgvector", "migration", "classifier", "memory"):
        assert key in body

    # On the sqlite test bind, pg-only checks are skipped (not failed);
    # db must be reachable and the trained classifier artifact must load.
    assert body["db"] == "ok"
    assert body["pgvector"] == "skipped"
    assert body["migration"] == "skipped"
    assert body["classifier"] == "loaded"
    assert body["memory"] == "disabled"


@pytest.mark.asyncio
async def test_health_does_not_leak_secrets(client: AsyncClient) -> None:
    response = await client.get("/health")
    raw = response.text.lower()

    # The readiness probe reports states only — never secret/config values.
    for forbidden in ("secret", "password", "jwt", "database_url", "token"):
        assert forbidden not in raw
