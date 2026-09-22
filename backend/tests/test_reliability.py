import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import ConnectionError
from sqlalchemy import select

from app.config import get_settings
from app.limits import limit
from app.main import app, stream
from app.models import Event
from app.security import Principal


async def test_redis_outage_fails_closed_when_required(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "redis_required", True)
    monkeypatch.setattr(app.state.redis, "eval", AsyncMock(side_effect=ConnectionError("offline")))
    response = await client.post(
        "/v1/auth/login", json={"email": "admin@alpha.test", "password": "test-password-123"}
    )
    assert response.status_code == 503


async def test_readiness_checks_dependencies(client):
    assert (await client.get("/health/ready")).status_code == 200


async def test_sse_cursor_replay_is_ordered_and_tenant_scoped(client, store, incident):
    user = store["users"]["admin"]
    identity = Principal(user.id, user.tenant_id, user.name, user.email, user.role)
    async with store["factory"]() as session, session.begin():
        initial = await session.scalar(select(Event).where(Event.tenant_id == user.tenant_id))
        first_id = initial.id
        session.add(
            Event(
                tenant_id=store["users"]["outsider"].tenant_id,
                kind="private.event",
                actor="Private",
                message="Never reveal this",
            )
        )
        await session.flush()
        event = Event(
            tenant_id=user.tenant_id,
            incident_id=incident["incident_id"],
            kind="note.added",
            actor=user.name,
            message="Resume from this event",
        )
        session.add(event)
        await session.flush()
        expected_id = event.id
    request = SimpleNamespace(app=app, is_disconnected=AsyncMock(return_value=False))
    response = await stream(request, after=0, last_event_id=first_id, user=identity)
    try:
        chunk = await anext(response.body_iterator)
        assert f"id: {expected_id}\n" in chunk
        assert "Resume from this event" in chunk
        assert "Never reveal" not in chunk
        assert "event: activity" in chunk
    finally:
        await response.body_iterator.aclose()


async def test_large_requests_are_rejected_before_parsing(client):
    response = await client.post(
        "/v1/auth/login", content="x" * 66000, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


async def test_real_redis_atomic_limit_and_expiry():
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("Set TEST_REDIS_URL to exercise the Lua script against real Redis")
    redis = Redis.from_url(url, decode_responses=True)
    identity = f"integration:{uuid4()}"
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis=redis, local_limits={}))
    )
    try:
        await limit(request, identity, maximum=2, seconds=30)
        await limit(request, identity, maximum=2, seconds=30)
        with pytest.raises(HTTPException) as exc:
            await limit(request, identity, maximum=2, seconds=30)
        assert exc.value.status_code == 429
        # The integration database is dedicated to CI. Only inspect our own identity's key.
        import hashlib

        prefix = hashlib.sha256(identity.encode()).hexdigest()
        keys = [key async for key in redis.scan_iter(f"stratum:limit:{prefix}:*")]
        assert keys and 0 < await redis.ttl(keys[0]) <= 30
        await redis.delete(*keys)
    finally:
        await redis.aclose()
