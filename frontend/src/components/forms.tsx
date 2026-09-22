"use client";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Service } from "@/lib/types";
import { Modal } from "./ui";
import { Icon } from "./icon";

export function SignalForm({
  services,
  onClose,
  onCreated,
}: {
  services: Service[];
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [key, setKey] = useState(() => crypto.randomUUID());
  const mutation = useMutation({
    mutationFn: (body: unknown) =>
      api<{ incident_id: string }>("/signals", {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify(body),
      }),
    onSuccess: (r) => onCreated(r.incident_id),
  });
  return (
    <Modal title="Send a service signal" onClose={onClose}>
      <p className="modal-intro">
        Turn an observation into an incident. Matching fingerprints correlate into the same active
        incident.
      </p>
      <form
        onChange={() => setKey(crypto.randomUUID())}
        onSubmit={(event) => {
          event.preventDefault();
          const f = new FormData(event.currentTarget);
          mutation.mutate({
            service_id: f.get("service"),
            title: f.get("title"),
            fingerprint: f.get("fingerprint"),
            evidence: {
              error_rate_5m: Number(f.get("error5")),
              error_rate_1h: Number(f.get("error1")),
              error_rate_6h: Number(f.get("error6")),
              latency_p95_ms: Number(f.get("latency")),
              requests_per_minute: Number(f.get("rpm")),
              deployment: f.get("deployment") || null,
            },
          });
        }}
      >
        <label>
          Service
          <select name="service" aria-label="Service" required>
            {services.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Incident title
          <input
            name="title"
            placeholder="Elevated errors on the checkout path"
            minLength={5}
            maxLength={180}
            required
          />
        </label>
        <label>
          Correlation fingerprint
          <input
            name="fingerprint"
            placeholder="checkout.http.5xx"
            pattern="[a-zA-Z0-9._:\-]+"
            minLength={3}
            maxLength={120}
            required
          />
        </label>
        <div className="form-grid three">
          <label>
            Error rate · 5m (%)
            <input
              name="error5"
              type="number"
              min="0"
              max="100"
              step="0.001"
              defaultValue="2.4"
              required
            />
          </label>
          <label>
            Error rate · 1h (%)
            <input
              name="error1"
              type="number"
              min="0"
              max="100"
              step="0.001"
              defaultValue="1.8"
              required
            />
          </label>
          <label>
            Error rate · 6h (%)
            <input
              name="error6"
              type="number"
              min="0"
              max="100"
              step="0.001"
              defaultValue="0.7"
              required
            />
          </label>
        </div>
        <div className="form-grid">
          <label>
            p95 latency (ms)
            <input name="latency" type="number" min="0" max="3600000" defaultValue="840" required />
          </label>
          <label>
            Requests / minute
            <input
              name="rpm"
              type="number"
              min="0"
              max="1000000000"
              defaultValue="12500"
              required
            />
          </label>
        </div>
        <label>
          Deployment reference (optional)
          <input name="deployment" placeholder="api-v2.8.1" maxLength={120} />
        </label>
        <div className="info-callout">
          <Icon name="bolt" />
          <span>
            Severity is calculated from your service SLO. Triage runs asynchronously after the
            signal is durably stored.
          </span>
        </div>
        {mutation.error && (
          <p className="error-message" role="alert">
            {mutation.error.message}
          </p>
        )}
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="primary" disabled={mutation.isPending || !services.length}>
            {mutation.isPending ? "Sending…" : "Send signal"}
            <Icon name="arrow" />
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function ServiceForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const mutation = useMutation({
    mutationFn: (body: unknown) => api("/services", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: onCreated,
  });
  return (
    <Modal title="Register a service" onClose={onClose}>
      <p className="modal-intro">Give every signal an owner and an objective.</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          mutation.mutate({
            name: f.get("name"),
            slug: f.get("slug"),
            team: f.get("team"),
            tier: Number(f.get("tier")),
            slo: Number(f.get("slo")),
            description: f.get("description"),
            dependencies: String(f.get("dependencies"))
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
          });
        }}
      >
        <label>
          Service name
          <input name="name" minLength={2} maxLength={120} required />
        </label>
        <label>
          Unique slug
          <input
            name="slug"
            pattern="[a-z0-9-]+"
            minLength={2}
            maxLength={80}
            placeholder="checkout-api"
            required
          />
        </label>
        <label>
          Owning team
          <input name="team" minLength={2} maxLength={80} required />
        </label>
        <div className="form-grid">
          <label>
            Service tier
            <select name="tier">
              <option value="1">Tier 1 · Critical</option>
              <option value="2">Tier 2 · Important</option>
              <option value="3">Tier 3 · Supporting</option>
            </select>
          </label>
          <label>
            Availability SLO (%)
            <input
              name="slo"
              type="number"
              min="90"
              max="99.999"
              step="0.001"
              defaultValue="99.9"
              required
            />
          </label>
        </div>
        <label>
          Description
          <textarea name="description" maxLength={500} rows={2} />
        </label>
        <label>
          Dependencies (comma separated)
          <input name="dependencies" placeholder="postgres, redis" />
        </label>
        {mutation.error && (
          <p className="error-message" role="alert">
            {mutation.error.message}
          </p>
        )}
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="primary" disabled={mutation.isPending}>
            {mutation.isPending ? "Registering…" : "Register service"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
