"use client";

import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, relativeTime } from "@/lib/api";
import type { AuditEvent, Incident, Job, Overview, Service, User } from "@/lib/types";
import { Icon } from "./icon";

type View = "overview" | "incidents" | "services" | "activity" | "jobs";
const navigation: { id: View; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "grid" },
  { id: "incidents", label: "Incidents", icon: "pulse" },
  { id: "services", label: "Service catalog", icon: "layers" },
  { id: "activity", label: "Activity log", icon: "clock" },
  { id: "jobs", label: "Job operations", icon: "bolt" },
];

import { Badge, Modal } from "./ui";
import { Login } from "./login";
import { History } from "./history";
import { IncidentTable } from "./incident-table";
import { SignalForm, ServiceForm } from "./forms";
import { IncidentDetail } from "./incident-detail";

export function Console() {
  const client = useQueryClient();
  const [view, setView] = useState<View>("overview");
  const [selected, setSelected] = useState<string | null>(null);
  const [signalOpen, setSignalOpen] = useState(false);
  const [serviceOpen, setServiceOpen] = useState(false);
  const [architecture, setArchitecture] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("active");
  const [cursor, setCursor] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState("Connecting");
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/me"),
    retry: false,
    refetchInterval: 60000,
  });
  const enabled = !!me.data && !me.error;
  const overview = useQuery({
    queryKey: ["overview"],
    queryFn: () => api<Overview>("/overview"),
    enabled,
    refetchInterval: 30000,
  });
  const services = useQuery({
    queryKey: ["services"],
    queryFn: () => api<Service[]>("/services"),
    enabled,
  });
  const incidents = useQuery({
    queryKey: ["incidents", cursor, filter],
    queryFn: () =>
      api<{ items: Incident[]; next_cursor: string | null }>(
        `/incidents?limit=100${cursor ? `&before=${cursor}` : ""}${filter !== "all" ? `&status=${filter}` : ""}`,
      ),
    enabled,
  });
  const events = useQuery({
    queryKey: ["events"],
    queryFn: () => api<AuditEvent[]>("/events"),
    enabled,
  });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api<Job[]>("/jobs"),
    enabled,
    refetchInterval: 15000,
  });
  const retryJob = useMutation({
    mutationFn: (id: string) => api(`/jobs/${id}/retry`, { method: "POST", body: "{}" }),
    onSuccess: () => client.invalidateQueries(),
  });
  const logout = useMutation({
    mutationFn: () => api("/auth/logout", { method: "POST", body: "{}" }),
    onSuccess: () => {
      setSelected(null);
      client.clear();
      client.invalidateQueries();
    },
  });
  const refresh = useCallback(() => {
    for (const key of ["overview", "incidents", "services", "events", "jobs", "incident"])
      client.invalidateQueries({ queryKey: [key] });
  }, [client]);
  useEffect(() => {
    if (!enabled) return;
    const source = new EventSource("/api/v1/stream");
    let timer: ReturnType<typeof setTimeout> | undefined;
    source.onopen = () => setStreamStatus("Live");
    source.onerror = () => setStreamStatus("Reconnecting");
    source.addEventListener("activity", () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(refresh, 250);
    });
    const fallback = setInterval(refresh, 30000);
    return () => {
      source.close();
      clearInterval(fallback);
      if (timer) clearTimeout(timer);
    };
  }, [enabled, refresh]);
  if (me.isPending)
    return (
      <main className="center-state">
        <div className="brand-mark">
          <Icon name="layers" size={30} />
        </div>
        <p>Connecting to your workspace…</p>
      </main>
    );
  if (me.error instanceof ApiError && me.error.status === 401)
    return (
      <Login
        onLogin={() => {
          client.clear();
          me.refetch();
        }}
      />
    );
  if (me.error || !me.data)
    return (
      <main className="center-state">
        <h1>Workspace unavailable</h1>
        <p>{me.error?.message}</p>
        <button className="primary" onClick={() => me.refetch()}>
          Try again
        </button>
      </main>
    );
  const user = me.data;
  const serviceRows = services.data || [];
  const incidentRows = incidents.data?.items || [];
  const active = incidentRows.filter((i) => i.status !== "resolved");
  const filtered = incidentRows.filter(
    (i) =>
      (filter !== "active" || i.status !== "resolved") &&
      `${i.title} ${i.id} ${serviceRows.find((s) => s.id === i.service_id)?.name}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const stats = overview.data;
  const dataError =
    overview.error || services.error || incidents.error || events.error || jobs.error;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="Stratum home">
          <div className="brand-mark">
            <Icon name="layers" size={24} />
          </div>
          stratum<span className="brand-period">.</span>
        </a>
        <div className="workspace">
          <div className="workspace-avatar">A</div>
          <div>
            <strong>{user.workspace}</strong>
            <span>Reliability workspace</span>
          </div>
          <span className="workspace-indicator" />
        </div>
        <span className="nav-label">WORKSPACE</span>
        <nav aria-label="Primary navigation">
          {navigation.map((item) => (
            <button
              key={item.id}
              aria-label={item.label}
              title={item.label}
              className={`nav-item ${view === item.id ? "active" : ""}`}
              onClick={() => {
                setView(item.id);
                setSearch("");
                setCursor(null);
                setFilter("active");
              }}
              aria-current={view === item.id ? "page" : undefined}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {item.id === "incidents" && !!stats?.active_incidents && (
                <span className="nav-count">{stats.active_incidents}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="system-card">
            <div>
              <span className="live-dot" />
              <strong>Evidence over guesswork.</strong>
            </div>
            <p>
              Every signal has context.
              <br />
              Every decision has a trail.
            </p>
            <button onClick={() => setArchitecture(true)}>
              Explore the architecture <Icon name="arrow" size={14} />
            </button>
          </div>
          <button
            className="profile"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
            aria-label="Sign out"
          >
            <span className="avatar">
              {user.name
                .split(" ")
                .map((n) => n[0])
                .slice(0, 2)
                .join("")}
            </span>
            <span>
              <strong>{user.name}</strong>
              <small>{user.role}</small>
            </span>
            <Icon name="logout" size={16} />
          </button>
          {logout.error && (
            <span role="alert" className="error-message">
              {logout.error.message}
            </span>
          )}
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span>
            <strong>{navigation.find((n) => n.id === view)?.label}</strong>
          </div>
          <div className="topbar-right">
            <span className="environment">
              <span className="dot" />
              {process.env.NEXT_PUBLIC_DEMO_MODE === "true" ? "Demo environment" : "Workspace"}
            </span>
            <span className={`stream-state ${streamStatus === "Live" ? "online" : ""}`}>
              <span className="live-dot" />
              {streamStatus}
            </span>
          </div>
        </header>
        <main id="main" className="main-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {view === "overview"
                  ? "THE BIG PICTURE"
                  : view === "incidents"
                    ? "SIGNALS INTO ACTION"
                    : view === "services"
                      ? "KNOW YOUR SYSTEM"
                      : view === "activity"
                        ? "NOTHING LOST IN THE HANDOFF"
                        : "RELIABILITY UNDER THE HOOD"}
              </div>
              <h1>
                {view === "overview"
                  ? "Reliability overview"
                  : navigation.find((n) => n.id === view)?.label}
                <span className="heading-dot">.</span>
              </h1>
              <p>
                {view === "overview"
                  ? "Your systems, signals, and response. All in one place."
                  : view === "incidents"
                    ? "Investigate the signal. Coordinate the response. Close the loop."
                    : view === "services"
                      ? "Ownership, objectives, and dependencies for every service."
                      : view === "activity"
                        ? "A shared record of what happened, and why."
                        : "Durable triage jobs, recoverable by design."}
              </p>
            </div>
            <div className="page-actions">
              <button
                className="secondary icon-button"
                title="Refresh data"
                aria-label="Refresh data"
                onClick={refresh}
              >
                <Icon name="retry" />
              </button>
              {view === "services" && user.role === "admin" ? (
                <button className="primary" onClick={() => setServiceOpen(true)}>
                  <Icon name="plus" size={16} />
                  Register service
                </button>
              ) : (
                user.role !== "viewer" && (
                  <button className="primary" onClick={() => setSignalOpen(true)}>
                    <Icon name="plus" size={16} />
                    Send signal
                  </button>
                )
              )}
            </div>
          </div>
          {dataError && (
            <div className="error-banner" role="alert">
              <Icon name="alert" />
              {dataError.message}
              <button onClick={refresh}>Retry</button>
            </div>
          )}
          {view === "overview" && (
            <>
              <div className="summary-strip">
                <span className="summary-icon">
                  <Icon name="pulse" size={18} />
                </span>
                <strong>
                  {stats
                    ? stats.active_incidents
                      ? `${stats.active_incidents} active incidents need your attention`
                      : "No active incidents in this workspace"
                    : "Loading workspace health…"}
                </strong>
                <span className="summary-detail">
                  {stats?.critical_incidents
                    ? `${stats.critical_incidents} critical · Response in progress`
                    : "Keep your next response in context"}
                </span>
                <button onClick={() => setView("incidents")} aria-label="View active incidents">
                  <Icon name="arrow" />
                </button>
              </div>
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-label">
                    Active incidents
                    <Icon name="pulse" />
                  </div>
                  <div className="stat-value">
                    {stats?.active_incidents ?? "—"}
                    <span className="stat-detail amber">
                      {stats?.critical_incidents ?? 0} critical
                    </span>
                  </div>
                  <div className="stat-footer">
                    <span className="amber-dot" />
                    Across your service catalog
                  </div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">
                    Services without incidents
                    <Icon name="layers" />
                  </div>
                  <div className="stat-value">
                    {stats?.unaffected_services ?? "—"}
                    <span className="denominator">/ {stats?.service_count ?? "—"}</span>
                  </div>
                  <div className="mini-segments">
                    {stats?.services.map((s) => (
                      <span
                        key={s.id}
                        className={s.active ? "warning" : "healthy"}
                        title={`${s.name}: ${s.active} active incidents`}
                      />
                    ))}
                  </div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">
                    Mean time to resolve
                    <Icon name="clock" />
                  </div>
                  <div className="stat-value">
                    {stats?.mttr_minutes ?? "—"}
                    <span className="denominator">min</span>
                  </div>
                  <div className="stat-footer">
                    {stats?.resolved_30d ?? 0} resolved incidents · Last 30 days
                  </div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">
                    Triage jobs completed
                    <Icon name="bolt" />
                  </div>
                  <div className="stat-value">
                    {stats?.jobs.done ?? "—"}
                    <span className="stat-detail green">Evidence ready</span>
                  </div>
                  <div className="stat-footer">
                    {(stats?.jobs.pending || 0) + (stats?.jobs.running || 0)} in progress ·{" "}
                    {stats?.jobs.dead || 0} failed
                  </div>
                </div>
              </div>
              <div className="overview-middle">
                <section className="panel trend-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Incident pulse</h2>
                      <p>A clearer view of your response rhythm.</p>
                    </div>
                    <span className="period-pill">
                      <Icon name="clock" size={13} />
                      Last 14 days
                    </span>
                  </div>
                  <div className="chart-legend">
                    <span>
                      <i />
                      Opened
                    </span>
                    <span>
                      <i className="resolved-legend" />
                      Resolved
                    </span>
                    <span className="chart-caption">INCIDENTS / DAY</span>
                  </div>
                  {stats ? (
                    <History data={stats.history} />
                  ) : (
                    <div className="loading">Loading incident history…</div>
                  )}
                </section>
                <section className="panel risk-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Error-budget burn</h2>
                      <p>1-hour burn against each service SLO.</p>
                    </div>
                    <Icon name="shield" />
                  </div>
                  <div className="risk-list">
                    {stats?.services.slice(0, 4).map((s) => (
                      <button key={s.id} className="risk-row" onClick={() => setView("services")}>
                        <div>
                          <span>{s.name}</span>
                          <strong className={s.burn_rate >= 6 ? "amber" : "green"}>
                            {s.active ? `${s.burn_rate.toFixed(1)}×` : "No signal"}
                          </strong>
                        </div>
                        <div className="risk-track">
                          <span
                            style={{
                              width: `${s.active ? Math.min(100, (s.burn_rate / 30) * 100) : 0}%`,
                            }}
                          />
                        </div>
                        <small>
                          {s.slo}% objective{" "}
                          <span>
                            {s.active
                              ? `${s.active} active incident${s.active === 1 ? "" : "s"}`
                              : "No active incidents"}
                          </span>
                        </small>
                      </button>
                    ))}
                  </div>
                  <p className="risk-note">
                    Based on latest active alert evidence, not continuous telemetry.
                  </p>
                </section>
              </div>
              <section className="panel incidents-panel">
                <div className="panel-heading">
                  <div className="heading-inline">
                    <h2>Active incidents</h2>
                    <span className="count-pill">{stats?.active_incidents ?? "—"}</span>
                  </div>
                  <button className="text-button" onClick={() => setView("incidents")}>
                    View all incidents
                    <Icon name="arrow" size={14} />
                  </button>
                </div>
                <IncidentTable
                  incidents={active.slice(0, 5)}
                  services={serviceRows}
                  open={setSelected}
                  compact
                />
              </section>
              <div className="overview-bottom">
                <span>
                  <Icon name="shield" size={14} /> Every change is recorded. Every response is
                  accountable.
                </span>
                <span>{stats ? `Updated ${relativeTime(stats.as_of)}` : "Connecting…"}</span>
              </div>
            </>
          )}
          {view === "incidents" && (
            <section className="panel">
              <div className="list-toolbar">
                <div className="tabs" role="group" aria-label="Incident status">
                  {["active", "resolved", "all"].map((value) => (
                    <button
                      key={value}
                      className={filter === value ? "selected" : ""}
                      onClick={() => {
                        setFilter(value);
                        setCursor(null);
                      }}
                      aria-pressed={filter === value}
                    >
                      {value[0].toUpperCase() + value.slice(1)}
                    </button>
                  ))}
                </div>
                <label className="search-field">
                  <Icon name="search" size={16} />
                  <input
                    placeholder="Search loaded incidents…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    aria-label="Search incidents"
                  />
                </label>
              </div>
              <IncidentTable incidents={filtered} services={serviceRows} open={setSelected} />
              <div className="pagination">
                <span>{filtered.length} incidents on this page</span>
                {cursor && (
                  <button className="secondary small-button" onClick={() => setCursor(null)}>
                    Back to latest
                  </button>
                )}
                {incidents.data?.next_cursor && (
                  <button
                    className="secondary small-button"
                    onClick={() => setCursor(incidents.data!.next_cursor)}
                  >
                    Older incidents <Icon name="arrow" size={14} />
                  </button>
                )}
              </div>
            </section>
          )}
          {view === "services" && (
            <>
              <div className="catalog-intro">
                <span className="mono">
                  {serviceRows.length.toString().padStart(2, "0")} REGISTERED SERVICES
                </span>
                <p>Objectives are configuration. Health is inferred only from ingested signals.</p>
              </div>
              <div className="service-grid">
                {serviceRows.map((service) => (
                  <section className="panel service-card" key={service.id}>
                    <div className="service-card-top">
                      <span className="service-icon">
                        <Icon name={service.tier === 1 ? "layers" : "code"} size={23} />
                      </span>
                      <Badge
                        value={service.active_incidents ? "investigating" : "no_active_incidents"}
                      />
                    </div>
                    <h2>{service.name}</h2>
                    <p>{service.description || "No description provided."}</p>
                    <div className="service-meta">
                      <span>
                        <Icon name="users" size={14} />
                        {service.team}
                      </span>
                      <span>Tier {service.tier}</span>
                    </div>
                    <div className="service-slo">
                      <div>
                        <span>Availability objective</span>
                        <strong>{service.slo}%</strong>
                      </div>
                      <div>
                        <span>Active incidents</span>
                        <strong className={service.active_incidents ? "amber" : "green"}>
                          {service.active_incidents}
                        </strong>
                      </div>
                    </div>
                    <div className="dependencies">
                      <span>DEPENDS ON</span>
                      <div>
                        {service.dependencies.length ? (
                          service.dependencies.map((d) => (
                            <span className="dependency" key={d}>
                              {d}
                            </span>
                          ))
                        ) : (
                          <span className="muted small">No dependencies registered</span>
                        )}
                      </div>
                    </div>
                  </section>
                ))}
              </div>
              {!serviceRows.length && (
                <div className="empty">
                  <h3>Your catalog starts here.</h3>
                  <p>Register a service to start receiving signals.</p>
                </div>
              )}
            </>
          )}
          {view === "activity" && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Workspace activity</h2>
                  <p>The latest 100 events, scoped to your workspace.</p>
                </div>
                <span className="period-pill">
                  <Icon name="shield" size={14} />
                  Audit trail
                </span>
              </div>
              <div className="activity-feed">
                {events.data?.map((event) => (
                  <article className="activity-row" key={event.id}>
                    <div
                      className={`event-icon ${event.kind.includes("resolved") || event.kind.includes("completed") ? "green" : ""}`}
                    >
                      <Icon
                        name={
                          event.kind.includes("completed")
                            ? "bolt"
                            : event.kind.includes("note")
                              ? "log"
                              : "pulse"
                        }
                      />
                    </div>
                    <div>
                      <div className="activity-kind">
                        <strong>{event.actor}</strong>
                        <span className="mono">{event.kind}</span>
                      </div>
                      <p>{event.message}</p>
                      {typeof event.details.reason === "string" && (
                        <p className="muted">{event.details.reason}</p>
                      )}
                      {event.incident_id && (
                        <button
                          className="text-button"
                          onClick={() => setSelected(event.incident_id)}
                        >
                          INC-{event.incident_id.slice(0, 6).toUpperCase()}
                          <Icon name="arrow" size={12} />
                        </button>
                      )}
                    </div>
                    <time>{relativeTime(event.created_at)}</time>
                  </article>
                ))}
                {!events.data?.length && (
                  <div className="empty">
                    No activity yet. Your first signal will start the timeline.
                  </div>
                )}
              </div>
            </section>
          )}
          {view === "jobs" && (
            <>
              <div className="job-summary">
                <div>
                  <Icon name="shield" />
                  <strong>At-least-once processing</strong>
                  <span>Durable database queue</span>
                </div>
                <div>
                  <Icon name="clock" />
                  <strong>45-second leases</strong>
                  <span>Automatic crash recovery</span>
                </div>
                <div>
                  <Icon name="retry" />
                  <strong>4 attempts per job</strong>
                  <span>Exponential retry backoff</span>
                </div>
              </div>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Triage execution</h2>
                    <p>The latest 50 jobs. Failed jobs can be retried by an administrator.</p>
                  </div>
                </div>
                {retryJob.error && (
                  <p className="error-message" role="alert">
                    {retryJob.error.message}
                  </p>
                )}
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Job</th>
                        <th>Incident</th>
                        <th>Status</th>
                        <th>Attempts</th>
                        <th>Created</th>
                        <th>Recovery</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobs.data?.map((job) => (
                        <tr key={job.id}>
                          <td className="mono">{job.id.slice(0, 8)}</td>
                          <td>
                            <button
                              className="text-button mono"
                              onClick={() => setSelected(job.incident_id)}
                            >
                              INC-{job.incident_id.slice(0, 6).toUpperCase()}
                            </button>
                          </td>
                          <td>
                            <Badge value={job.status} />
                          </td>
                          <td>{job.attempts} / 4</td>
                          <td className="muted">{relativeTime(job.created_at)}</td>
                          <td>
                            {job.status === "dead" && user.role === "admin" ? (
                              <button
                                className="secondary small-button"
                                disabled={retryJob.isPending}
                                onClick={() => retryJob.mutate(job.id)}
                              >
                                Retry job
                              </button>
                            ) : (
                              <span className="muted small">{job.error || "—"}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!jobs.data?.length && (
                  <div className="empty">No triage jobs have been created yet.</div>
                )}
              </section>
            </>
          )}
        </main>
        <footer className="app-footer">
          <span>
            <span className="mini-brand">≋</span> STRATUM <span className="muted">/</span>{" "}
            RELIABILITY, IN FOCUS
          </span>
          <span className="mono">v1.0 · Built for the on-call</span>
        </footer>
      </div>
      {signalOpen && (
        <SignalForm
          services={serviceRows}
          onClose={() => setSignalOpen(false)}
          onCreated={(id) => {
            setSignalOpen(false);
            setSelected(id);
            refresh();
          }}
        />
      )}
      {serviceOpen && (
        <ServiceForm
          onClose={() => setServiceOpen(false)}
          onCreated={() => {
            setServiceOpen(false);
            refresh();
          }}
        />
      )}
      {selected && (
        <IncidentDetail
          id={selected}
          services={serviceRows}
          user={user}
          close={() => setSelected(null)}
        />
      )}
      {architecture && (
        <Modal title="Designed for the failure cases" onClose={() => setArchitecture(false)}>
          <div className="architecture">
            <p>
              Stratum connects a Next.js operator console to an asynchronous FastAPI service.
              PostgreSQL stores the source of truth. Redis provides rate limits and live-update
              wakeups.
            </p>
            <div className="architecture-flow">
              <span>Signals</span>
              <Icon name="arrow" />
              <span>API + audit</span>
              <Icon name="arrow" />
              <span>Durable jobs</span>
              <Icon name="arrow" />
              <span>Triage</span>
            </div>
            <h3>One transaction, three guarantees.</h3>
            <p>
              An incident, its audit event, and its triage job commit together. Duplicate delivery
              is handled with tenant-scoped idempotency keys and active fingerprint correlation.
            </p>
            <h3>Recovery is part of the workflow.</h3>
            <p>
              Workers claim jobs with database locks and expiring leases. Fencing tokens reject
              stale workers. Retries are bounded; dead jobs remain visible for recovery.
            </p>
            <h3>Evidence has the final word.</h3>
            <p>
              Multi-window error-budget burn determines severity. An optional model gateway may
              summarize evidence, but cannot execute actions or change severity. Investigation
              approvals are recorded for humans to carry out.
            </p>
            <h3>Deliberate boundaries.</h3>
            <p>
              This is an incident coordination system, not a continuous telemetry collector or
              infrastructure executor. SSO, database row-level security, and multi-region failover
              are future deployment work.
            </p>
          </div>
        </Modal>
      )}
    </div>
  );
}
