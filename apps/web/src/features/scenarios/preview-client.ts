import example from "./outage-preview.json";
import { outageExample, outageReport, snapshots, validateIncident, type Assessment, type ComparisonRow, type Extraction, type IncidentFields, type PreviewRevision, type PreviewRun } from "./model";

const key = "healthgrid:incident-frontend-preview:v1";
type Store = { version: 1; revisions: PreviewRevision[]; runs: PreviewRun[] };
export function createPreviewClient(storage: Pick<Storage, "getItem" | "setItem">) {
  function read(): Store {
    const raw = storage.getItem(key);
    if (!raw) return { version: 1, revisions: [], runs: [] };
    try {
      const data = JSON.parse(raw) as Store;
      if (data.version !== 1 || !Array.isArray(data.revisions) || !Array.isArray(data.runs)) throw new Error();
      for (const revision of data.revisions) {
        if (!revision || typeof revision.revision_id !== "string" || typeof revision.incident_id !== "string" || !["draft", "confirmed"].includes(revision.status) || !Number.isFinite(Date.parse(revision.created_at)) || validateIncident(revision.input, revision.status === "confirmed").length) throw new Error();
        if (revision.status === "confirmed" && (!revision.baseline || !Array.isArray(revision.baseline.rows) || !Array.isArray(revision.baseline.facility_snapshots))) throw new Error();
      }
      for (const run of data.runs) {
        if (!run || typeof run.run_id !== "string" || !Array.isArray(run.rows) || validateIncident(run.input, true).length || !data.revisions.some((revision) => revision.revision_id === run.revision_id && revision.status === "confirmed")) throw new Error();
      }
      return data;
    } catch { throw new Error("Local preview data could not be read. It has not been overwritten. Use another browser profile to try the preview."); }
  }
  function write(data: Store) { storage.setItem(key, JSON.stringify(data)); }
  function check(input: IncidentFields, confirming: boolean) {
    const errors = validateIncident(input, confirming);
    if (errors.length) throw new Error(errors.join(" "));
  }
  return {
    async list() { const data = read(); return structuredClone(data); },
    async saveDraft(input: IncidentFields): Promise<PreviewRevision> {
      check(input, false);
      const data = read();
      const revision: PreviewRevision = { incident_id: crypto.randomUUID(), revision_id: crypto.randomUUID(), parent_revision_id: null, status: "draft", input: structuredClone({ ...input, affected_facility_ids: [...input.affected_facility_ids].sort() }), created_at: new Date().toISOString(), confirmed_at: null, confirmed_by: null, baseline: null };
      data.revisions.unshift(revision); write(data); return structuredClone(revision);
    },
    async getRevision(id: string, _incidentId?: string): Promise<PreviewRevision> {
      const revision = read().revisions.find((item) => item.revision_id === id);
      if (!revision) throw new Error("Local preview revision not found."); return structuredClone(revision);
    },
    async confirm(draftId: string, input: IncidentFields, reviewer: string): Promise<PreviewRevision> {
      check(input, true);
      if (!reviewer.trim()) throw new Error("Enter a demo reviewer display name.");
      const data = read(); const draft = data.revisions.find((item) => item.revision_id === draftId);
      if (!draft || draft.status !== "draft" || data.revisions.some((item) => item.parent_revision_id === draftId)) throw new Error("This draft is already confirmed or no longer available. Reopen the saved revision.");
      if (input.report_text !== draft.input.report_text) throw new Error("The original report changed. Save a new draft before confirmation.");
      const revision: PreviewRevision = { ...draft, revision_id: crypto.randomUUID(), parent_revision_id: draftId, status: "confirmed", input: structuredClone(input), created_at: new Date().toISOString(), confirmed_at: new Date().toISOString(), confirmed_by: reviewer.trim(), baseline: { baseline_id: crypto.randomUUID(), captured_at: example.captured_at, rows: (structuredClone(example.rows) as ComparisonRow[]).map(({ facility_id, name, baseline }) => ({ facility_id, name, baseline })), facility_snapshots: structuredClone(snapshots), requirement_profiles: structuredClone(example.requirement_profiles) } };
      data.revisions.unshift(revision); write(data); return structuredClone(revision);
    },
    async simulate(revisionId: string): Promise<PreviewRun> {
      const data = read(); const revision = data.revisions.find((item) => item.revision_id === revisionId);
      if (!revision?.baseline || revision.status !== "confirmed") throw new Error("Confirm the reviewed assumptions first.");
      const existing = data.runs.find((item) => item.revision_id === revisionId); if (existing) return structuredClone(existing);
      const input = revision.input; const override = input.service_overrides[0];
      if (input.service_id !== "emergency-care" || input.affected_facility_ids.length !== 1 || input.affected_facility_ids[0] !== "DEMO-B" || input.service_overrides.length !== 1 || override?.facility_id !== "DEMO-B" || override.status !== "unavailable" || input.resource_overrides.length) throw new Error("Only the fixed Hospital B emergency outage has a display comparison in this preview. Other assumptions require the backend simulation engine; no result was saved.");
      const fixedBaseline = (example.rows as ComparisonRow[]).map(({ facility_id, name, baseline }) => ({ facility_id, name, baseline }));
      if (JSON.stringify(revision.baseline.rows) !== JSON.stringify(fixedBaseline)) throw new Error("This saved baseline does not match the fixed preview fixture. The backend engine is required; no result was saved.");
      const run: PreviewRun = { run_id: crypto.randomUUID(), revision_id: revisionId, incident_id: revision.incident_id, created_at: new Date().toISOString(), engine_version: "frontend-display-fixture-only", baseline_id: revision.baseline.baseline_id, baseline_at: revision.baseline.captured_at, input: structuredClone(input), rows: structuredClone(example.rows) as ComparisonRow[] };
      data.runs.unshift(run); write(data); return structuredClone(run);
    },
    async getRun(id: string): Promise<PreviewRun> { const run = read().runs.find((item) => item.run_id === id); if (!run) throw new Error("Local preview run not found."); return structuredClone(run); },
    async assess(_report: string): Promise<Assessment> { return { status: "unavailable", answers: [], model: null, elapsed_ms: null, rubric_version: "emergency-review-v1", message: "AI assessment is not connected in this frontend preview. Manual entry remains available." }; },
    async extract(_report: string): Promise<Extraction> { return { status: "unavailable", candidate: null, evidence: [], questions: [], warnings: [], model: null, elapsed_ms: null, message: "AI extraction is not connected in this frontend preview. No fields were changed." }; },
  };
}
export type IncidentClient = ReturnType<typeof createPreviewClient>;
/** Explicit UI sample, never treated as a provider response. */
export function extractionSample(report: string): Extraction {
  if (report !== outageReport) throw new Error("The synthetic proposal matches only the sample outage report. Load that sample to inspect the review panel.");
  return { status: "completed", candidate: outageExample(), model: null, elapsed_ms: null, message: "Synthetic extraction display example; no OpenAI call was made.", evidence: [
    { field_path: "affected_facility_ids", source_excerpt: "Demo Hospital B" },
    { field_path: "service_id", source_excerpt: "emergency service" },
    { field_path: "service_overrides.0.status", source_excerpt: "unavailable after a power failure" },
    { field_path: "starts_at", source_excerpt: "10:00 UTC on October 10, 2026" },
    { field_path: "expected_ends_at", source_excerpt: "expected to last six hours" },
  ], questions: ["Verify the hospital, service, time and outage status before accepting these assumptions."], warnings: ["Title and restriction note are editorial suggestions. The recovery time is contextual; the simulation models one state only."] };
}
