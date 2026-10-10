# Fictional investment package demo

All projects, costs, idle equipment, compatibility and demand are synthetic,
human-reviewed planning assumptions. Nothing here changes reported observations,
executes an allocation transfer, purchases equipment or approves funding.

## Shared demo

The frozen post-allocation source has A: 3 monitors and demand 3; B: 3 monitors,
18 beds, 9 nurses and demand 8. C remains excluded. Transfers are explicitly
assumed complete at 2026-10-10 11:00 UTC. The evaluation is 30 days later.

| Candidate ID | Capital | Monthly operation | Readiness | Resource effect |
| --- | --- | --- | --- | --- |
| INV-B-BUY-5-MONITORS | $5,000 | $300 | 14 days | +5 working monitors |
| INV-B-BUY-1-MONITOR | $1,000 | $60 | 14 days | +1 working monitor |
| INV-B-REPAIR-5-IDLE | $1,000 | $0 | 7 days | None until commissioning |
| INV-B-COMMISSION-5-REPAIRED | $500 | $300 | 3 days after INV-B-REPAIR-5-IDLE | +5 working monitors |

With $3,000 and three full months of operating allowance, select INV-B-REPAIR-5-IDLE and
INV-B-COMMISSION-5-REPAIRED. Readiness is October 20 at 11:00 UTC. Total cost is $1,500 capital plus
$900 operation = $2,400; $600 remains. B capacity rises 3 → 8; included covered
demand rises 6 → 11; the modeled gap falls 5 → 0. C's demand is not treated as zero.

Below $2,400, the package cannot be funded. At $1,180 or above, buying one monitor
can close one place if it is ready by evaluation. Before day 10, repair has no
working capacity benefit; useless prerequisite-only work is not selected.

## Files and ownership

- `catalog.json`: reviewed starter candidates, matched to teammate 1's pushed
  frontend display IDs, costs, dependencies, provenance and effects.
- `post-allocation-snapshots.json`: fictional A/B quantities after exactly one
  source transfer; no reapplication of transfers inside the investment engine.
- `requirement-profile.json`: the existing demo capacity requirements.
- `planning-inputs.json`: inherited demand/coverage and explicit planning constraints.
- `demo-expectations.json`: expected numerical results for the shared demo.
- `engine-handoff.md`: internal numerical interface and canonical public DTO binding.

These are numerical fixtures, not independently published HTTP response schemas.
Teammate 2 owns the canonical investment types, catalog API and wire examples.
API mode runs the actual engine and persists results; explicit example mode is a fixed preview.

## Numerical behavior

CP-SAT minimizes unmet simultaneous places, then cost, then project count. All
sequential solves share one five-second budget. Only proven optimal objectives
are frozen. A feasible incumbent is independently checked before publication;
unknown/no incumbent has no proposed package. Costs include every prerequisite
once and the full operating allowance for every selected project. No prior
transfer cost is charged again.

Readiness follows the latest prerequisite plus implementation time. Exclusions
propagate from missing confirmation and late prerequisites. Effects apply once
only to known operating source facilities. The existing capacity engine verifies
every requirement and all resulting bottlenecks. Missing information stays
excluded; purchases cannot reopen an unavailable service.

Alternative projects restoring the same assets must use an exclusive group. In
custom catalogs with multiple final commissioning alternatives, group those final
effects as well so the same five idle monitors cannot be counted twice. Different
projects can share a prerequisite; prerequisite sharing does not imply independent
ownership of the same physical assets.

Tests cover the demo, budget/deadline changes, coupled resource bundles, shared
prerequisites, exclusive assets, stale/missing evidence, zero availability, exact
ratios, malformed inputs and timeout statuses. Exhaustive comparison checks 42
small budget/deadline combinations against all project subsets.

Run from the repository root:

```bash
.venv/bin/python -m pytest apps/api/tests/test_investment_engine.py -q
```

Checks use the existing Python 3.14 environment, as requested. Python 3.12 remains
the shared deployment target. Frontend and backend integration checks also pass.
