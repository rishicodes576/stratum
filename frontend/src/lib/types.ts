import type { components } from "./schema";

export type Evidence = components["schemas"]["Evidence"];
export type Action = components["schemas"]["ActionRead"];
export type Analysis = components["schemas"]["AnalysisRead"];
export type AuditEvent = components["schemas"]["EventRead"];
export type Incident = components["schemas"]["IncidentRead"] & { events?: AuditEvent[] };
export type Service = components["schemas"]["ServiceView"];
export type Overview = components["schemas"]["OverviewRead"];
export type User = components["schemas"]["UserRead"];
export type Job = components["schemas"]["JobRead"];
