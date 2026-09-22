import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import worker
from app.models import Event, Incident, Job, now


async def test_lease_expiring_during_analysis_cannot_publish(store, incident, monkeypatch):
    original = worker.analyze
    item = await worker.claim(store["factory"])

    async def expire_during_analysis(evidence, slo):
        async with store["factory"]() as session, session.begin():
            job = await session.get(Job, item[0])
            job.lease_until = now() - timedelta(seconds=1)
        return await original(evidence, slo)

    monkeypatch.setattr(worker, "analyze", expire_during_analysis)
    await worker.process(*item, factory=store["factory"])
    async with store["factory"]() as session:
        assert (await session.get(Incident, incident["incident_id"])).analysis is None
        assert (await session.get(Job, item[0])).status == "running"
    reclaimed = await worker.claim(store["factory"])
    assert reclaimed[1] != item[1]


async def test_repeated_crashes_exhaust_attempt_budget(store, incident):
    async with store["factory"]() as session, session.begin():
        job = await session.get(Job, incident["job_id"])
        job.status = "running"
        job.attempts = 4
        job.lease_token = "abandoned"
        job.lease_until = now() - timedelta(seconds=1)
    assert await worker.claim(store["factory"]) is None
    async with store["factory"]() as session:
        assert (await session.get(Job, incident["job_id"])).status == "dead"
        assert await session.scalar(select(Event).where(Event.kind == "triage.failed")) is not None


@pytest.mark.postgres
async def test_simultaneous_operator_updates_have_one_winner(client, store, incident):
    if not store["postgres"]:
        pytest.skip("PostgreSQL concurrent updates required")

    async def acknowledge():
        return await client.patch(
            f"/v1/incidents/{incident['incident_id']}",
            headers=store["tokens"]["operator"],
            json={"status": "acknowledged", "version": 1},
        )

    responses = await asyncio.gather(acknowledge(), acknowledge())
    assert sorted(r.status_code for r in responses) == [200, 409]
