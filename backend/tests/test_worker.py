import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app import worker
from app.models import Event, Incident, Job, now


async def test_worker_persists_triage_and_audit(store, incident):
    item = await worker.claim(store["factory"])
    assert item is not None
    await worker.process(*item, factory=store["factory"])
    async with store["factory"]() as session:
        job = await session.get(Job, item[0])
        row = await session.get(Incident, incident["incident_id"])
        assert job.status == "done"
        assert job.lease_token is None
        assert row.analysis["severity"] == "SEV1"
        assert row.analysis["actions"][0]["id"] == "inspect-deployment"
        assert (
            await session.scalar(
                select(func.count()).select_from(Event).where(Event.kind == "triage.completed")
            )
            == 1
        )
    # A duplicate worker delivery after completion cannot produce another audit event.
    await worker.process(*item, factory=store["factory"])
    async with store["factory"]() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(Event).where(Event.kind == "triage.completed")
            )
            == 1
        )


async def test_expired_lease_is_reclaimed_and_old_worker_is_fenced(store, incident):
    first = await worker.claim(store["factory"])
    async with store["factory"]() as session, session.begin():
        job = await session.get(Job, first[0])
        job.lease_until = now() - timedelta(seconds=1)
    second = await worker.claim(store["factory"])
    assert second[0] == first[0] and second[1] != first[1]
    await worker.process(*first, factory=store["factory"])
    async with store["factory"]() as session:
        assert (await session.get(Incident, incident["incident_id"])).analysis is None
    await worker.process(*second, factory=store["factory"])
    async with store["factory"]() as session:
        assert (await session.get(Job, second[0])).attempts == 2
        assert (await session.get(Job, second[0])).status == "done"


async def test_failed_jobs_retry_then_dead_letter(store, incident, monkeypatch):
    monkeypatch.setattr(
        worker, "analyze", AsyncMock(side_effect=RuntimeError("secret should not be stored"))
    )
    for attempt in range(4):
        item = await worker.claim(store["factory"])
        assert item is not None
        await worker.process(*item, factory=store["factory"])
        async with store["factory"]() as session, session.begin():
            job = await session.get(Job, item[0])
            assert job.attempts == attempt + 1
            assert job.error == "RuntimeError"
            assert job.status == ("dead" if attempt == 3 else "pending")
            job.available_at = now() - timedelta(seconds=1)
    assert await worker.claim(store["factory"]) is None


async def test_retry_admin_and_tenant_checks(client, store, incident):
    job_id = incident["job_id"]
    async with store["factory"]() as session, session.begin():
        job = await session.get(Job, job_id)
        job.status = "dead"
        job.attempts = 4
    url = f"/v1/jobs/{job_id}/retry"
    assert (await client.post(url, headers=store["tokens"]["viewer"])).status_code == 403
    assert (await client.post(url, headers=store["tokens"]["outsider"])).status_code == 404
    assert (await client.post(url, headers=store["tokens"]["admin"])).status_code == 200
    assert (await client.post(url, headers=store["tokens"]["admin"])).status_code == 409


async def test_stale_analysis_queues_fresh_evidence(store, incident, monkeypatch):
    original = worker.analyze

    async def change_during_analysis(evidence, slo):
        async with store["factory"]() as session, session.begin():
            row = await session.get(Incident, incident["incident_id"])
            row.version += 1
        return await original(evidence, slo)

    monkeypatch.setattr(worker, "analyze", change_during_analysis)
    item = await worker.claim(store["factory"])
    await worker.process(*item, factory=store["factory"])
    async with store["factory"]() as session:
        assert (await session.get(Incident, incident["incident_id"])).analysis is None
        assert (
            await session.scalar(
                select(func.count()).select_from(Job).where(Job.status == "pending")
            )
            == 1
        )


async def test_action_decisions_are_audited_and_do_not_execute(client, store, incident):
    url = f"/v1/incidents/{incident['incident_id']}/decisions"
    body = {
        "action_id": "inspect-deployment",
        "outcome": "approved",
        "reason": "The deployment timing warrants investigation",
        "version": 1,
    }
    assert (
        await client.post(url, headers=store["tokens"]["operator"], json=body)
    ).status_code == 409
    item = await worker.claim(store["factory"])
    await worker.process(*item, factory=store["factory"])
    response = await client.post(url, headers=store["tokens"]["operator"], json=body)
    assert response.status_code == 201
    assert response.json()["execution"] == "manual-external"
    assert (
        await client.post(url, headers=store["tokens"]["operator"], json=body)
    ).status_code == 409
    body["action_id"] = "execute-shell-command"
    assert (
        await client.post(url, headers=store["tokens"]["operator"], json=body)
    ).status_code == 422


@pytest.mark.postgres
async def test_two_workers_never_claim_same_live_job(store, incident):
    if not store["postgres"]:
        pytest.skip("PostgreSQL SKIP LOCKED semantics required")
    results = await asyncio.gather(worker.claim(store["factory"]), worker.claim(store["factory"]))
    assert sum(r is not None for r in results) == 1
