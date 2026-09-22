"""Opt-in, deterministic sample workspace. Refuses production mode."""

import asyncio
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.config import get_settings
from app.db import Session, engine
from app.models import Event, Incident, Job, Service, Tenant, User, now
from app.security import hash_password
from app.triage import evaluate


def stable(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"stratum-demo/{value}"))


async def seed():
    if get_settings().environment == "production":
        raise RuntimeError("Demo seeding is disabled in production. Use app.bootstrap.")
    async with Session() as session, session.begin():
        if await session.get(Tenant, stable("tenant")):
            print("Demo workspace already exists; no data changed.")
            return
        tenant = Tenant(id=stable("tenant"), name="Acme Engineering")
        session.add(tenant)
        await session.flush()
        for email, name, role in [
            ("demo@stratum.local", "Alex Morgan", "admin"),
            ("viewer@stratum.local", "Jamie Chen", "viewer"),
        ]:
            if await session.scalar(select(User).where(User.email == email)):
                raise RuntimeError("Demo email already exists in another workspace")
            session.add(
                User(
                    id=stable(email),
                    tenant_id=tenant.id,
                    email=email,
                    name=name,
                    role=role,
                    password_hash=hash_password("stratum-demo-password"),
                )
            )
        catalog = [
            (
                "checkout-api",
                "Checkout API",
                "Commerce",
                1,
                99.9,
                "The critical path from basket to confirmed order.",
                ["payments", "postgres", "redis"],
            ),
            (
                "payments",
                "Payment Gateway",
                "Payments",
                1,
                99.95,
                "Payment authorization, settlement, and provider routing.",
                ["postgres", "payment-provider"],
            ),
            (
                "identity",
                "Identity Service",
                "Platform",
                1,
                99.99,
                "Authentication and access for every customer session.",
                ["postgres", "redis"],
            ),
            (
                "event-pipeline",
                "Event Pipeline",
                "Data Infrastructure",
                2,
                99.5,
                "Durable product events delivered to downstream consumers.",
                ["redis", "object-storage"],
            ),
            (
                "search",
                "Search & Discovery",
                "Discovery",
                2,
                99.9,
                "Fast, relevant discovery across the product catalog.",
                ["search-index", "redis"],
            ),
            (
                "notifications",
                "Notifications",
                "Engagement",
                3,
                99.5,
                "Transactional notifications across email and push.",
                ["event-pipeline", "email-provider"],
            ),
        ]
        services = []
        for slug, name, team, tier, slo, description, dependencies in catalog:
            service = Service(
                id=stable(slug),
                tenant_id=tenant.id,
                slug=slug,
                name=name,
                team=team,
                tier=tier,
                slo=slo,
                description=description,
                dependencies=dependencies,
            )
            session.add(service)
            services.append(service)
        await session.flush()
        active = [
            (
                0,
                "Elevated 5xx errors on checkout",
                "mitigating",
                37,
                2.8,
                1.8,
                0.8,
                1240,
                "checkout-v2.8.1",
                "Alex Morgan",
                14,
            ),
            (
                1,
                "Payment authorization latency spike",
                "acknowledged",
                23,
                0.9,
                0.4,
                0.32,
                2180,
                "payments-v1.14.0",
                "Alex Morgan",
                8,
            ),
            (
                3,
                "Consumer lag above processing threshold",
                "open",
                11,
                1.2,
                0.8,
                0.3,
                860,
                None,
                None,
                6,
            ),
        ]
        for index, (
            service_index,
            title,
            status,
            minutes,
            error5,
            error1,
            error6,
            latency,
            deployment,
            owner,
            count,
        ) in enumerate(active):
            service = services[service_index]
            evidence = {
                "error_rate_5m": error5,
                "error_rate_1h": error1,
                "error_rate_6h": error6,
                "latency_p95_ms": latency,
                "requests_per_minute": 14280 - index * 4000,
                "deployment": deployment,
            }
            analysis = evaluate(evidence, service.slo)
            created = now() - timedelta(minutes=minutes)
            incident = Incident(
                id=stable(f"active-{index}"),
                tenant_id=tenant.id,
                service_id=service.id,
                title=title,
                fingerprint=f"{service.slug}.demo",
                severity=analysis["severity"],
                status=status,
                owner=owner,
                version=3 if status == "mitigating" else 2 if owner else 1,
                signal_count=count,
                evidence=evidence,
                analysis=analysis,
                created_at=created,
                updated_at=created + timedelta(minutes=3),
                acknowledged_at=created + timedelta(minutes=2) if owner else None,
            )
            session.add(incident)
            await session.flush()
            session.add(
                Event(
                    tenant_id=tenant.id,
                    incident_id=incident.id,
                    kind="incident.created",
                    actor="Demo signal source",
                    message=f"Signal received for {service.name}",
                    created_at=created,
                )
            )
            session.add(
                Event(
                    tenant_id=tenant.id,
                    incident_id=incident.id,
                    kind="triage.completed",
                    actor="Stratum worker",
                    message=analysis["summary"],
                    created_at=created + timedelta(seconds=8),
                )
            )
            if owner:
                session.add(
                    Event(
                        tenant_id=tenant.id,
                        incident_id=incident.id,
                        kind="incident.acknowledged",
                        actor=owner,
                        message="Investigating the latest deployment and downstream traces.",
                        created_at=created + timedelta(minutes=2),
                    )
                )
            if status == "mitigating":
                session.add(
                    Event(
                        tenant_id=tenant.id,
                        incident_id=incident.id,
                        kind="incident.mitigating",
                        actor=owner,
                        message="Comparing error signatures with the previous release. Rollback under review.",
                        created_at=created + timedelta(minutes=3),
                    )
                )
            session.add(
                Job(
                    id=stable(f"active-job-{index}"),
                    tenant_id=tenant.id,
                    incident_id=incident.id,
                    status="done",
                    attempts=1,
                    created_at=created,
                )
            )
        # Deterministic fixtures, deliberately labeled as demo data in the UI and README.
        for day, count in enumerate([2, 1, 3, 2, 4, 1, 2, 5, 3, 1, 2, 4, 2], start=1):
            for n in range(count):
                service = services[(day + n) % len(services)]
                created = now() - timedelta(days=day, hours=n + 1)
                duration = 12 + ((day * 7 + n * 13) % 38)
                evidence = {
                    "error_rate_5m": 1.8,
                    "error_rate_1h": 0.9,
                    "error_rate_6h": 0.4,
                    "latency_p95_ms": 740,
                    "requests_per_minute": 8400,
                    "deployment": None,
                }
                analysis = evaluate(evidence, service.slo)
                incident = Incident(
                    id=stable(f"history-{day}-{n}"),
                    tenant_id=tenant.id,
                    service_id=service.id,
                    title=f"{service.name}: transient error increase",
                    fingerprint=f"history.{day}.{n}",
                    severity=analysis["severity"],
                    status="resolved",
                    owner="Alex Morgan",
                    version=4,
                    signal_count=3 + n,
                    evidence=evidence,
                    analysis=analysis,
                    created_at=created,
                    updated_at=created + timedelta(minutes=duration),
                    acknowledged_at=created + timedelta(minutes=2),
                    resolved_at=created + timedelta(minutes=duration),
                )
                session.add(incident)
                await session.flush()
                session.add(
                    Event(
                        tenant_id=tenant.id,
                        incident_id=incident.id,
                        kind="incident.resolved",
                        actor="Alex Morgan",
                        message="Sample incident: error rate returned to baseline and recovery verified.",
                        created_at=incident.resolved_at,
                    )
                )
                session.add(
                    Job(
                        tenant_id=tenant.id,
                        incident_id=incident.id,
                        status="done",
                        attempts=1,
                        created_at=created,
                    )
                )
        print("Seeded Acme Engineering. Login: demo@stratum.local / stratum-demo-password")


async def main():
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
