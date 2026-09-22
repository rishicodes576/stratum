"""Postgres is the durable queue. Redis only wakes live clients; loss is harmless."""

import asyncio
import contextlib
import signal
from datetime import timedelta

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import and_, or_, select, update

from app.config import get_settings
from app.db import Session, engine
from app.models import Event, Incident, Job, Service, now, uid
from app.triage import analyze

log = structlog.get_logger()
MAX_ATTEMPTS = 4
LEASE_SECONDS = 45


async def claim(factory=Session) -> tuple[str, str] | None:
    async with factory() as session, session.begin():
        ready = or_(
            and_(Job.status == "pending", Job.available_at <= now()),
            and_(Job.status == "running", Job.lease_until < now()),
        )
        job = await session.scalar(
            select(Job)
            .where(ready)
            .order_by(Job.available_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return None
        if job.attempts >= MAX_ATTEMPTS:
            job.status = "dead"
            job.lease_token = None
            job.error = "Retry budget exhausted after lease expiry"
            session.add(
                Event(
                    tenant_id=job.tenant_id,
                    incident_id=job.incident_id,
                    kind="triage.failed",
                    actor="Stratum worker",
                    message=job.error,
                )
            )
            return None
        token = uid()
        job.status = "running"
        job.attempts += 1
        job.lease_token = token
        job.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
        return job.id, token


async def process(job_id: str, token: str, factory=Session, redis: Redis | None = None):
    try:
        async with factory() as session:
            job = await session.get(Job, job_id)
            if not job or job.status != "running" or job.lease_token != token:
                return
            incident = await session.get(Incident, job.incident_id)
            service = await session.get(Service, incident.service_id)
            evidence, version, slo = incident.evidence, incident.version, service.slo
        analysis = await analyze(evidence, slo)
        async with factory() as session, session.begin():
            # Fencing: an expired or superseded worker cannot publish a result.
            owned = await session.execute(
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.status == "running",
                    Job.lease_token == token,
                    Job.lease_until > now(),
                )
                .values(status="done", lease_token=None, lease_until=None)
            )
            if owned.rowcount != 1:
                return
            updated = await session.execute(
                update(Incident)
                .where(
                    Incident.id == incident.id,
                    Incident.version == version,
                    Incident.tenant_id == job.tenant_id,
                )
                .values(analysis=analysis)
            )
            if updated.rowcount == 1:
                session.add(
                    Event(
                        tenant_id=job.tenant_id,
                        incident_id=incident.id,
                        kind="triage.completed",
                        actor="Stratum worker",
                        message=analysis["summary"],
                        details={
                            "engine": analysis["engine"],
                            "model_status": analysis["model_status"],
                        },
                    )
                )
            else:
                # Evidence or lifecycle changed during analysis. A fresh job evaluates current data.
                session.add(Job(tenant_id=job.tenant_id, incident_id=incident.id))
        if redis:
            with contextlib.suppress(RedisError):
                await redis.publish(f"stratum:events:{job.tenant_id}", "changed")
        log.info("job.completed", job_id=job_id, tenant_id=job.tenant_id)
    except Exception as exc:
        log.exception("job.failed", job_id=job_id)
        async with factory() as session, session.begin():
            job = await session.scalar(
                select(Job)
                .where(
                    Job.id == job_id,
                    Job.status == "running",
                    Job.lease_token == token,
                    Job.lease_until > now(),
                )
                .with_for_update()
            )
            if job:
                job.status = "dead" if job.attempts >= MAX_ATTEMPTS else "pending"
                job.error = type(
                    exc
                ).__name__  # Never persist provider secrets or full exception bodies.
                job.available_at = now() + timedelta(seconds=2**job.attempts)
                job.lease_token = None
                job.lease_until = None
                if job.status == "dead":
                    session.add(
                        Event(
                            tenant_id=job.tenant_id,
                            incident_id=job.incident_id,
                            kind="triage.failed",
                            actor="Stratum worker",
                            message="Triage retry budget exhausted",
                        )
                    )


async def run():
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    redis = Redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=2)
    log.info("worker.started")
    try:
        while not stop.is_set():
            try:
                item = await claim()
                if item:
                    await process(*item, redis=redis)
                    continue
            except Exception:
                log.exception("worker.poll_failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=1)
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
