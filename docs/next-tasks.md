# Full-product workstreams (reference)

**Active milestone:** build Feature 1 only, using `feature-1-contract.md`. Its
three small assignments supersede the broad workstreams below for the current step.

Read product-scope.md first. Keep the agreed stack and modular monolith. Work on
separate branches and local databases. Integrate one complete scenario early.

## Shared kickoff before splitting

Agree on the demonstrated service, facility IDs, resource units, illustrative
capacity rules, incident fields, solver objective and candidate actions. Record
these in contracts/examples and data/synthetic before implementing behavior.

Use these shared concepts: FacilitySnapshot, ServiceRequirement, ForecastResult,
IncidentInput, ScenarioSnapshot, ResponsePlan, InvestmentCandidate, InvestmentPlan,
DecisionRecord. They are proposed contract names, not existing implemented schemas.

Backend/data owns shared observation/scenario/decision schemas. Forecasting/AI owns
engine inputs and result schemas. Frontend reviews examples before implementation.
Backend/data coordinates OpenAPI export; frontend regenerates TypeScript types.

## Task 1 — Frontend: make the decision journey usable

Owner: frontend/product teammate. Primary area: apps/web.

Build the five screens against agreed mocks, with a prominent crisis-mode entry.
Implement the first connected journey: overview alert -> facility bottleneck ->
incident form -> scenario results -> compare plans -> record chosen plan and owner.
Include the investment comparison view against a fixed example catalog.

Show input freshness, service units, current versus projected capacity, synthetic
data labels, assumed versus confirmed incident inputs, cost, time to effect,
remaining gaps and solver status. Include loading, incomplete-data, no-feasible-plan
and error states. Clearly label mock persistence and simulated personas.

Deliverable: a clickable routine and crisis workflow using contracts/examples,
ready to replace mocks with backend calls without changing result shapes.

Done when another teammate can complete the demonstration without instructions,
and the UI never presents an unimplemented action as a completed operational action.

## Task 2 — Backend/data: create a trustworthy shared scenario

Owner: backend/data teammate. Areas: core, facilities, ingestion, capacity,
scenarios, migrations, engines/capacity.py and shared contracts.

Implement models/migrations for facilities, resources, service requirements,
observations, scenarios, incident revisions and decision records. Add reproducible
synthetic facilities, historical activity and resource observations. Validate units,
nonnegative quantities, IDs, timestamps and required fields at ingestion.

Implement current usable-capacity calculations with bottleneck explanations.
Add an incident overlay that changes availability/demand assumptions without
mutating the baseline. Persist immutable run inputs and connect engine results
through services. Expose report, capacity, scenario and decision endpoints.

Deliverable: the three-hospital dataset and APIs used by both other teammates,
including one baseline and one sudden-disruption scenario.

Done when a saved scenario can be reloaded with identical inputs, changing an
incident preserves original reports, and capacity tests catch missing resources,
unit mismatches and double allocation of shared resources.

## Task 3 — Forecasting/AI: produce feasible, explainable alternatives

Owner: forecasting/AI teammate. Areas: forecasting, allocation, investments,
intelligence and the corresponding numerical engines.

Implement in this order:

1. A baseline forecast and projected gap calculation. Use a time-based holdout;
   report error and data limitations without treating synthetic accuracy as proof.
2. A pure response engine accepting a baseline or incident snapshot. Compare
   feasible actions under availability, donor reserves, receiver capacity,
   transfer eligibility, lead-time and budget constraints. Use a configurable
   solver time limit and return correct optimal/feasible/infeasible/unknown states.
3. An investment engine selecting from a small supplied candidate catalog,
   honoring costs, resource dependencies and time to effect.
4. An AI adapter to interpret incident reports and explain computed plans with
   source references. Flag contradictions for confirmation. Structured manual
   inputs and numerical plans must remain available when AI is unavailable.

Deliverable: independent numerical engines, typed result schemas, deterministic
example outputs for frontend work, and a report-to-proposed-incident adapter.

Done when constraint tests cover donor depletion, blocked transfers, insufficient
capacity, delayed investments and no feasible plan; forecast validation is reported;
and time to first feasible plan is measured on the shared scenario. AI explanations
must agree with computed quantities and must not fabricate unavailable actions.

## Integration order

First connect incident form -> saved snapshot -> capacity engine -> response
engine -> plan comparison. Then connect routine forecasts, investment comparison,
AI interpretation and decision follow-up. Each owner can build independently
against the committed contracts while this first end-to-end path is integrated.
