import example from "./demo-display.json";
import { facilityRequest } from "../../lib/api/facilities";
import type { components } from "../../lib/api/schema";
import { type InvestmentForm, type InvestmentSource, type PackagePreview } from "./model";
export const exampleSource = () => structuredClone(example.source) as InvestmentSource;
export const exampleForm = () => structuredClone(example.input) as InvestmentForm;
export async function loadSource(id: string): Promise<InvestmentSource> {
  const run = await facilityRequest<components["schemas"]["AllocationRun"]>(`/api/v1/allocation/runs/${encodeURIComponent(id)}`);
  if (run.allocation_run_id !== id) throw new Error("The saved allocation does not match the requested ID.");
  if (!run.validation_passed || !run.proposed_summary || !["optimal", "feasible"].includes(run.solver_status)) throw new Error("Investment planning requires a validated saved allocation with a proposed summary. Open another allocation proposal.");
  return { allocation_run_id: run.allocation_run_id, simulation_run_id: run.simulation_run_id, incident_id: run.incident_id, revision_id: run.revision_id, baseline_id: run.baseline_id, saved_at: run.created_at, example: false, summary: run.proposed_summary, excluded: run.coverage.excluded, transfers: run.transfers.map((transfer) => JSON.stringify(transfer)), transfer_cost_minor_units: run.total_cost_minor_units, solver_status: run.solver_status, remaining_gap_reasons: run.remaining_gap_reasons };
}
export function showExample(form: InvestmentForm): PackagePreview {
  if (JSON.stringify(form) !== JSON.stringify(example.input)) throw new Error("The display result matches only the unchanged synthetic catalog, budget and dates. Edited inputs require the backend package solver; no funding result was produced.");
  return structuredClone(example) as PackagePreview;
}
export function exampleStore(storage: Pick<Storage, "getItem" | "setItem">) {
  const key = "healthgrid:investment-ui-example:v1";
  function list(): PackagePreview[] {
    const raw = storage.getItem(key); if (!raw) return [];
    try { const data = JSON.parse(raw); if (!Array.isArray(data) || data.some((item) => !item?.source?.example || !item.input || !Array.isArray(item.input.candidates) || !Array.isArray(item.selected_projects) || !item.source.summary || !Array.isArray(item.source.summary.rows))) throw new Error(); return data; }
    catch { throw new Error("Stored funding examples could not be read. Existing data has not been overwritten."); }
  }
  return { list, get(id: string) { const proposal = list().find((item) => item.id === id); if (!proposal) throw new Error("Saved browser funding example not found."); return structuredClone(proposal); }, save(proposal: PackagePreview) { const result = { ...structuredClone(proposal), id: crypto.randomUUID(), saved_at: new Date().toISOString() }; storage.setItem(key, JSON.stringify([result, ...list()])); return result; } };
}
