# Investment numerical handoff to backend/data

The backend-owned `InvestmentEngineInput` and `InvestmentEngineResult` are now
implemented. The public `optimize_investments(input) -> result` binding maps frozen
facility inputs to the numerical kernel and returns the canonical Pydantic result.
The API independently checks and persists that result. No duplicate public schema
or endpoint has been introduced. Canonical catalog: `demo-investments-v1`.

Current internal entry points in `apps/api/app/engines/investments.py`:

- `_optimize_investments(data)` selects and independently verifies a package.
- `_validate_selected_package(data, selected_ids)` verifies a package independently
  of solver variables and recomputes capacities.

`_Problem` is a private structural protocol, not a wire model. The public binding maps the canonical frozen inputs to these internal attributes
and converts the result to the backend-owned result model. Tests use internal fixture records
in `apps/api/tests/investment_fixture_types.py`; production must not import them.

## Internal input attributes

| Attribute | Numerical meaning |
| --- | --- |
| service_id, capacity_unit, currency | One frozen service, simultaneous_service_place, USD |
| snapshots | Existing FacilitySnapshotResponse objects, after saved transfers exactly once |
| requirement_profiles | Existing frozen ServiceRequirement objects |
| required_service_places | Facility-ID → inherited integer demand; missing/null excludes |
| included_facility_ids | Source allocation's included facilities |
| excluded_facilities | Source exclusions with facility_id and reasons |
| candidates | Agreed candidate fields from the Feature 7 contract |
| planning_starts_at, evaluation_at | Aware UTC datetimes; evaluation at/after planning start |
| operating_cost_months | Positive integer full-month allowance |
| budget_minor_units | Nonnegative investment budget, excluding source transfer cost |
| solver_settings | time_limit_seconds (0 < limit ≤ 5), num_search_workers=1, random_seed=0 |

Confirming source eligibility, transfer reconstruction, matching the saved proposed
summary, and planning start ≥ incident start + source horizon belong to the backend.
The kernel cannot establish those facts without source metadata; do not pass live
hospital observations as replacement inputs.

## Internal result attributes

The kernel returns solver_status, plan_outcome, coverage, baseline_summary,
proposed_summary, selected_projects, capital/operating/total costs, remaining budget,
remaining_gap_reasons, validation_passed, review_required, engine/solver versions,
objective_description, objectives_proven and solve_duration_ms.

Coverage retains included facility IDs and facility/candidate exclusions. Internal
exclusion records use identifier/reasons: map identifiers to facility_id or
candidate_id according to the list. Summaries have included IDs, required/covered/
unmet totals and rows with facility/service status, demand, capacity, bottlenecks
and resulting resource quantities. Selected projects retain supplied effects,
ready_at and independently calculated costs, including prerequisite-only projects.

The internal engine version is investment-cpsat-v1. Solver version and duration are
runtime metadata; do not treat elapsed duration as a fixed fixture expectation.
`optimal` proves all three objectives; `feasible` may prove only a prefix. Unknown
or infeasible results have no proposed summary or selected package. `needs_inputs`
means no facility has usable inherited coverage; an empty catalog is a valid
no-improvement solve.

Malformed numerical inputs raise InvestmentValidationError with a field/context
message. Backend request schemas should catch invalid quantities, units, IDs and
dependency graphs at the field-level 422 boundary. Internal solver/model or result
inconsistencies raise InvestmentSolverError and must never be saved as valid plans.

Numeric counts are bounded at 1,000,000,000, catalog size at 200 projects, and exact
resource scaling is checked before CP-SAT. The backend checks these support limits at the field-level request boundary.

## Agreement with the pushed frontend

The numerical catalog now matches its project IDs (INV-B-BUY-5-MONITORS, INV-B-BUY-1-MONITOR, INV-B-REPAIR-5-IDLE,
INV-B-COMMISSION-5-REPAIRED), costs, dependencies and evidence. A numerical test verifies that the
display's selected IDs, ready dates, $2,400 cost and 6 → 11 covered demand agree
with the actual solver. Frontend integration, generated types, rendering/transport tests and production
build checks are complete. The starter and browser catalogs use the published
demo-investments-v1 version.
