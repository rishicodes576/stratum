import asyncio

import jwt
import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models import Event, Incident, Job, Receipt, User, now


async def test_authentication_and_private_session(client, store):
    assert (await client.get("/v1/me")).status_code == 401
    bad = await client.post(
        "/v1/auth/login", json={"email": "operator@alpha.test", "password": "wrong-password"}
    )
    assert bad.status_code == 401
    response = await client.post(
        "/v1/auth/login", json={"email": "operator@alpha.test", "password": "test-password-123"}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["workspace"] == "Alpha"
    assert "password_hash" not in me.json()


@pytest.mark.parametrize("role", ["admin", "operator", "viewer"])
async def test_reads_are_available_to_workspace_members(client, store, role):
    response = await client.get("/v1/services", headers=store["tokens"][role])
    assert response.status_code == 200
    assert [row["name"] for row in response.json()] == ["Checkout"]


async def test_viewer_cannot_ingest_or_mutate(client, store, signal_body, incident):
    headers = {**store["tokens"]["viewer"], "Idempotency-Key": "viewer-key"}
    assert (await client.post("/v1/signals", headers=headers, json=signal_body)).status_code == 403
    assert (
        await client.patch(
            f"/v1/incidents/{incident['incident_id']}",
            headers=headers,
            json={"version": 1, "status": "acknowledged"},
        )
    ).status_code == 403


async def test_tenant_cannot_read_or_modify_foreign_incident(client, store, incident):
    headers = store["tokens"]["outsider"]
    base = f"/v1/incidents/{incident['incident_id']}"
    assert (await client.get(base, headers=headers)).status_code == 404
    assert (
        await client.patch(base, headers=headers, json={"version": 1, "status": "acknowledged"})
    ).status_code == 404
    assert (
        await client.post(base + "/notes", headers=headers, json={"message": "Trying to write"})
    ).status_code == 404
    assert (await client.get("/v1/incidents", headers=headers)).json()["items"] == []
    assert (await client.get("/v1/events", headers=headers)).json() == []
    assert (await client.get("/v1/jobs", headers=headers)).json() == []
    assert (await client.get("/v1/overview", headers=headers)).json()["active_incidents"] == 0


async def test_foreign_service_cannot_be_used_for_ingestion(client, store, signal_body):
    signal_body["service_id"] = store["outside_service"].id
    response = await client.post(
        "/v1/signals",
        headers={**store["tokens"]["admin"], "Idempotency-Key": "foreign-service"},
        json=signal_body,
    )
    assert response.status_code == 404


async def test_idempotent_replay_and_transactional_outbox(client, store, signal_body, incident):
    response = await client.post(
        "/v1/signals",
        headers={**store["tokens"]["operator"], "Idempotency-Key": "fixture-key-123"},
        json=signal_body,
    )
    assert response.json()["incident_id"] == incident["incident_id"]
    assert response.json()["replayed"] is True
    async with store["factory"]() as session:
        for model in [Incident, Job, Receipt, Event]:
            assert await session.scalar(select(func.count()).select_from(model)) == 1


async def test_idempotency_key_reuse_with_different_payload_is_rejected(
    client, store, signal_body, incident
):
    signal_body["title"] = "Different title"
    response = await client.post(
        "/v1/signals",
        headers={**store["tokens"]["operator"], "Idempotency-Key": "fixture-key-123"},
        json=signal_body,
    )
    assert response.status_code == 409


async def test_matching_fingerprints_correlate(client, store, signal_body, incident):
    response = await client.post(
        "/v1/signals",
        headers={**store["tokens"]["operator"], "Idempotency-Key": "different-delivery"},
        json=signal_body,
    )
    assert response.json()["correlated"] is True
    assert response.json()["incident_id"] == incident["incident_id"]
    detail = (
        await client.get(
            f"/v1/incidents/{incident['incident_id']}", headers=store["tokens"]["admin"]
        )
    ).json()
    assert detail["signal_count"] == 2
    assert detail["version"] == 2


async def test_state_machine_and_optimistic_concurrency(client, store, incident):
    headers = store["tokens"]["operator"]
    url = f"/v1/incidents/{incident['incident_id']}"
    invalid = await client.patch(
        url,
        headers=headers,
        json={"version": 1, "status": "resolved", "note": "It is now resolved"},
    )
    assert invalid.status_code == 409
    ack = await client.patch(url, headers=headers, json={"version": 1, "status": "acknowledged"})
    assert ack.status_code == 200 and ack.json()["owner"] == "Operator"
    stale = await client.patch(url, headers=headers, json={"version": 1, "status": "mitigating"})
    assert stale.status_code == 409
    short = await client.patch(
        url, headers=headers, json={"version": 2, "status": "resolved", "note": "fixed"}
    )
    assert short.status_code == 422
    resolved = await client.patch(
        url,
        headers=headers,
        json={
            "version": 2,
            "status": "resolved",
            "note": "Verified recovery using healthy request traces.",
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved_at"] is not None
    assert (await client.get(url, headers=headers)).json()["events"][-1][
        "kind"
    ] == "incident.resolved"


async def test_resolved_fingerprint_opens_a_new_incident(client, store, signal_body, incident):
    headers = store["tokens"]["admin"]
    url = f"/v1/incidents/{incident['incident_id']}"
    await client.patch(url, headers=headers, json={"version": 1, "status": "acknowledged"})
    await client.patch(
        url,
        headers=headers,
        json={"version": 2, "status": "resolved", "note": "Recovery is verified"},
    )
    response = await client.post(
        "/v1/signals", headers={**headers, "Idempotency-Key": "new-incident"}, json=signal_body
    )
    assert response.status_code == 202
    assert response.json()["incident_id"] != incident["incident_id"]


@pytest.mark.parametrize("value", [-1, 100.1])
async def test_error_rate_validation(client, store, signal_body, value):
    signal_body["evidence"]["error_rate_5m"] = value
    assert (
        await client.post(
            "/v1/signals",
            headers={**store["tokens"]["admin"], "Idempotency-Key": "invalid-body"},
            json=signal_body,
        )
    ).status_code == 422


async def test_unknown_input_fields_are_rejected(client, store, signal_body):
    signal_body["tenant_id"] = store["outside_service"].tenant_id
    assert (
        await client.post(
            "/v1/signals",
            headers={**store["tokens"]["admin"], "Idempotency-Key": "spoofing-tenant"},
            json=signal_body,
        )
    ).status_code == 422


async def test_expired_and_forged_tokens_are_rejected(client, store):
    user = store["users"]["admin"]
    token = jwt.encode(
        {
            "sub": user.id,
            "tid": user.tenant_id,
            "iat": 1,
            "exp": 2,
            "iss": "stratum",
            "aud": "stratum-api",
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    assert (
        await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 401
    token = jwt.encode(
        {
            "sub": user.id,
            "tid": store["outside_service"].tenant_id,
            "iat": now(),
            "exp": 9999999999,
            "iss": "stratum",
            "aud": "stratum-api",
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    assert (
        await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 401


async def test_role_changes_apply_to_existing_sessions(client, store, signal_body):
    async with store["factory"]() as session, session.begin():
        user = await session.get(User, store["users"]["operator"].id)
        user.role = "viewer"
    response = await client.post(
        "/v1/signals",
        headers={**store["tokens"]["operator"], "Idempotency-Key": "role-change"},
        json=signal_body,
    )
    assert response.status_code == 403


async def test_admin_service_registration_and_duplicate_slug(client, store):
    body = {"name": "Identity", "slug": "identity", "team": "Platform"}
    assert (
        await client.post("/v1/services", headers=store["tokens"]["operator"], json=body)
    ).status_code == 403
    assert (
        await client.post("/v1/services", headers=store["tokens"]["admin"], json=body)
    ).status_code == 201
    assert (
        await client.post("/v1/services", headers=store["tokens"]["admin"], json=body)
    ).status_code == 409


async def test_cursor_pagination_does_not_leak_foreign_anchor(client, store, signal_body, incident):
    response = await client.get(
        f"/v1/incidents?before={incident['incident_id']}", headers=store["tokens"]["outsider"]
    )
    assert response.status_code == 404
    for index in range(3):
        signal_body["fingerprint"] = f"unique.{index}"
        await client.post(
            "/v1/signals",
            headers={**store["tokens"]["admin"], "Idempotency-Key": f"page-key-{index}"},
            json=signal_body,
        )
    first = (await client.get("/v1/incidents?limit=2", headers=store["tokens"]["admin"])).json()
    second = (
        await client.get(
            f"/v1/incidents?limit=2&before={first['next_cursor']}", headers=store["tokens"]["admin"]
        )
    ).json()
    assert len(first["items"]) == len(second["items"]) == 2
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}
    assert second["next_cursor"] is None


async def test_login_rate_limit(client):
    body = {"email": "missing@test.local", "password": "wrong-password"}
    responses = [await client.post("/v1/auth/login", json=body) for _ in range(11)]
    assert responses[-1].status_code == 429
    assert responses[-1].headers["retry-after"] == "60"


async def test_request_ids_and_metrics_use_bounded_routes(client, store):
    response = await client.get("/health/live")
    assert response.status_code == 200 and response.headers["x-request-id"]
    await client.get("/v1/incidents/not-a-real-id", headers=store["tokens"]["admin"])
    metrics = (await client.get("/metrics")).text
    assert "stratum_http_requests_total" in metrics
    assert "not-a-real-id" not in metrics


@pytest.mark.postgres
async def test_concurrent_delivery_creates_exactly_one_receipt(client, store, signal_body):
    if not store["postgres"]:
        pytest.skip("PostgreSQL is required to verify concurrent transaction semantics")

    async def send():
        return await client.post(
            "/v1/signals",
            headers={**store["tokens"]["admin"], "Idempotency-Key": "concurrent-key"},
            json=signal_body,
        )

    responses = await asyncio.gather(*(send() for _ in range(8)))
    assert all(r.status_code == 202 for r in responses)
    assert len({r.json()["incident_id"] for r in responses}) == 1
    async with store["factory"]() as session:
        for model in [Incident, Job, Receipt, Event]:
            assert await session.scalar(select(func.count()).select_from(model)) == 1


@pytest.mark.postgres
async def test_concurrent_distinct_deliveries_correlate_without_lost_signals(
    client, store, signal_body
):
    if not store["postgres"]:
        pytest.skip("PostgreSQL required")

    async def send(index):
        return await client.post(
            "/v1/signals",
            headers={**store["tokens"]["admin"], "Idempotency-Key": f"parallel-{index}"},
            json=signal_body,
        )

    responses = await asyncio.gather(*(send(index) for index in range(8)))
    assert all(r.status_code == 202 for r in responses)
    async with store["factory"]() as session:
        incident = await session.scalar(select(Incident))
        assert incident.signal_count == 8
        assert await session.scalar(select(func.count()).select_from(Incident)) == 1
