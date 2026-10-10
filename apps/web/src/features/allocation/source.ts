import example from "./demo-display.json";
import { createIncidentApiClient } from "../scenarios/api-client";
import type { PlanningSource, PlanningForm, Proposal } from "./model";
import type { components } from "../../lib/api/schema";
type AllocationRun = components["schemas"]["AllocationRun"];
type AllocationRequest = components["schemas"]["AllocationRunRequest"];

export function allocationPayload(form: PlanningForm): AllocationRequest {
  return { ...form, planning_horizon_minutes: Number(form.planning_horizon_minutes),
    budget_minor_units: Number(form.budget_minor_units),
    facility_constraints: form.facility_constraints.map((row) => ({ ...row,
      required_service_places: Number(row.required_service_places),
      minimum_retained_service_places: Number(row.minimum_retained_service_places),
      minimum_retained_resource_quantity: Number(row.minimum_retained_resource_quantity),
      transferable_quantity: Number(row.transferable_quantity), maximum_inbound_quantity: Number(row.maximum_inbound_quantity) })),
    routes: form.routes.map((row) => ({ ...row, lead_time_minutes: Number(row.lead_time_minutes),
      cost_per_unit_minor_units: Number(row.cost_per_unit_minor_units), maximum_quantity: Number(row.maximum_quantity) })) };
}
async function allocationRequest(path: string, payload?: AllocationRequest): Promise<AllocationRun> {
  let response: Response;
  try { response = await fetch(`/api/v1/allocation/runs${path}`, { cache: "no-store", ...(payload ? {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  } : {}) }); }
  catch { throw new Error(payload ? "The save could not be confirmed. Check saved proposal links before retrying; this request is not automatically retried." : "Could not connect to the allocation API."); }
  let body;
  try { body = await response.json(); }
  catch { throw new Error(payload ? "The calculation/save response could not be read. The server may have saved the result; do not automatically retry." : "The saved allocation response could not be read."); }
  if (!response.ok) throw new Error([body?.error?.message ?? "The allocation API could not complete the request.",
    ...(body?.error?.fields ?? []).map((field: { field: string; message: string }) => `${field.field}: ${field.message}`)].join("\n"));
  return body as AllocationRun;
}
export function planningFormFromRequest(input: AllocationRequest): PlanningForm {
  return {
    ...input, planning_horizon_minutes: String(input.planning_horizon_minutes), budget_minor_units: String(input.budget_minor_units),
    facility_constraints: input.facility_constraints.map((row) => ({ ...row, required_service_places: String(row.required_service_places),
      minimum_retained_service_places: String(row.minimum_retained_service_places), minimum_retained_resource_quantity: String(row.minimum_retained_resource_quantity),
      transferable_quantity: String(row.transferable_quantity), maximum_inbound_quantity: String(row.maximum_inbound_quantity) })),
    routes: input.routes.map((row) => ({ ...row, lead_time_minutes: String(row.lead_time_minutes), cost_per_unit_minor_units: String(row.cost_per_unit_minor_units), maximum_quantity: String(row.maximum_quantity) })),

  };
}
export function presentAllocation(run: AllocationRun, source: PlanningSource): Proposal {
  const summary = (value: AllocationRun["baseline_summary"]) => ({ covered: value.covered_service_places,
    unmet: value.unmet_service_places, rows: value.rows.map((row) => ({ facility_id: row.facility_id,
      demand: row.required_service_places, capacity: row.estimated_capacity, covered: row.covered_service_places,
      unmet: row.unmet_service_places, bottlenecks: row.bottleneck_resource_ids })) });
  return { id: run.allocation_run_id, saved_at: run.created_at, source, input: planningFormFromRequest(run.input), solver_status: run.solver_status, plan_outcome: run.plan_outcome, included: run.coverage.included_facility_ids,
    excluded: run.coverage.excluded.map((row) => ({ facility_id: row.facility_id, reason: row.reasons.join(", ") })),
    baseline: summary(run.baseline_summary), proposed: run.proposed_summary ? summary(run.proposed_summary) : null,
    transfers: run.transfers.map((row) => ({ route_id: row.route_id, from: row.from_facility_id, to: row.to_facility_id,
      quantity: row.quantity, unit: "item", lead_time_minutes: row.lead_time_minutes, cost_minor_units: row.cost_minor_units })),
    total_cost_minor_units: run.total_cost_minor_units, remaining_gap_reasons: run.remaining_gap_reasons,
    validation_passed: run.validation_passed, review_required: run.review_required,
    objective: run.objective_description, solve_duration_ms: run.solve_duration_ms,
    engine_version: run.engine_version, solver_version: run.solver_version, solver_settings: run.solver_settings };
}
export async function calculateAllocation(form: PlanningForm, source: PlanningSource): Promise<Proposal> {
  return presentAllocation(await allocationRequest("", allocationPayload(form)), source);
}
export async function reopenAllocation(id: string): Promise<Proposal> {
  const run = await allocationRequest(`/${encodeURIComponent(id)}`);
  return presentAllocation(run, await loadPlanningSource(run.simulation_run_id));
}
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
