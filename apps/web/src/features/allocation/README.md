# Monitor transfer planning

The saved-incident journey is connected to the backend and OR-Tools engine.
From a saved Feature 5 simulation choose **Plan resource transfers**. Enter
simultaneous demand, donor floors, retained monitors, approved movable inventory,
receiving limits, directed routes, deadline, budget and provenance. Review the
inputs, then choose **Calculate and save proposal**.

POST `/api/v1/allocation/runs` calculates and saves the result in one operation.
The URL becomes `/allocation?proposal_id=...`; reopening or refreshing retrieves
the saved result through GET, without solving again. The displayed source comes
from the immutable saved simulation rather than live hospital observations.
The form uses generated OpenAPI request types. Capacities, counts, costs and
transfers come from Python; the frontend only maps them to the comparison panel.
No automatic retry or synthetic fallback follows a failed request. Field-level
validation errors remain visible and manual inputs are preserved.

The comparison shows solver status, exclusions, covered demand and unmet places,
hospital capacities/bottlenecks, transfers, costs, validation and engine metadata.
An optimal result can still leave demand unmet. Unknown means no incumbent or
proof within the limit; infeasible means conflicting hard constraints. Every
result is a proposal requiring human review; saving never dispatches equipment.

`/allocation?mode=example` remains an explicitly separate, fixed synthetic display
preview with browser storage. It does not call the solver or substitute for an API
failure. Live API calculation is available only from a saved simulation.

The synthetic shared demo transfers one monitor A → B, costing USD 100. A retains
three places, B increases from two to three, covered demand rises 5 → 6 and five
modeled places remain unmet. Canonical payloads are in `contracts/examples/feature-6`.

Checks: frontend type check, allocation client/render tests and production build
using the supported webpack builder (Turbopack worker ports were blocked here);
backend integration tests cover create/reopen, real solver outcomes, preservation
of reported observations and immutability after subsequent hospital updates.
