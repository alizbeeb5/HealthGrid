/** Frontend editor/presentation models. Not a proposed allocation wire contract. */
export const constraintFields = [
  ["required_service_places", "Required simultaneous service places"],
  ["minimum_retained_service_places", "Minimum retained service places"],
  ["minimum_retained_resource_quantity", "Minimum retained monitors (items)"],
  ["transferable_quantity", "Explicitly approved movable monitors (items)"],
  ["maximum_inbound_quantity", "Maximum additional inbound monitors (items)"],
] as const;
export type ConstraintKey = typeof constraintFields[number][0];
export type FacilityConstraint = Record<ConstraintKey, string> & { facility_id: string; source_note: string; confirmed_at: string };
export type Route = { route_id: string; from_facility_id: string; to_facility_id: string; lead_time_minutes: string; cost_per_unit_minor_units: string; maximum_quantity: string; source_note: string; confirmed_at: string };
export type PlanningForm = { simulation_run_id: string; resource_id: "working-monitors"; planning_horizon_minutes: string; budget_minor_units: string; currency: "USD"; facility_constraints: FacilityConstraint[]; routes: Route[]; assumptions: string[] };
export type SourceHospital = { facility_id: string; name: string; capacity: number | null; status: string; monitors: number | null; evidence: string[] };
export type PlanningSource = { simulation_run_id: string; incident_id: string; revision_id: string; baseline_id: string; baseline_at: string; planning_start_at: string | null; service_id: string; example: boolean; hospitals: SourceHospital[] };
export type Summary = { covered: number; unmet: number; rows: { facility_id: string; demand: number; capacity: number | null; covered: number | null; unmet: number | null; bottlenecks: string[] }[] };
export type Proposal = {
  id: string; saved_at: string | null; source: PlanningSource; input: PlanningForm;
  solver_status: "not_run" | "optimal" | "feasible" | "infeasible" | "unknown";
  plan_outcome: "needs_inputs" | "improved" | "no_improvement" | "no_solution";
  included: string[]; excluded: { facility_id: string; reason: string }[];
  baseline: Summary; proposed: Summary | null;
  transfers: { route_id: string; from: string; to: string; quantity: number; unit: "item"; lead_time_minutes: number; cost_minor_units: number }[];
  total_cost_minor_units: number | null; remaining_gap_reasons: string[];
  validation_passed: boolean; review_required: boolean; objective: string; solve_duration_ms: number | null;
  engine_version?: string; solver_version?: string;
  solver_settings?: { time_limit_seconds: number; objective_order: string[] };
};
export function blankConstraint(facility_id: string): FacilityConstraint {
  return { facility_id, required_service_places: "", minimum_retained_service_places: "", minimum_retained_resource_quantity: "", transferable_quantity: "", maximum_inbound_quantity: "", source_note: "", confirmed_at: "" };
}
export function blankForm(source: PlanningSource): PlanningForm {
  return { simulation_run_id: source.simulation_run_id, resource_id: "working-monitors", planning_horizon_minutes: "", budget_minor_units: "", currency: "USD", facility_constraints: source.hospitals.map((item) => blankConstraint(item.facility_id)), routes: [], assumptions: [] };
}
/** Form feedback only. Eligibility, donor protection and solving belong in Python. */
export function validatePlanning(form: PlanningForm, source: PlanningSource): string[] {
  const errors: string[] = [];
  function integer(value: string, label: string, positive = false) {
    if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) < (positive ? 1 : 0)) errors.push(`${label}: enter a ${positive ? "positive" : "nonnegative"} whole number; unknown is not zero.`);
  }
  function provenance(note: string, at: string, label: string) {
    if (!note.trim()) errors.push(`${label}: explain the source and approval assumptions.`);
    if (!at || !at.endsWith("Z") || !Number.isFinite(Date.parse(at))) errors.push(`${label}: enter a UTC confirmation timestamp.`);
  }
  if (form.simulation_run_id !== source.simulation_run_id) errors.push("The selected simulation does not match these constraints.");
  integer(form.planning_horizon_minutes, "Response horizon (minutes)", true); integer(form.budget_minor_units, "Budget (USD cents)");
  const included = new Set<string>();
  for (const facility of form.facility_constraints) {
    if (!source.hospitals.some((item) => item.facility_id === facility.facility_id) || included.has(facility.facility_id)) errors.push("Included hospitals must be unique and belong to the saved simulation.");
    included.add(facility.facility_id);
    for (const [key, label] of constraintFields) integer(facility[key], `${facility.facility_id} — ${label}`);
    provenance(facility.source_note, facility.confirmed_at, facility.facility_id);
  }
  if (!included.size) errors.push("Include at least one hospital with explicit planning constraints.");
  const routeIds = new Set<string>(); const directions = new Set<string>();
  for (const route of form.routes) {
    const pair = `${route.from_facility_id}:${route.to_facility_id}`;
    if (!route.route_id.trim() || routeIds.has(route.route_id) || directions.has(pair)) errors.push("Routes require unique IDs and directed hospital pairs.");
    routeIds.add(route.route_id); directions.add(pair);
    if (route.from_facility_id === route.to_facility_id || !included.has(route.from_facility_id) || !included.has(route.to_facility_id)) errors.push("Routes must connect two different included hospitals.");
    integer(route.lead_time_minutes, `${route.route_id} — lead time`); integer(route.cost_per_unit_minor_units, `${route.route_id} — cost per item (USD cents)`); integer(route.maximum_quantity, `${route.route_id} — route quantity limit`, true);
    provenance(route.source_note, route.confirmed_at, route.route_id);
  }
  if (form.assumptions.some((item) => !item.trim())) errors.push("Enter or remove empty assumptions.");
  return [...new Set(errors)];
}
export function money(cents: number) { return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(cents / 100); }
