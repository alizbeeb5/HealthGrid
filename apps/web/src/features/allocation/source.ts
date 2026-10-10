import example from "./demo-display.json";
import { createIncidentApiClient } from "../scenarios/api-client";
import type { PlanningSource, PlanningForm, Proposal } from "./model";
export const exampleSource = () => structuredClone(example.source) as PlanningSource;
export const exampleForm = () => structuredClone(example.input) as PlanningForm;
export async function loadPlanningSource(runId: string): Promise<PlanningSource> {
  const run = await createIncidentApiClient().getRun(runId);
  return { simulation_run_id: run.run_id, incident_id: run.incident_id, revision_id: run.revision_id, baseline_id: run.baseline_id, baseline_at: run.baseline_at, planning_start_at: run.input.starts_at, service_id: run.input.service_id!, example: false,
    hospitals: run.rows.map((row) => {
      const monitor = row.scenario.resource_limits.find((item) => item.resource_id === "working-monitors");
      return { facility_id: row.facility_id, name: row.name, capacity: row.scenario.estimated_capacity, status: row.scenario.status, monitors: monitor?.available_quantity ?? null, evidence: [
        `Frozen profile: ${row.scenario.profile_version ?? "Not configured"}`,
        ...row.scenario.resource_limits.map((item) => `${item.resource_id}: ${item.available_quantity ?? "Unknown"} ${item.unit}; ${item.data_status}; observed ${item.observed_at ?? "not supplied"}`),
        ...row.scenario.reason_codes.map((reason) => reason.replaceAll("_", " ")),
        ...(row.applied_overrides ?? []).map((item) => item.override_type === "service_status" ? `Confirmed assumption: service ${item.scenario_status}` : `Confirmed assumption: ${item.resource_id} = ${item.scenario_quantity} ${item.unit}`),
      ] };
    }),
  };
}
/** A fixed preview lookup, not a solver or API fallback. Any edits invalidate it. */
export function showExample(form: PlanningForm): Proposal {
  if (JSON.stringify(form) !== JSON.stringify(example.input)) throw new Error("This display fixture matches only the loaded synthetic constraints. Edited inputs require the backend OR-Tools endpoint; no plan was produced.");
  return structuredClone(example) as Proposal;
}
const storageKey = "healthgrid:allocation-ui-example:v1";
export function previewStore(storage: Pick<Storage, "getItem" | "setItem">) {
  function read(): Proposal[] {
    const raw = storage.getItem(storageKey); if (!raw) return [];
    try {
      const data = JSON.parse(raw);
      if (!Array.isArray(data) || data.some((item: Proposal) => !item?.source?.example || !item.input || !Array.isArray(item.included) || !Array.isArray(item.transfers))) throw new Error();
      return data;
    } catch { throw new Error("Saved browser examples could not be read. They have not been replaced."); }
  }
  return {
    list: read,
    save(proposal: Proposal) { const saved = { ...structuredClone(proposal), id: crypto.randomUUID(), saved_at: new Date().toISOString() }; storage.setItem(storageKey, JSON.stringify([saved, ...read()])); return saved; },
    get(id: string) { const saved = read().find((item) => item.id === id); if (!saved) throw new Error("Saved browser proposal example not found."); return structuredClone(saved); },
  };
}
