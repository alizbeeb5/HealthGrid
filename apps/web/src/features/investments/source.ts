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

type WireRequest = components["schemas"]["InvestmentRunRequest"];
type WireRun = components["schemas"]["InvestmentRun"];
export function formFromRequest(input: WireRequest): InvestmentForm {
  return { ...input, operating_cost_months: String(input.operating_cost_months), budget_minor_units: String(input.budget_minor_units), candidates: input.candidates.map((c) => ({ ...c, capital_cost_minor_units: String(c.capital_cost_minor_units), monthly_operating_cost_minor_units: String(c.monthly_operating_cost_minor_units), implementation_days: String(c.implementation_days), source_note: c.source_note ?? "", confirmed_at: c.confirmed_at ?? "", resource_effects: c.resource_effects.map((e) => ({ ...e, quantity_delta: String(e.quantity_delta) })) })) };
}
export function requestFromForm(form: InvestmentForm): WireRequest {
  return { ...form, operating_cost_months: Number(form.operating_cost_months), budget_minor_units: Number(form.budget_minor_units), candidates: form.candidates.map((c) => ({ ...c, capital_cost_minor_units: Number(c.capital_cost_minor_units), monthly_operating_cost_minor_units: Number(c.monthly_operating_cost_minor_units), implementation_days: Number(c.implementation_days), source_note: c.source_note.trim() || null, confirmed_at: c.confirmed_at || null, requires_candidate_ids: [...c.requires_candidate_ids].sort(), resource_effects: c.resource_effects.map((e) => ({ ...e, quantity_delta: Number(e.quantity_delta), unit: e.unit as components["schemas"]["ResourceUnit"] })) })) };
}
export async function loadCatalogForm(id: string): Promise<InvestmentForm> {
  const catalog = await facilityRequest<components["schemas"]["InvestmentCatalog"]>("/api/v1/investments/catalog");
  return formFromRequest({ allocation_run_id: id, planning_starts_at: "", evaluation_at: "", operating_cost_months: 3, budget_minor_units: 300000, currency: catalog.currency, catalog_version: catalog.catalog_version, candidates: catalog.candidates, assumptions: ["Source transfers are assumed completed by planning_starts_at; they are not executed.", "Inherited demand persists to evaluation_at; it is not a forecast."] });
}
export function previewFromRun(run: WireRun): PackagePreview {
  return { ...run, id: run.investment_run_id, saved_at: run.created_at, input: formFromRequest(run.input), source: { allocation_run_id: run.allocation_run_id, simulation_run_id: run.simulation_run_id, incident_id: run.incident_id, revision_id: run.revision_id, baseline_id: run.baseline_id, saved_at: run.created_at, example: false, summary: run.baseline_summary, excluded: run.coverage.excluded_facilities, transfers: run.assumed_transfers.map((t) => JSON.stringify(t)), transfer_cost_minor_units: run.assumed_transfers.reduce((sum, t) => sum + t.cost_minor_units, 0), solver_status: run.solver_status, remaining_gap_reasons: run.remaining_gap_reasons }, proposed: run.proposed_summary, candidate_exclusions: run.coverage.excluded_candidates };
}
export async function createInvestment(form: InvestmentForm): Promise<PackagePreview> {
  return previewFromRun(await facilityRequest<WireRun>("/api/v1/investments/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(requestFromForm(form)) }));
}
export async function loadInvestment(id: string): Promise<PackagePreview> {
  const run = await facilityRequest<WireRun>(`/api/v1/investments/runs/${encodeURIComponent(id)}`);
  if (run.investment_run_id !== id) throw new Error("The saved investment does not match the requested ID.");
  return previewFromRun(run);
}
