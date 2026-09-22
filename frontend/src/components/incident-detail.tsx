"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, relativeTime } from "@/lib/api";
import type { Incident, Service, User } from "@/lib/types";
import { Badge, Modal } from "./ui";
import { Icon } from "./icon";

export function IncidentDetail({
  id,
  services,
  user,
  close,
}: {
  id: string;
  services: Service[];
  user: User;
  close: () => void;
}) {
  const client = useQueryClient();
  const detail = useQuery({
    queryKey: ["incident", id],
    queryFn: () => api<Incident>(`/incidents/${id}`),
    refetchInterval: 8000,
  });
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [success, setSuccess] = useState("");
  const canWrite = user.role !== "viewer";
  const mutation = useMutation({
    mutationFn: ({
      path,
      body,
      method = "POST",
    }: {
      path: string;
      body: unknown;
      method?: string;
    }) => api(`/incidents/${id}${path}`, { method, body: JSON.stringify(body) }),
    onSuccess: async (_result, variables) => {
      const submitted = variables.body as { note?: string; message?: string };
      const sentNote = variables.path === "/notes" ? submitted.message : submitted.note;
      // A response may arrive after the operator has begun the next note.
      // Clear only the submitted text, never a newer unsaved draft.
      if (sentNote !== undefined) setNote((current) => (current === sentNote ? "" : current));
      setSuccess("Saved to the incident timeline.");
      await client.invalidateQueries();
    },
    onError: () => {
      setSuccess("");
      client.invalidateQueries({ queryKey: ["incident", id] });
    },
  });
  const i = detail.data;
  const next =
    i?.status === "open"
      ? "acknowledged"
      : i?.status === "acknowledged"
        ? "mitigating"
        : i?.status === "mitigating"
          ? "resolved"
          : null;
  return (
    <Modal
      title={i ? `INC-${i.id.slice(0, 6).toUpperCase()}` : "Incident details"}
      drawer
      onClose={close}
    >
      {detail.error && (
        <p className="error-message" role="alert">
          {detail.error.message}
        </p>
      )}
      {!i && !detail.error && <div className="loading">Loading incident context…</div>}
      {i && (
        <>
          <div className="detail-title">
            <div className="badge-row">
              <Badge value={i.severity} />
              <Badge value={i.status} />
            </div>
            <h2>{i.title}</h2>
            <p>
              {services.find((s) => s.id === i.service_id)?.name} <span>·</span>{" "}
              {relativeTime(i.created_at)} <span>·</span> {i.signal_count} signals
            </p>
          </div>
          <div className="detail-facts">
            <div>
              <span>INCIDENT OWNER</span>
              <strong>{i.owner || "Unassigned"}</strong>
            </div>
            <div>
              <span>ERROR RATE · 5M</span>
              <strong>{i.evidence.error_rate_5m}%</strong>
            </div>
            <div>
              <span>P95 LATENCY</span>
              <strong>
                {i.evidence.latency_p95_ms} <small>ms</small>
              </strong>
            </div>
          </div>
          <section className="triage-panel">
            <div className="section-heading">
              <h3>
                <Icon name="bolt" /> Evidence-based triage
              </h3>
              <span className="mono tiny">{i.analysis?.engine || "QUEUED"}</span>
            </div>
            {i.analysis ? (
              <>
                <h4>{i.analysis.summary}</h4>
                <ul className="evidence-list">
                  {i.analysis.evidence.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
                <div className="burn-windows">
                  {Object.entries(i.analysis.burn_rates).map(([window, burn]) => (
                    <div key={window}>
                      <span>{window.toUpperCase()} BURN</span>
                      <strong>{burn}×</strong>
                    </div>
                  ))}
                </div>
                {i.analysis.model_summary && (
                  <div className="model-note">
                    <strong>Model-assisted summary · verify independently</strong>
                    <p>{i.analysis.model_summary}</p>
                  </div>
                )}
                {i.analysis.model_status === "unavailable" && (
                  <p className="muted tiny">
                    Model gateway unavailable. Deterministic triage is complete.
                  </p>
                )}
              </>
            ) : (
              <p className="muted">
                A durable background job is evaluating this evidence. This panel updates
                automatically.
              </p>
            )}
          </section>
          {i.analysis && (
            <section className="detail-section">
              <h3>Suggested investigation</h3>
              <p className="muted small">
                Approval records an operator decision. Runbook steps are performed manually in your
                own tools.
              </p>
              {i.analysis.actions.map((action) => (
                <details className="runbook" key={action.id}>
                  <summary>
                    <span>
                      <Icon name="log" />
                      {action.title}
                    </span>
                    <Icon name="down" size={14} />
                  </summary>
                  <ol>
                    {action.steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                  {canWrite && i.status !== "resolved" && (
                    <div className="decision">
                      <label>
                        Decision rationale
                        <input
                          placeholder="Why is this the right next step?"
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          maxLength={1000}
                        />
                      </label>
                      <div className="button-row">
                        {["approved", "rejected"].map((outcome) => (
                          <button
                            key={outcome}
                            className="secondary small-button"
                            disabled={reason.trim().length < 5 || mutation.isPending}
                            onClick={() =>
                              mutation.mutate({
                                path: "/decisions",
                                body: { action_id: action.id, outcome, reason, version: i.version },
                              })
                            }
                          >
                            {outcome === "approved" ? "Approve investigation" : "Reject"}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </details>
              ))}
            </section>
          )}
          <section className="detail-section">
            <h3>Incident timeline</h3>
            <div className="timeline">
              {i.events?.map((event) => (
                <div className="timeline-item" key={event.id}>
                  <span
                    className={`timeline-dot ${event.kind.includes("completed") ? "accent" : ""}`}
                  />
                  <div>
                    <div className="timeline-top">
                      <strong>{event.actor}</strong>
                      <span>{relativeTime(event.created_at)}</span>
                    </div>
                    <p>{event.message}</p>
                    {typeof event.details.reason === "string" && (
                      <blockquote>{event.details.reason}</blockquote>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
          {canWrite && (
            <section className="detail-section response-form">
              <label>
                Response note
                <textarea
                  value={note}
                  onChange={(e) => {
                    setNote(e.target.value);
                    setSuccess("");
                  }}
                  rows={3}
                  maxLength={2000}
                  placeholder={
                    next === "resolved"
                      ? "Describe the fix and how recovery was verified (10+ characters)."
                      : "Share findings with the next responder…"
                  }
                />
              </label>
              {mutation.error && (
                <p className="error-message" role="alert">
                  {mutation.error.message}
                </p>
              )}
              {success && (
                <p className="success-message" role="status">
                  {success}
                </p>
              )}
              <div className="button-row">
                <button
                  className="secondary"
                  disabled={!note.trim() || mutation.isPending}
                  onClick={() => mutation.mutate({ path: "/notes", body: { message: note } })}
                >
                  Add note
                </button>
                {next && (
                  <button
                    className="primary"
                    disabled={
                      mutation.isPending || (next === "resolved" && note.trim().length < 10)
                    }
                    onClick={() =>
                      mutation.mutate({
                        path: "",
                        method: "PATCH",
                        body: { status: next, version: i.version, note },
                      })
                    }
                  >
                    {next === "acknowledged"
                      ? "Acknowledge incident"
                      : next === "mitigating"
                        ? "Begin mitigation"
                        : "Resolve incident"}
                    <Icon name="check" size={16} />
                  </button>
                )}
              </div>
            </section>
          )}
        </>
      )}
    </Modal>
  );
}
