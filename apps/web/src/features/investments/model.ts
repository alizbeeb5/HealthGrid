import type { components } from "../../lib/api/schema";
export type Summary = Pick<components["schemas"]["InvestmentSummary"], "included_facility_ids" | "required_service_places" | "covered_service_places" | "unmet_service_places" | "rows"> | components["schemas"]["PlanSummary"];
/** Editor/display models only; wire requests use generated backend-owned investment schemas. */
export type Candidate = { candidate_id: string; name: string; facility_id: string; service_id: string; capital_cost_minor_units: string; monthly_operating_cost_minor_units: string; implementation_days: string; resource_effects: { resource_id: string; quantity_delta: string; unit: string }[]; requires_candidate_ids: string[]; exclusive_group_id: string | null; source_note: string; confirmed_at: string };
export type InvestmentForm = { allocation_run_id: string; planning_starts_at: string; evaluation_at: string; operating_cost_months: string; budget_minor_units: string; currency: "USD"; catalog_version: string; candidates: Candidate[]; assumptions: string[] };
export type InvestmentSource = { allocation_run_id: string; simulation_run_id: string; incident_id: string; revision_id: string; baseline_id: string; saved_at: string; example: boolean; summary: Summary; excluded: { facility_id: string; reasons: string[] }[]; transfers: string[]; transfer_cost_minor_units: number; solver_status: string; remaining_gap_reasons: string[] };
export type PackagePreview = { engine_version?: string; solver_version?: string; objective_description?: string; solve_duration_ms?: number; id: string; saved_at: string | null; source: InvestmentSource; input: InvestmentForm; solver_status: "not_run" | "optimal" | "feasible" | "infeasible" | "unknown"; plan_outcome: "needs_inputs" | "improved" | "no_improvement" | "no_solution"; proposed: Summary | null; selected_projects: { candidate_id: string; ready_at: string; capital_cost_minor_units: number; operating_cost_minor_units: number; total_cost_minor_units: number; resource_effects: { resource_id: string; quantity_delta: number; unit: string }[] }[]; candidate_exclusions: { candidate_id: string; reasons: string[] }[]; total_capital_cost_minor_units: number | null; total_operating_cost_minor_units: number | null; total_cost_minor_units: number | null; remaining_budget_minor_units: number | null; validation_passed: boolean; remaining_gap_reasons: string[] };
export const effectOptions = [{ resource_id: "working-monitors", name: "Working monitors", unit: "item" }, { resource_id: "available-beds", name: "Physical beds", unit: "bed" }, { resource_id: "nurses-on-duty", name: "Nurses on duty", unit: "person" }];
export function blankCandidate(facility_id: string): Candidate { return { candidate_id: `project-${crypto.randomUUID().slice(0, 8)}`, name: "", facility_id, service_id: "emergency-care", capital_cost_minor_units: "", monthly_operating_cost_minor_units: "", implementation_days: "", resource_effects: [], requires_candidate_ids: [], exclusive_group_id: null, source_note: "", confirmed_at: "" }; }
export function blankForm(allocation_run_id: string): InvestmentForm { return { allocation_run_id, planning_starts_at: "", evaluation_at: "", operating_cost_months: "", budget_minor_units: "", currency: "USD", catalog_version: "user-edited-preview", candidates: [], assumptions: [] }; }
/** Input feedback only. No project cost, readiness, capacity or optimization maths. */
export function validateInvestment(input: InvestmentForm, source: InvestmentSource): string[] {
  const errors: string[] = [];
  function integer(value: string, label: string, positive = false) { if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) < (positive ? 1 : 0)) errors.push(`${label}: enter a ${positive ? "positive" : "nonnegative"} whole number. Unknown is not zero.`); }
  function date(value: string, label: string, required: boolean) { if ((required || value) && (!value.endsWith("Z") || !Number.isFinite(Date.parse(value)))) errors.push(`${label}: enter a valid UTC timestamp.`); }
  if (input.allocation_run_id !== source.allocation_run_id) errors.push("Inputs must match the selected saved allocation.");
  integer(input.budget_minor_units, "Budget (USD cents)"); integer(input.operating_cost_months, "Operating allowance (months)", true);
  date(input.planning_starts_at, "Assumed transfer completion", true); date(input.evaluation_at, "Evaluation date", true);
  if (Date.parse(input.evaluation_at) < Date.parse(input.planning_starts_at)) errors.push("Evaluation cannot precede planning start.");
  if (!input.catalog_version.trim()) errors.push("Supply a reviewed catalog/version label.");
  const ids = new Set(input.candidates.map((candidate) => candidate.candidate_id));
  if (ids.size !== input.candidates.length) errors.push("Project IDs must be unique.");
  for (const candidate of input.candidates) {
    if (!candidate.candidate_id.trim() || !candidate.name.trim()) errors.push("Every project needs an ID and name.");
    if (!source.summary.included_facility_ids.includes(candidate.facility_id) || candidate.service_id !== "emergency-care") errors.push(`${candidate.candidate_id}: choose an included hospital and emergency-care service.`);
    integer(candidate.capital_cost_minor_units, `${candidate.candidate_id} — capital cost`); integer(candidate.monthly_operating_cost_minor_units, `${candidate.candidate_id} — monthly operation`); integer(candidate.implementation_days, `${candidate.candidate_id} — implementation days`);
    date(candidate.confirmed_at, `${candidate.candidate_id} — confirmation`, false);
    const resources = new Set<string>();
    for (const effect of candidate.resource_effects) {
      const option = effectOptions.find((item) => item.resource_id === effect.resource_id);
      if (!option || option.unit !== effect.unit || resources.has(effect.resource_id)) errors.push(`${candidate.candidate_id}: effects require unique resources with matching catalog units.`);
      resources.add(effect.resource_id); integer(effect.quantity_delta, `${candidate.candidate_id} — resource addition`);
    }
    if (new Set(candidate.requires_candidate_ids).size !== candidate.requires_candidate_ids.length || candidate.requires_candidate_ids.some((id) => !ids.has(id) || id === candidate.candidate_id)) errors.push(`${candidate.candidate_id}: prerequisites must be unique other project IDs in this catalog.`);
  }
  const visited = new Set<string>(); const stack = new Set<string>();
  function visit(id: string): boolean { if (stack.has(id)) return true; if (visited.has(id)) return false; stack.add(id); const candidate = input.candidates.find((item) => item.candidate_id === id); if (candidate?.requires_candidate_ids.some(visit)) return true; stack.delete(id); visited.add(id); return false; }
  if (input.candidates.some((candidate) => visit(candidate.candidate_id))) errors.push("Project dependencies contain a cycle.");
  if (input.assumptions.some((item) => !item.trim())) errors.push("Enter or remove empty assumptions.");
  return [...new Set(errors)];
}
