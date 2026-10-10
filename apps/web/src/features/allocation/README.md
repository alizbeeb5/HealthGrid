# Monitor transfer planning frontend

Agreement: `docs/feature-6-contract.md`. Frontend ownership is `apps/web` only.
Allocation schemas/router/engine and canonical Feature 6 JSON are still placeholders
in this checkout. No optimization or server proposal persistence is implemented by
these UI files. Do not claim that OR-Tools ran in the browser.

## Saved-incident journey

A saved Feature 5 comparison links **Plan resource transfers** to
`/allocation?simulation_run_id=...`. This loads the saved run/revision through the
existing API and exposes frozen scenario capacity, resource evidence, profile,
confirmed overrides and baseline timestamp. It never queries current hospital
observations for the planning baseline or changes any reports.

The editor starts with blank planning quantities: demand, protected service capacity,
retained monitors, explicitly approved movable monitors and receiving limits. The
planner chooses included hospitals, approved directed routes, travel times/quantity
caps/costs, source notes and UTC confirmation timestamps, response horizon, budget
in USD cents and additional assumptions. Zero must be explicit; unknown is blank.
Whole-number, provenance, route-ID/pair, inclusion and input-review feedback is
presentation validation only. The Python engine owns hard constraint enforcement.

Donor protection, no re-exporting of incoming inventory, service closure/limited
states, fixed beds/nurses and direct parallel transfer assumptions are explained.
Forecast volumes/inventory never auto-fill simultaneous demand or movable inventory.
The calculation button is visibly disabled until the real allocation schemas and
endpoint are supplied. API request failures never select an example as a fallback.

## Explicit browser preview

`/allocation?mode=example` uses a frontend-owned display fixture, not an agreed
wire payload or engine output. **Load agreed synthetic constraints (A → B)** populates
the exact demo in the contract. Review/acknowledge inputs, then **Show fixed proposal
example**. The fixture supplies one monitor A → B, USD 100 cost, capacities A 4 → 3
and B 2 → 3; covered demand 5 → 6 and unmet demand 6 → 5. C is visibly excluded and
its demand is uncounted rather than zero. Invented solver times/versions are omitted.

The lookup accepts only those unchanged example inputs. Editing any constraint
invalidates the displayed result and requires a backend solve; no numerical forecast,
capacity, donor eligibility, cost objective or allocation arithmetic runs here.
**Save browser example for review** stores the fixed inputs/evidence/result under a
separate allocation-preview key. Its `proposal_id` URL/list entry reopens after
refresh without a new calculation. Storage failure is shown; prior data is not reset.

A separate **Inspect hypothetical solver-result states** panel demonstrates needs
inputs/not run, no improvement, feasible timeout incumbents, unknown/no incumbent
and proven infeasibility. Those hypothetical states cannot be saved as calculated
plans. Proposed summaries/transfers are withheld without passed validation and a
feasible/optimal incumbent. Optimal can still have remaining unmet demand; unknown
is not proven infeasible. All preview results are labeled synthetic display examples.

## Backend integration handoff

After backend/data publishes Pydantic/OpenAPI, `contracts/examples/feature-6/` and the
shared typed engine interface:

- Regenerate `schema.d.ts`; replace internal editor/presentation boundary mappings
  with generated wire types and canonical request/example files.
- Connect POST `/api/v1/allocation/runs` and GET `/api/v1/allocation/runs/{id}` through
  the existing same-origin proxy. POST uses the complete visible reviewed constraints;
  no automatic retry after ambiguous errors and no solve triggered on startup.
- Map saved coverage, baseline/proposed summaries, transfer costs, validation,
  versions/settings/duration and remaining-gap reasons without recalculating them.
- Reopen immutable saved inputs/result by allocation ID. Retain exclusions, unknowns,
  feasible versus optimal status and absent proposals. Never use live reports to
  replace a saved input or silently fall back to preview storage.
- Preserve field-level 422 errors, missing simulation 404, independent solver errors
  and source/constraint edit guards. Proposals remain for review, never dispatch.

## Checks

`npm run typecheck --prefix apps/web` checks frontend types; `git diff --check` checks
patch formatting. Per the Feature 6 agreement, no browser checks, frontend builds
or test suites were run. User browser acceptance: saved simulation navigation,
blank/zero distinction, all constraint/provenance fields, explicit sample lookup,
input edits hiding old results, incomplete coverage, every solver-state example,
storage errors and saved proposal refresh/reopening. Live calculating/persistence
acceptance waits for teammates' backend contract and OR-Tools implementation.
