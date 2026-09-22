from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="operator")


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("tenant_id", "slug"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    team: Mapped[str] = mapped_column(String(80))
    tier: Mapped[int] = mapped_column(Integer, default=1)
    slo: Mapped[float] = mapped_column(default=99.9)
    description: Mapped[str] = mapped_column(String(500), default="")
    dependencies: Mapped[list] = mapped_column(JSON, default=list)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incident_tenant_created", "tenant_id", "created_at"),
        Index(
            "uq_incident_active_fingerprint",
            "tenant_id",
            "service_id",
            "fingerprint",
            unique=True,
            postgresql_where=text("status != 'resolved'"),
            sqlite_where=text("status != 'resolved'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"))
    title: Mapped[str] = mapped_column(String(180))
    fingerprint: Mapped[str] = mapped_column(String(120))
    severity: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(20), default="open")
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    signal_count: Mapped[int] = mapped_column(Integer, default=1)
    evidence: Mapped[dict] = mapped_column(JSON)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_event_tenant_cursor", "tenant_id", "id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(60))
    actor: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(String(2000))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_job_claim", "status", "available_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (UniqueConstraint("tenant_id", "key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    key: Mapped[str] = mapped_column(String(120))
    digest: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
