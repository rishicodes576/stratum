"use client";
import { relativeTime } from "@/lib/api";
import type { Incident, Service } from "@/lib/types";
import { Badge } from "./ui";
import { Icon } from "./icon";

export function IncidentTable({
  incidents,
  services,
  open,
  compact = false,
}: {
  incidents: Incident[];
  services: Service[];
  open: (id: string) => void;
  compact?: boolean;
}) {
  if (!incidents.length)
    return (
      <div className="empty">
        <Icon name="shield" size={30} />
        <h3>All clear here.</h3>
        <p>No incidents match this view.</p>
      </div>
    );
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Incident</th>
            <th>Severity</th>
            <th>Status</th>
            {!compact && <th>Owner</th>}
            <th>Opened</th>
            <th>
              <span className="sr-only">Details</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((i) => (
            <tr key={i.id}>
              <td>
                <button className="incident-title" onClick={() => open(i.id)}>
                  {i.title}
                </button>
                <div className="table-secondary">
                  <span className="mono">INC-{i.id.slice(0, 6).toUpperCase()}</span>
                  <span>·</span>
                  {services.find((s) => s.id === i.service_id)?.name || "Service"}
                  <span>·</span>
                  {i.signal_count} signal{i.signal_count === 1 ? "" : "s"}
                </div>
              </td>
              <td>
                <Badge value={i.severity} />
              </td>
              <td>
                <Badge value={i.status} />
              </td>
              {!compact && <td className="muted">{i.owner || "Unassigned"}</td>}
              <td className="muted nowrap">{relativeTime(i.created_at)}</td>
              <td>
                <button
                  className="icon-button"
                  aria-label={`Open ${i.title}`}
                  onClick={() => open(i.id)}
                >
                  <Icon name="arrow" size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
