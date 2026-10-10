import type { components } from "../../lib/api/schema";
import { facilityRequest } from "../../lib/api/facilities";
import type { FacilityListResponse, FacilitySnapshotResponse } from "../../lib/api/feature-1";
import type { IncidentClient } from "./preview-client";
import type { PreviewRevision, PreviewRun } from "./model";
type Schemas = components["schemas"];
export class IncidentRequestError extends Error {
  constructor(message: string, public uncertain: boolean, public existingRevisionId?: string, public fields: { field: string; message: string }[] = []) { super(message); }
}
async function request<T>(path: string, payload?: unknown): Promise<T> {
  const writing = payload !== undefined;
  let response: Response;
  try { response = await fetch(`/api/v1/scenarios${path}`, { cache: "no-store", ...(writing ? { method: "POST", ...(payload === null ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }) } : {}) }); }
  catch { throw new IncidentRequestError(writing ? "The save could not be confirmed. Refresh saved incidents and reopen the revision before trying again." : "Could not connect to the incident API.", writing); }
  let body: unknown;
  try { body = await response.json(); }
  catch { throw new IncidentRequestError(writing ? "The save response could not be read. Refresh saved incidents before trying again." : "The incident response could not be read.", writing && response.status !== 422 && response.status !== 409); }
  if (!response.ok) {
    const detail = (body as Schemas["ScenarioErrorResponse"])?.error;
    throw new IncidentRequestError(response.status >= 500 ? writing ? "The save could not be confirmed. Refresh saved incidents and reopen before trying again." : "The incident API is unavailable." : detail?.message ?? "The incident request failed.", writing && response.status >= 500, detail?.existing_revision_id ?? undefined, Array.isArray(detail?.fields) ? detail.fields : []);
  }
  return body as T;
}
export async function loadIncidentCatalog(): Promise<FacilitySnapshotResponse[]> {
  const list = await facilityRequest<FacilityListResponse>("/api/v1/facilities");
  return Promise.all(list.items.map((item) => facilityRequest<FacilitySnapshotResponse>(`/api/v1/facilities/${encodeURIComponent(item.facility_id)}/snapshot`)));
}
const id = encodeURIComponent;
export function createIncidentApiClient(): IncidentClient {
  const known = new Map<string, Schemas["IncidentRevision"]>();
  const runs = new Map<string, PreviewRun>();
  function presentRevision(revision: Schemas["IncidentRevision"]): PreviewRevision { known.set(revision.revision_id, revision); return { ...revision, baseline: null }; }
  async function getRevision(revisionId: string, incidentId?: string): Promise<PreviewRevision> {
    const incident = incidentId ?? known.get(revisionId)?.incident_id;
    if (!incident) throw new IncidentRequestError("An incident ID is required to reopen this revision. Select it from saved incidents.", false);
    return presentRevision(await request<Schemas["IncidentRevision"]>(`/incidents/${id(incident)}/revisions/${id(revisionId)}`));
  }
  async function presentRun(run: Schemas["SimulationRun"]): Promise<PreviewRun> {
    const revision = await getRevision(run.impact.revision_id, run.impact.incident_id);
    const result: PreviewRun = { run_id: run.run_id, revision_id: run.impact.revision_id, incident_id: run.impact.incident_id, created_at: run.created_at, engine_version: run.engine_version, baseline_id: run.impact.baseline_id, baseline_at: run.impact.baseline_captured_at, input: revision.input,
      rows: run.impact.rows.map((row) => ({ facility_id: row.facility.facility_id, name: row.facility.name, baseline: row.baseline_capacity, scenario: row.scenario_capacity, capacity_change: row.capacity_change, affected: row.affected, applied_overrides: row.applied_overrides })),
    };
    runs.set(result.run_id, result); return result;
  }
  return {
    async list() { const list = await request<Schemas["IncidentListResponse"]>("/incidents"); return { version: 1 as const, revisions: list.items.map(presentRevision), runs: [...runs.values()] }; },
    async saveDraft(input) { return presentRevision(await request<Schemas["IncidentRevision"]>("/incidents", input)); },
    getRevision,
    async confirm(draftId, input, reviewer) {
      const draft = known.get(draftId); if (!draft) throw new IncidentRequestError("Reopen the draft before confirming.", false);
      const payload: Schemas["IncidentConfirmRequest"] = { draft_revision_id: draftId, input: { ...input, service_id: input.service_id!, starts_at: input.starts_at! }, confirmed_by: reviewer.trim() };
      return presentRevision(await request<Schemas["IncidentRevision"]>(`/incidents/${id(draft.incident_id)}/confirm`, payload));
    },
    async simulate(revisionId) {
      const revision = known.get(revisionId); if (!revision) throw new IncidentRequestError("Reopen the confirmed revision before simulating.", false);
      // Endpoint has no request body; POST is explicit and never automatically retried.
      return presentRun(await request<Schemas["SimulationRun"]>(`/incidents/${id(revision.incident_id)}/revisions/${id(revisionId)}/simulate`, null));
    },
    async getRun(runId) { return presentRun(await request<Schemas["SimulationRun"]>(`/runs/${id(runId)}`)); },
    async assess() { return { status: "unavailable", answers: [], model: null, elapsed_ms: null, rubric_version: "emergency-review-v1", message: "AI assessment endpoint has not been implemented. Manual entry remains available." }; },
    async extract() { return { status: "unavailable", candidate: null, evidence: [], questions: [], warnings: [], model: null, elapsed_ms: null, message: "AI extraction endpoint has not been implemented. Your manual fields are unchanged." }; },
  };
}
