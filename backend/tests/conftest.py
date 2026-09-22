import os
from uuid import uuid4

import fakeredis.aioredis
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_session
from app.main import app
from app.models import Base, Service, Tenant, User
from app.security import hash_password, token_for


@pytest.fixture
async def store(tmp_path):
    url = os.getenv("TEST_DATABASE_URL")
    schema = f"test_{uuid4().hex}"
    admin = None
    if url:
        if not url.startswith("postgresql+asyncpg://"):
            raise ValueError("TEST_DATABASE_URL must use postgresql+asyncpg")
        admin = create_async_engine(url)
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        alpha = Tenant(name="Alpha")
        beta = Tenant(name="Beta")
        session.add_all([alpha, beta])
        await session.flush()
        password_hash = hash_password("test-password-123")
        users = {
            role: User(
                tenant_id=alpha.id,
                email=f"{role}@alpha.test",
                name=role.title(),
                role=role,
                password_hash=password_hash,
            )
            for role in ["admin", "operator", "viewer"]
        }
        users["outsider"] = User(
            tenant_id=beta.id,
            email="admin@beta.test",
            name="Outsider",
            role="admin",
            password_hash=password_hash,
        )
        session.add_all(users.values())
        service = Service(
            tenant_id=alpha.id, slug="checkout", name="Checkout", team="Commerce", slo=99.9
        )
        outside_service = Service(
            tenant_id=beta.id, slug="outside", name="Outside", team="Beta", slo=99.9
        )
        session.add_all([service, outside_service])
        await session.flush()
        tokens = {
            role: {"Authorization": f"Bearer {token_for(user)}"} for role, user in users.items()
        }
    yield {
        "factory": factory,
        "users": users,
        "tokens": tokens,
        "service": service,
        "outside_service": outside_service,
        "postgres": bool(url),
    }
    await engine.dispose()
    if admin:
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.fixture
async def client(store):
    async def session_override():
        async with store["factory"]() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.state.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.state.local_limits = {}
    app.state.session_factory = store["factory"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    await app.state.redis.aclose()
    app.dependency_overrides.clear()


@pytest.fixture
def signal_body(store):
    return {
        "service_id": store["service"].id,
        "title": "Checkout is returning errors",
        "fingerprint": "checkout.errors",
        "evidence": {
            "error_rate_5m": 2.4,
            "error_rate_1h": 1.8,
            "error_rate_6h": 0.8,
            "latency_p95_ms": 840,
            "requests_per_minute": 12500,
            "deployment": "v2.8.1",
        },
    }


@pytest.fixture
async def incident(client, store, signal_body):
    response = await client.post(
        "/v1/signals",
        headers={**store["tokens"]["operator"], "Idempotency-Key": "fixture-key-123"},
        json=signal_body,
    )
    assert response.status_code == 202, response.text
    return response.json()
