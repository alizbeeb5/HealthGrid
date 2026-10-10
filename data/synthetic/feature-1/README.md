# Feature 1 fictional hospital fixtures

All records are synthetic, manually authored demo data. Hospital names and
coordinates are illustrative; these are not real reports or clinical estimates.
Service statuses are supplied demo values, not calculated usable capacity.

## Shared inputs

Paths below are relative to the repository root.

| Input | File | Contents |
| --- | --- | --- |
| Facilities | `contracts/examples/feature-1/facilities.response.json` | Three canonical facilities, including last receipt timestamps |
| Resource catalog | `contracts/examples/feature-1/resource-definitions.json` | Four resource definitions with units and fractional-quantity rules |
| Services | `data/synthetic/feature-1/services.json` | Three FacilityService records |
| Applicable resources | `data/synthetic/feature-1/facility-resources.json` | Twelve facility/resource pairs, including resources with no report |
| Reported observations | `data/synthetic/feature-1/observations.json` | Eleven ObservationResponse records matching the baseline snapshots |
| Expected snapshots | `contracts/examples/feature-1/DEMO-{A,B,C}.snapshot.response.json` | Shared frontend mocks and expected baseline backend results |

The applicability file is seed metadata, not a new API payload or database schema.
The existing `data/synthetic/facilities.csv` contains the same facility identities
and coordinates; use the canonical JSON for complete Facility records.

## Demo cases

Evaluate freshness at **2026-10-10T09:00:00Z**, with a 24-hour threshold.
Do not use today's clock to compare these fixed fixtures with the expected mocks.

| Hospital | Emergency care | Beds (bed) | Nurses (person) | Oxygen (liter) | Monitors (item) | Expected case |
| --- | --- | --- | --- | --- | --- | --- |
| DEMO-A | limited | 12 | 6 | 800.5 | unknown | Three current reports; no monitor observation |
| DEMO-B | operating | 18 | 9 | 1200 | 5 | Complete current observations |
| DEMO-C | unavailable | 0 | 2 | 0 | 1 | All reports are 26 hours old and stale; zeros remain known values |

Hospital A's monitors are applicable but have no observation record. Its snapshot
must return null quantity, observation ID and timestamps, with status `unknown`.
Never insert a zero observation to represent missing data. Hospital C's reported
zeros must remain zero even though their reports are stale. Actual availability
is uncertain when reports are missing or outdated. No capacity or feasibility
assessment is included in these fixtures.

## Teammate handoff

Frontend uses the existing list and snapshot examples directly. Backend can seed
the facilities and catalog, then services and applicability, then observations
through its own persistence code. This folder does not implement an importer or
change database models. Keep these seed records and the shared examples aligned
when either changes; preserve stable IDs and explicit units.

The baseline contains only the eleven initial observations. Do not seed
`observation.response.json`: it represents the subsequent user update of Hospital
A's beds from 12 to 10. That update is submitted using `observation.request.json`;
the live backend assigns its own observation ID and receipt timestamp. After a
successful save and refresh, the newer bed observation should appear and the old
one should remain in history. End-to-end persistence still requires teammate 2's
backend and the frontend integration.
