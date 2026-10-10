# Feature 6 — Feasible resource allocation

Status: backend implemented — `modules/allocation` schemas/router/service/models,
migration `0005_allocation_runs`, both endpoints, OpenAPI and examples in
`contracts/examples/feature-6/`. `POST /allocation/runs` returns HTTP 500 until the
OR-Tools engine `optimize_allocation` is merged; the frontend is pending.

Backend interface decisions for the engine owner to review (`allocation/schemas.py`):
- `AllocationEngineInput`: `service_id`, `resource_id`, `unit`, `capacity_unit`,
  frozen `requirement`, `facilities` (every baseline facility: effective scenario
  `snapshot`, `applied_overrides`, and the planner `constraint` or null), `routes`,
  horizon, budget, currency and `solver_settings` (5 s total). Built by
  `scenarios.service.get_effective_scenario`, never from live observations.
- `AllocationEngineResult` is the response minus run metadata. Rows add
  `service_status` and `resource_quantity` (the moved resource after transfers).
  `ExclusionReason`: `no_planning_constraints`, `service_unavailable`,
  `service_limited`, `requirements_not_configured`, `missing_required_evidence`,
  `stale_required_evidence`. `needs_inputs` means no facility is included.
- `minimum_retained_resource_quantity` is a hard floor for every included facility's
  final quantity, so a retained quantity above current inventory is `infeasible`
  (the no-solution example). The donor service floor applies only to senders.
- The backend re-checks every hard constraint and recomputes capacities with the
  capacity engine before saving; a failing proposal is a 500 and is never saved.
- Examples were produced through the live API with a contract-faithful reference
  solver; tests compare everything except generated IDs, `created_at` and
  `solve_duration_ms` (wall clock; the examples show 0).
- Errors use the shared envelope with codes `invalid_request`,
  `simulation_run_not_found` and `allocation_run_not_found`.

## Outcome and first scope

Given a saved Feature 5 simulation, propose equipment transfers that reduce
unmet modeled service demand while preserving donor reserves and respecting
route, receiving, time and budget limits. Compare doing nothing with one computed
proposal and retain the remaining gap. This answers “What should we do with the
resources we already have?” Funding packages follow in Feature 7.

The first complete demonstration uses `emergency-care` and whole
`working-monitors` (`item`). Beds and nurses still constrain capacity but are
not moved in this milestone. Patient referrals, staffing shifts, oxygen transfers,
repairs and multiple competing services require additional rules and come later.
Modeled simultaneous service places are not admissions, occupied beds, patient
eligibility, or a guarantee of safe clinical care.

## User workflow

1. Open a saved incident simulation and choose “Plan resource transfers.”
2. Enter target demand, protected donor capacity, explicitly movable inventory,
   approved routes, receiving limits, budget and response horizon.
3. Review inputs and their provenance; unknown required inputs remain unknown.
4. Compute a proposal within a bounded solver time.
5. Compare capacity, covered demand, remaining gaps and cost before/after.
6. Save/reopen the proposal for human review. This feature does not dispatch
   resources or mark a proposal as operationally approved.

## Shared agreement before splitting

Use snake_case everywhere, existing facility/resource/service IDs, UTC timestamps,
integer item counts, and `simultaneous_service_place` for capacity and demand.
Backend owns Pydantic wire schemas; the engine owner reviews numerical fields;
frontend uses matching JSON examples and generated API types. No duplicate
frontend capacity calculation or separate interpretation of the same inputs.

Implement these endpoints in the existing allocation module:

```text
POST /api/v1/allocation/runs
GET  /api/v1/allocation/runs/{allocation_run_id}
```

Canonical request `AllocationRunRequest`:

| Field | Meaning |
| --- | --- |
| `simulation_run_id` | Existing saved Feature 5 `run_id`; confirmed revision required |
| `resource_id` | `working-monitors` for this milestone |
| `planning_horizon_minutes` | Positive response deadline from the incident planning start |
| `budget_minor_units` | Nonnegative integer budget in USD cents |
| `currency` | Literal `USD` for the demonstration |
| `facility_constraints` | One entry per included facility, described below |
| `routes` | Explicitly approved directed routes, described below |
| `assumptions` | Visible human-entered planning assumptions |

Each facility constraint has `facility_id`, `required_service_places`,
`minimum_retained_service_places`, `minimum_retained_resource_quantity`,
`transferable_quantity`, and `maximum_inbound_quantity`, all nonnegative integers.
Also record `source_note` and `confirmed_at`. Transferable quantity means explicitly
approved movable, compatible inventory, not all reported equipment. The donor
capacity floor is the larger of demand and minimum retained service places;
facilities already below this floor cannot donate. Receiving limits are additional
compatible equipment that can be accepted, not spare patient admission capacity.
The first version uses manually confirmed demand assumptions. Daily forecast
volumes must not be copied into simultaneous demand without an explicit conversion.

Each route has `route_id`, `from_facility_id`, `to_facility_id`,
`lead_time_minutes`, `cost_per_unit_minor_units`, `maximum_quantity`,
`source_note`, and `confirmed_at`. No self-routes, duplicates or unknown IDs.
Costs are linear per item for this milestone. Route eligibility is explicit;
coordinates do not establish travel time or transfer authorization.

Canonical response `AllocationRun` contains:

- `allocation_run_id`, `simulation_run_id`, `incident_id`, `revision_id`,
  `baseline_id`, `created_at`, `engine_version`, `solver_version`,
  `schema_version`, immutable `input`, and solver settings.
- `solver_status`: `not_run`, `optimal`, `feasible`, `infeasible`, or `unknown`.
- `plan_outcome`: `needs_inputs`, `improved`, `no_improvement`, or `no_solution`.
- `coverage`: included and excluded facility IDs with exclusion reasons.
- `baseline_summary` and nullable `proposed_summary`, with covered demand,
  unmet demand, and facility rows. Summary totals explicitly cover only included
  facilities; excluded demand is not counted as zero.
- Facility rows: `facility_id`, `required_service_places`, `estimated_capacity`,
  `covered_service_places`, `unmet_service_places`, and bottleneck IDs.
- `transfers`: route/source/destination/resource IDs, `quantity`, `unit`,
  lead time and cost; `total_cost_minor_units`; `remaining_gap_reasons`.
- `validation_passed`, `review_required`, objective description and solve duration.

Malformed inputs return field-level 422 errors; missing simulation returns 404.
Missing planning inputs or unusable resource evidence yields `needs_inputs` or
explicit exclusions, not invented values. A usable subset can be solved only with
its incomplete coverage exposed. Solver/model failures return a clear server error.
Never publish a proposed plan when independent constraint validation fails.

Before implementation, commit request/response examples under
`contracts/examples/feature-6/`: improved, no improvement, needs inputs and no
solution. Regenerate OpenAPI and TypeScript types when real schemas are committed.

## Numerical and persistence rules

- Reconstruct effective scenario quantities from the saved baseline, confirmed
  overrides and frozen requirement profiles through the scenarios service/public
  contract. Do not query live observations or another module's repository.
- Only known, usable evidence can establish donor availability. Exclude stale or
  unknown required resource evidence unless the saved scenario explicitly replaces
  it with a visible confirmed assumption. Unavailable/limited services cannot be
  treated as operating merely because equipment arrives.
- Integer transfers conserve inventory. Outbound totals cannot exceed original
  approved transferable quantities; incoming inventory cannot be re-exported.
  Final quantities must honor retained resource and donor service capacity floors.
- Enforce receiving caps, directed route quantity caps, route lead time within the
  horizon and total cost within budget. The demo assumes parallel direct transfers;
  transport vehicles and shared transport scheduling are not modeled.
- Compute service capacity using all existing profile requirements. Scale rational
  coefficients to integers for CP-SAT. Recompute final capacity with the existing
  capacity engine and independently validate every hard constraint.
- Primary objective: minimize unmet demand across included facilities. Among proven
  primary optima, minimize transfer cost, then number of moved items. Use sequential
  solves under one total time budget; freeze an objective only after it is proven
  optimal. A feasible timeout incumbent is valid but must not be called optimal.
- Default total solver time limit: 5 seconds, set server-side. `unknown` means no
  solution/proof found within limits; it does not mean proven infeasible.
- Demand is a soft target. No transfer is an allowed plan. Remaining unmet demand
  can coexist with an optimal result; no beneficial move means `no_improvement`,
  not `infeasible`. Unknown results without an incumbent have no proposed summary.
- Persist complete inputs, evidence references, results and versions. Reopening
  returns the saved result, not a new solve. Observations, incidents and saved
  baselines are never edited by allocation. No OpenAI call is required here.

CP-SAT status and integer modeling reference:
https://developers.google.com/optimization/cp/cp_solver

## Three focused teammate tasks

### 1. Frontend — Inputs and before/after comparison

Work in `apps/web`, extending the saved incident simulation journey. Build the
constraint form against agreed example JSON, then connect the two endpoints.
Show donor protection, route assumptions, do-nothing versus proposed outcomes,
transfers, cost, remaining gap, coverage and solver status. Include incomplete
inputs, no improvement, timeout and request-error states. Reopen saved proposals.

Done: a user can enter the shared demo, compute, understand the partial improvement
and reopen it. Web testing is performed by the user; do not run browser checks or
frontend builds/tests unless requested.

### 2. Backend/data — Contracts, frozen input and saved runs

Own `modules/allocation/{schemas,router,service,repository,models}.py`, one
coordinated migration, OpenAPI export and examples. Add a public scenarios service
method if necessary to supply the frozen allocation input. Validate IDs, units,
routes, bounds and confirmed source simulation. Persist requests and results.

Agree with the engine owner on the exact typed interface:
`optimize_allocation(input: AllocationEngineInput) -> AllocationEngineResult`.
The input contains effective scenario snapshots, frozen profiles and validated
planning constraints. Numerical types must be shared, not separately redefined.

Done: saved simulation -> allocation input -> engine -> saved result -> GET works;
changing hospital observations cannot change an existing allocation run. Verify
API validation, persistence, immutable inputs and engine integration.

### 3. Optimization/data — OR-Tools engine and constraint evidence

Own `engines/allocation.py`, allocation numerical tests and
`data/synthetic/feature-6/`. Implement the agreed pure typed function with CP-SAT,
do-nothing comparison, bounded solving and independent plan validation. No database,
HTTP, OpenAI or live observation calls in this engine.

Done: tests cover inventory conservation, combined donor withdrawals, protected
capacity, blocked recipients, receiving/route caps, budget, deadline, stale/unknown
evidence, no improvement and solver status handling. Match example outputs exactly
and confirm final capacities through the existing capacity engine.

## Shared demonstration and integration order

Use a separate confirmed resource-loss scenario: DEMO-A operates with 4 monitors,
12 beds and 6 nurses; DEMO-B operates with 2 monitors, 18 beds and 9 nurses.
These are explicit synthetic scenario assumptions. DEMO-C remains excluded because
its service is unavailable. Required places: A=3, B=8. A can move one monitor,
retains at least 3 monitors and 3 service places; B accepts one. Approved A->B
route: 30 minutes, 10000 USD cents per item; budget 10000; horizon 60 minutes.

Expected: one monitor moves A->B. Modeled capacities change A 4->3 and B 2->3.
Covered demand increases 5->6; unmet demand decreases 6->5. Donor demand stays
covered and the result explicitly shows the unresolved gap. Re-run the original
service-closure scenario to demonstrate that equipment cannot reopen a closed
service. Neither demonstration claims clinically validated capacity.

Build order: (1) shared schemas/examples and typed engine interface; (2) engine,
API persistence and UI against examples in parallel; (3) connect the single demo;
(4) backend/numerical checks and user web review. Funding and operational action
approval are later milestones.
