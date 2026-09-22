import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, Incident, Job, Receipt, Service, now
from app.schemas import Signal, Transition
from app.security import Principal
from app.triage import evaluate

TRANSITIONS = {
    "open": {"acknowledged"},
    "acknowledged": {"mitigating", "resolved"},
    "mitigating": {"resolved"},
    "resolved": set(),
}


def serialize(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def audit(
    session: AsyncSession,
    user: Principal,
    kind: str,
    message: str,
    incident_id: str | None = None,
    details: dict | None = None,
):
    session.add(
        Event(
            tenant_id=user.tenant_id,
            incident_id=incident_id,
            kind=kind,
            actor=user.name,
            message=message,
            details=details or {},
        )
    )


async def get_incident(session: AsyncSession, tenant_id: str, incident_id: str) -> Incident:
    incident = await session.scalar(
        select(Incident).where(Incident.id == incident_id, Incident.tenant_id == tenant_id)
    )
    if not incident:
        raise HTTPException(404, "Incident not found")
    return incident


async def ingest(session: AsyncSession, user: Principal, signal: Signal, key: str) -> dict:
    digest = hashlib.sha256(json.dumps(signal.model_dump(), sort_keys=True).encode()).hexdigest()
    # A unique receipt and active-fingerprint index arbitrate concurrent requests.
    # Retry from a fresh transaction after a uniqueness race, never reuse a failed transaction.
    for _ in range(4):
        receipt = await session.scalar(
            select(Receipt).where(Receipt.tenant_id == user.tenant_id, Receipt.key == key)
        )
        if receipt:
            if receipt.digest != digest:
                raise HTTPException(409, "Idempotency key was already used for a different payload")
            return {**receipt.response, "replayed": True}
        service = await session.scalar(
            select(Service).where(
                Service.id == signal.service_id, Service.tenant_id == user.tenant_id
            )
        )
        if not service:
            raise HTTPException(404, "Service not found")
        incident = await session.scalar(
            select(Incident)
            .where(
                Incident.tenant_id == user.tenant_id,
                Incident.service_id == service.id,
                Incident.fingerprint == signal.fingerprint,
                Incident.status != "resolved",
            )
            .with_for_update()
        )
        correlated = incident is not None
        evidence = signal.evidence.model_dump()
        severity = evaluate(evidence, service.slo)["severity"]
        try:
            if incident:
                incident.signal_count += 1
                incident.evidence = evidence
                incident.severity = severity
                incident.analysis = None
                incident.version += 1
                incident.updated_at = now()
            else:
                incident = Incident(
                    tenant_id=user.tenant_id,
                    service_id=service.id,
                    title=signal.title,
                    fingerprint=signal.fingerprint,
                    severity=severity,
                    evidence=evidence,
                )
                session.add(incident)
                await session.flush()
            job = Job(tenant_id=user.tenant_id, incident_id=incident.id)
            session.add(job)
            await session.flush()
            response = {
                "incident_id": incident.id,
                "job_id": job.id,
                "correlated": correlated,
                "replayed": False,
            }
            session.add(
                Receipt(tenant_id=user.tenant_id, key=key, digest=digest, response=response)
            )
            audit(
                session,
                user,
                "signal.correlated" if correlated else "incident.created",
                f"Signal received for {service.name}",
                incident.id,
                {"fingerprint": signal.fingerprint, "severity": severity},
            )
            await session.commit()
            return response
        except IntegrityError:
            await session.rollback()
    raise HTTPException(409, "Concurrent ingestion conflict; retry with the same idempotency key")


async def transition(
    session: AsyncSession, user: Principal, incident_id: str, request: Transition
) -> dict:
    incident = await get_incident(session, user.tenant_id, incident_id)
    if incident.version != request.version:
        raise HTTPException(409, "Incident changed; refresh before updating")
    if request.status not in TRANSITIONS[incident.status]:
        raise HTTPException(409, f"Cannot move from {incident.status} to {request.status}")
    if request.status == "resolved" and len(request.note.strip()) < 10:
        raise HTTPException(422, "Resolution requires a note of at least 10 characters")
    changes = {"status": request.status, "version": Incident.version + 1, "updated_at": now()}
    if request.status == "acknowledged":
        changes.update(owner=user.name, acknowledged_at=now())
    if request.status == "resolved":
        changes["resolved_at"] = now()
    result = await session.execute(
        update(Incident)
        .where(
            Incident.id == incident.id,
            Incident.tenant_id == user.tenant_id,
            Incident.version == request.version,
        )
        .values(**changes)
    )
    if result.rowcount != 1:
        await session.rollback()
        raise HTTPException(409, "Incident changed; refresh before updating")
    audit(
        session,
        user,
        f"incident.{request.status}",
        request.note or f"{user.name} marked the incident {request.status}",
        incident.id,
    )
    await session.commit()
    await session.refresh(incident)
    return serialize(incident)
