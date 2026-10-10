# Beirut explosion exercise — canonical pack

All operational records here are synthetic. Hospital names and approximate map
positions are fictional. The historical context is the 4 August 2020 Beirut port
explosion; none of these quantities, costs, routes, staff ratios or local scenario
timestamps is a reconstructed hospital report or a clinical recommendation.

See `docs/beirut-demo-enhancements.md` for historical sources, the
presentation script and the integration sequence.

Scenario source files:

- `resource-definitions.json`: 19 catalog entries using existing resource schemas.
- `service-requirement.json`: illustrative emergency stabilization profile; five
  constraints, including physicians and supplied oxygen points.
- `snapshots.json`: before/incident phases for five fictional facility roles.
- `allocation.input.json`: typed pure-engine input for a monitor transfer.
- `investment.input.json`: typed pure-engine input for a later recovery package.
- `expected-results.json`: checked capacity results and key scenario expectations.
- `counterfactuals.json`: engine-checked examples where adding the wrong resource
  provides no capacity improvement, for the “Why this action?” comparison.

The isolated launcher consumes these fixtures through existing domain services:
`python apps/api/scripts/run_beirut_demo.py`. It also generates 63 days of synthetic
pre-event history, a confirmed incident with an immutable pre-event baseline,
saved allocation and investment proposals, decision drafts and a shared manifest.
Rehearsal stages append synthetic follow-up reports, completed-day history and outcome reviews. Resume repairs missing history while preserving existing records.
Older feature fixtures remain regression cases and are hidden from exercise navigation.

Engine-input files are not HTTP request bodies. HTTP shapes and generated example
payloads are documented in `docs/demo-contract.md` and `contracts/examples/demo`.

Only five resources enter this profile: treatment spaces, assigned emergency
nurses, emergency physicians, monitors and supplied oxygen points. The other
resources are contextual observations, not hidden capacity/stockout calculations.
Blood units are catalog items separated by product group; crossmatching, expiry
and patient suitability are not modeled. Staff are explicitly assigned to this
service in the exercise; do not reuse their full counts for parallel surgery/ICU
capacity. Oxygen points mean a supplied functional connection at snapshot time,
not proof of sufficient oxygen duration.

The synthetic future demand is 48 simultaneous places across the three included
operating facilities. Coverage is 28 after the incident, 36 after the proposed
transfer, and 48 at the later recovery evaluation if the staffing/repair assumptions
hold. Closed and unconfirmed facilities are visibly excluded from these totals.
The pack has no casualty estimate or measured patient outcomes.

Every run must preserve provenance: `snapshots.json` represents invented exercise
reports. In `investment.input.json`, quantities changed by assumed transfers have
no observation IDs/times; they are scenario assumptions, not received deliveries.
Frozen source snapshots retain their original assessment time. A fresh follow-up
review requires new reports; do not reuse these as evidence of execution.
