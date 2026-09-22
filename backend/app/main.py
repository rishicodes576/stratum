import asyncio
import contextlib
import json
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import timedelta
from uuid import uuid4

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.config import get_settings
from app.db import Session, engine, get_session
from app.domain import audit, get_incident, ingest, serialize, transition
from app.limits import limit
from app.models import Event, Incident, Job, Service, Tenant, User, now
from app.schemas import (
    Decision,
    EventRead,
    IncidentDetailRead,
    IncidentPage,
    IncidentRead,
    JobRead,
    Login,
    Note,
    OverviewRead,
    ServiceCreate,
    ServiceRead,
    ServiceView,
    Signal,
    SignalReceipt,
    Transition,
    UserRead,
)
from app.security import (
    Principal,
    admin,
    hash_password,
    operator,
    principal,
    token_for,
    verify_password,
)
from app.triage import RUNBOOKS, burn_rates

structlog.configure(
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()]
)
log = structlog.get_logger()
REQUESTS = Counter("stratum_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("stratum_http_request_seconds", "HTTP duration", ["method", "route"])
DUMMY_HASH = hash_password("not-a-real-user-password")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=1,
    )
    app.state.local_limits = {}
    app.state.session_factory = Session
    yield
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(
    title="Stratum Reliability API",
    version="1.0.0",
    lifespan=lifespan,
    description="Tenant-isolated incident response with durable evidence-based triage.",
)


@app.middleware("http")
async def observe(request: Request, call_next):
    request_id = str(uuid4())
    start = time.perf_counter()
    try:
        content_length = int(request.headers.get("content-length", "0"))
    except ValueError:
        return Response("Invalid content length", status_code=400)
    if content_length > 65536:
        return Response("Request body too large", status_code=413)
    response = await call_next(request)
    route = getattr(request.scope.get("route"), "path", "unmatched")
    duration = time.perf_counter() - start
    REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    LATENCY.labels(request.method, route).observe(duration)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    log.info(
        "http.request",
        request_id=request_id,
        method=request.method,
        route=route,
        status=response.status_code,
        duration_ms=round(duration * 1000, 2),
    )
    return response


@app.get("/health/live", tags=["health"])
async def live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def ready(request: Request, session: AsyncSession = Depends(get_session)):
    try:
        await session.execute(text("SELECT 1"))
        await request.app.state.redis.ping()
    except Exception as exc:
        raise HTTPException(503, "A dependency is unavailable") from exc
    return {"status": "ready", "database": "connected", "redis": "connected"}


@app.get("/metrics", include_in_schema=False)
async def metrics():
    # Internal-only endpoint; the frontend proxy explicitly excludes this path.
    return Response(generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})


@app.post("/v1/auth/login", tags=["auth"])
async def login(body: Login, request: Request, session: AsyncSession = Depends(get_session)):
    await limit(request, f"login:account:{body.email.lower()}", 10)
    user = await session.scalar(select(User).where(User.email == body.email.lower()))
    valid = await verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(401, "Invalid email or password")
    return {
        "access_token": token_for(user),
        "token_type": "bearer",
        "expires_in": get_settings().session_minutes * 60,
    }


@app.get("/v1/me", tags=["auth"], response_model=UserRead)
async def me(user: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    tenant = await session.get(Tenant, user.tenant_id)
    return {**asdict(user), "workspace": tenant.name}


@app.get("/v1/services", tags=["services"], response_model=list[ServiceView])
async def services(
    user: Principal = Depends(principal), session: AsyncSession = Depends(get_session)
):
    rows = (
        await session.scalars(
            select(Service).where(Service.tenant_id == user.tenant_id).order_by(Service.name)
        )
    ).all()
    active = (
        await session.scalars(
            select(Incident)
            .where(Incident.tenant_id == user.tenant_id, Incident.status != "resolved")
            .order_by(Incident.updated_at.desc())
        )
    ).all()
    return [
        {
            **serialize(s),
            "active_incidents": sum(i.service_id == s.id for i in active),
            "latest_evidence": next((i.evidence for i in active if i.service_id == s.id), None),
        }
        for s in rows
    ]


@app.post("/v1/services", status_code=201, tags=["services"], response_model=ServiceRead)
async def create_service(
    body: ServiceCreate,
    user: Principal = Depends(admin),
    session: AsyncSession = Depends(get_session),
):
    service = Service(tenant_id=user.tenant_id, **body.model_dump())
    session.add(service)
    audit(session, user, "service.created", f"Registered {body.name}")
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "Service slug already exists") from exc
    return serialize(service)


@app.post("/v1/signals", status_code=202, tags=["ingestion"], response_model=SignalReceipt)
async def signals(
    body: Signal,
    request: Request,
    idempotency_key: str = Header(min_length=8, max_length=120),
    user: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
):
    await limit(request, f"ingest:{user.tenant_id}", 120)
    result = await ingest(session, user, body, idempotency_key)
    with contextlib.suppress(RedisError):
        await request.app.state.redis.publish(f"stratum:events:{user.tenant_id}", "changed")
    return result


@app.get("/v1/incidents", tags=["incidents"], response_model=IncidentPage)
async def incidents(
    status: str | None = Query(
        default=None, pattern="^(active|open|acknowledged|mitigating|resolved)$"
    ),
    before: str | None = None,
    limit_: int = Query(default=50, alias="limit", ge=1, le=100),
    user: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    query = select(Incident).where(Incident.tenant_id == user.tenant_id)
    if status == "active":
        query = query.where(Incident.status != "resolved")
    elif status:
        query = query.where(Incident.status == status)
    if before:
        anchor = await get_incident(session, user.tenant_id, before)
        query = query.where(
            (Incident.created_at < anchor.created_at)
            | ((Incident.created_at == anchor.created_at) & (Incident.id < anchor.id))
        )
    rows = (
        await session.scalars(
            query.order_by(Incident.created_at.desc(), Incident.id.desc()).limit(limit_ + 1)
        )
    ).all()
    return {
        "items": [serialize(i) for i in rows[:limit_]],
        "next_cursor": rows[limit_ - 1].id if len(rows) > limit_ else None,
    }


@app.get("/v1/incidents/{incident_id}", tags=["incidents"], response_model=IncidentDetailRead)
async def detail(
    incident_id: str,
    user: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    incident = await get_incident(session, user.tenant_id, incident_id)
    events = (
        await session.scalars(
            select(Event)
            .where(Event.tenant_id == user.tenant_id, Event.incident_id == incident_id)
            .order_by(Event.id.desc())
            .limit(100)
        )
    ).all()
    return {**serialize(incident), "events": [serialize(e) for e in reversed(events)]}


@app.patch("/v1/incidents/{incident_id}", tags=["incidents"], response_model=IncidentRead)
async def update_incident(
    incident_id: str,
    body: Transition,
    user: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
):
    return await transition(session, user, incident_id, body)


@app.post("/v1/incidents/{incident_id}/notes", status_code=201, tags=["incidents"])
async def add_note(
    incident_id: str,
    body: Note,
    user: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
):
    await get_incident(session, user.tenant_id, incident_id)
    audit(session, user, "note.added", body.message, incident_id)
    await session.commit()
    return {"saved": True}


@app.post("/v1/incidents/{incident_id}/decisions", status_code=201, tags=["incidents"])
async def decision(
    incident_id: str,
    body: Decision,
    user: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
):
    incident = await get_incident(session, user.tenant_id, incident_id)
    if incident.status == "resolved":
        raise HTTPException(409, "Resolved incidents cannot receive action decisions")
    available = [a["id"] for a in (incident.analysis or {}).get("actions", [])]
    if body.action_id not in available:
        raise HTTPException(409, "Wait for current triage before deciding on this action")
    updated = await session.execute(
        update(Incident)
        .where(
            Incident.id == incident_id,
            Incident.tenant_id == user.tenant_id,
            Incident.version == body.version,
        )
        .values(version=Incident.version + 1, updated_at=now())
    )
    if updated.rowcount != 1:
        await session.rollback()
        raise HTTPException(409, "Incident changed; refresh before deciding")
    audit(
        session,
        user,
        "action.decided",
        f"{body.outcome.title()}: {RUNBOOKS[body.action_id]['title']}",
        incident_id,
        {**body.model_dump(exclude={"version"}), "execution": "manual-external"},
    )
    await session.commit()
    return {"recorded": True, "execution": "manual-external"}


@app.get("/v1/events", tags=["activity"], response_model=list[EventRead])
async def events(
    after: int = Query(default=0, ge=0),
    user: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.scalars(
            select(Event)
            .where(Event.tenant_id == user.tenant_id, Event.id > after)
            .order_by(Event.id.desc())
            .limit(100)
        )
    ).all()
    return [serialize(e) for e in rows]


@app.get("/v1/overview", tags=["overview"], response_model=OverviewRead)
async def overview(
    user: Principal = Depends(principal), session: AsyncSession = Depends(get_session)
):
    all_incidents = (
        await session.scalars(select(Incident).where(Incident.tenant_id == user.tenant_id))
    ).all()
    all_services = (
        await session.scalars(select(Service).where(Service.tenant_id == user.tenant_id))
    ).all()
    active = [i for i in all_incidents if i.status != "resolved"]
    resolved = [
        i
        for i in all_incidents
        if i.resolved_at
        and i.created_at >= (now() - timedelta(days=30)).replace(tzinfo=i.created_at.tzinfo)
    ]
    durations = [(i.resolved_at - i.created_at).total_seconds() / 60 for i in resolved]
    days = [(now() - timedelta(days=d)).date() for d in reversed(range(14))]
    history = [
        {
            "date": str(day),
            "opened": sum(i.created_at.date() == day for i in all_incidents),
            "resolved": sum(
                i.resolved_at is not None and i.resolved_at.date() == day for i in all_incidents
            ),
        }
        for day in days
    ]
    risks = []
    for service in all_services:
        service_incidents = [i for i in active if i.service_id == service.id]
        burn = max(
            (burn_rates(i.evidence, service.slo)["1h"] for i in service_incidents), default=0
        )
        risks.append(
            {
                "id": service.id,
                "name": service.name,
                "team": service.team,
                "slo": service.slo,
                "burn_rate": burn,
                "active": len(service_incidents),
            }
        )
    jobs = (
        await session.execute(
            select(Job.status, func.count())
            .where(Job.tenant_id == user.tenant_id)
            .group_by(Job.status)
        )
    ).all()
    return {
        "active_incidents": len(active),
        "critical_incidents": sum(i.severity == "SEV1" for i in active),
        "service_count": len(all_services),
        "unaffected_services": sum(r["active"] == 0 for r in risks),
        "mttr_minutes": round(sum(durations) / len(durations), 1) if durations else None,
        "resolved_30d": len(resolved),
        "history": history,
        "services": sorted(risks, key=lambda r: r["burn_rate"], reverse=True),
        "jobs": dict(jobs),
        "as_of": now(),
    }


@app.get("/v1/jobs", tags=["operations"], response_model=list[JobRead])
async def jobs(user: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    rows = (
        await session.scalars(
            select(Job)
            .where(Job.tenant_id == user.tenant_id)
            .order_by(Job.created_at.desc())
            .limit(50)
        )
    ).all()
    return [{k: v for k, v in serialize(row).items() if k != "lease_token"} for row in rows]


@app.post("/v1/jobs/{job_id}/retry", tags=["operations"])
async def retry_job(
    job_id: str, user: Principal = Depends(admin), session: AsyncSession = Depends(get_session)
):
    job = await session.scalar(
        select(Job).where(Job.id == job_id, Job.tenant_id == user.tenant_id).with_for_update()
    )
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != "dead":
        raise HTTPException(409, "Only dead jobs can be retried")
    job.status, job.attempts, job.available_at, job.error = "pending", 0, now(), None
    audit(session, user, "job.retried", "Manually retried failed triage", job.incident_id)
    await session.commit()
    return {"queued": True}


@app.get("/v1/stream", tags=["activity"])
async def stream(
    request: Request,
    after: int = Query(default=0, ge=0),
    last_event_id: int | None = Header(default=None, ge=0),
    user: Principal = Depends(principal),
):
    # Close within a minute, forcing session revalidation on reconnect.
    # Database cursors are authoritative; Redis messages are wake-up hints only.
    factory = request.app.state.session_factory

    async def generate():
        cursor = last_event_id if last_event_id is not None else after
        deadline = time.monotonic() + 55
        pubsub = request.app.state.redis.pubsub()
        connected = False
        try:
            try:
                await pubsub.subscribe(f"stratum:events:{user.tenant_id}")
                connected = True
            except RedisError:
                pass
            while time.monotonic() < deadline and not await request.is_disconnected():
                async with factory() as session:
                    rows = (
                        await session.scalars(
                            select(Event)
                            .where(Event.tenant_id == user.tenant_id, Event.id > cursor)
                            .order_by(Event.id)
                            .limit(100)
                        )
                    ).all()
                for event in rows:
                    cursor = event.id
                    data = json.dumps(jsonable_encoder(serialize(event)))
                    yield f"id: {cursor}\nevent: activity\ndata: {data}\n\n"
                if rows:
                    continue
                yield ": heartbeat\n\n"
                if connected:
                    try:
                        await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
                    except RedisError:
                        connected = False
                else:
                    await asyncio.sleep(2)
        finally:
            with contextlib.suppress(RedisError):
                await pubsub.aclose()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
