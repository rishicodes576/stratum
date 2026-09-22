from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class Evidence(StrictModel):
    error_rate_5m: float = Field(ge=0, le=100, description="Percentage, e.g. 2.5 = 2.5%")
    error_rate_1h: float = Field(ge=0, le=100)
    error_rate_6h: float = Field(ge=0, le=100)
    latency_p95_ms: float = Field(ge=0, le=3600000)
    requests_per_minute: int = Field(ge=0, le=1000000000)
    deployment: str | None = Field(default=None, max_length=120)
    observed_at: str | None = Field(default=None, max_length=50)


class Signal(StrictModel):
    service_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=5, max_length=180)
    fingerprint: str = Field(min_length=3, max_length=120, pattern=r"^[a-zA-Z0-9._:-]+$")
    evidence: Evidence


class Transition(StrictModel):
    status: Literal["acknowledged", "mitigating", "resolved"]
    version: int = Field(ge=1)
    note: str = Field(default="", max_length=2000)


class Note(StrictModel):
    message: str = Field(min_length=1, max_length=2000)


class Decision(StrictModel):
    action_id: Literal["inspect-deployment", "inspect-dependencies", "review-capacity"]
    outcome: Literal["approved", "rejected"]
    reason: str = Field(min_length=5, max_length=1000)
    version: int = Field(ge=1)


class ServiceCreate(StrictModel):
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=2, max_length=120)
    team: str = Field(min_length=2, max_length=80)
    tier: int = Field(default=1, ge=1, le=3)
    slo: float = Field(default=99.9, ge=90, le=99.999)
    description: str = Field(default="", max_length=500)
    dependencies: list[str] = Field(default_factory=list, max_length=20)


class ActionRead(BaseModel):
    id: str
    title: str
    risk: str
    steps: list[str]


class AnalysisRead(BaseModel):
    engine: str
    severity: str
    burn_rates: dict[str, float]
    summary: str
    evidence: list[str]
    actions: list[ActionRead]
    model_summary: str | None
    model_status: str


class IncidentRead(BaseModel):
    id: str
    tenant_id: str
    service_id: str
    title: str
    fingerprint: str
    severity: Literal["SEV1", "SEV2", "SEV3"]
    status: Literal["open", "acknowledged", "mitigating", "resolved"]
    owner: str | None
    version: int
    signal_count: int
    evidence: Evidence
    analysis: AnalysisRead | None
    created_at: datetime
    updated_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class EventRead(BaseModel):
    id: int
    tenant_id: str
    incident_id: str | None
    kind: str
    actor: str
    message: str
    details: dict[str, Any]
    created_at: datetime


class IncidentDetailRead(IncidentRead):
    events: list[EventRead]


class IncidentPage(BaseModel):
    items: list[IncidentRead]
    next_cursor: str | None


class ServiceRead(ServiceCreate):
    id: str
    tenant_id: str
    tier: int
    slo: float
    description: str
    dependencies: list[str]


class ServiceView(ServiceRead):
    active_incidents: int
    latest_evidence: Evidence | None


class UserRead(BaseModel):
    id: str
    tenant_id: str
    name: str
    email: str
    role: str
    workspace: str


class SignalReceipt(BaseModel):
    incident_id: str
    job_id: str
    correlated: bool
    replayed: bool


class JobRead(BaseModel):
    id: str
    tenant_id: str
    incident_id: str
    status: str
    attempts: int
    available_at: datetime
    lease_until: datetime | None
    error: str | None
    created_at: datetime


class HistoryDay(BaseModel):
    date: str
    opened: int
    resolved: int


class ServiceRisk(BaseModel):
    id: str
    name: str
    team: str
    slo: float
    burn_rate: float
    active: int


class OverviewRead(BaseModel):
    active_incidents: int
    critical_incidents: int
    service_count: int
    unaffected_services: int
    mttr_minutes: float | None
    resolved_30d: int
    history: list[HistoryDay]
    services: list[ServiceRisk]
    jobs: dict[str, int]
    as_of: datetime
