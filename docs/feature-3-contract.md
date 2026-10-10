# Feature 3: Network capacity dashboard

Status: design and assignments only; not implemented.

## Purpose and workflow

Feature 1 records hospital resources. Feature 2 estimates one hospital's capacity.
Feature 3 gives a Ministry planner one view across participating hospitals:
which services are unavailable, where capacity is constrained, and which reports
need updating. This is a current operational overview, not a demand forecast or
proof that a hospital can accept transfers.

Workflow: open /overview -> select a service -> inspect map and hospital table ->
filter by capacity status -> open a hospital's existing details page -> record a
resource update -> return and refresh the network view.

Build these five elements:
1. Service selector, initially emergency-care when available, otherwise the first
   service sorted by service_id. With no services, show an empty state.
2. Summary cards: reporting hospitals, calculated estimates, unavailable services,
   unknown estimates, and unconfigured profiles. Include the modeled subtotal
   and its coverage, as defined below.
3. Map with one marker per hospital offering the selected service. Match marker
   badges to the table and include text labels; never rely on color alone.
4. Hospital table: name, modeled places, capacity status, bottlenecks, evidence
   warnings and last report received. Open existing facility details from a row.
5. Attention list: unavailable service, calculated zero, unknown estimate, or
   missing profile. These are operational review categories, not clinical triage.

Filters: service selection, facility-name search, capacity status (all/calculated/
unknown/unavailable/not_configured). Search and status filters affect map, table,
attention list and summary cards together. Always show the filtered hospital count.

No new incident form, forecasting, resource transfers, funding decisions or AI
calls in this milestone. The dashboard will provide the entry point for those
later features. Do not display invented demand, utilization, shortage probability
or a nationwide health score.

## Shared contract

GET /api/v1/network/overview?service_id=emergency-care

service_id is required and uses the existing Identifier constraints. Obtain
selector options from GET /api/v1/network/services, returning
`{"items": [{"service_id": "emergency-care", "name": "Emergency care"}]}`.
Only include services offered by at least one facility, sorted by service_id.
Names come from the existing service catalog. No new database tables are needed.

`NetworkOverviewResponse`:

| Field | Type / agreement |
| --- | --- |
| service_id | Requested service ID |
| service_name | Catalog name; null for an unknown ID |
| as_of | One UTC timestamp shared by all calculations in the response |
| stale_after_hours | Existing Feature 1 freshness policy |
| calculation_scope | Literal single_service |
| capacity_unit | Literal simultaneous_service_place |
| facilities | List of NetworkFacilityResult, ordered by facility_id |

`NetworkFacilityResult`:

| Field | Type / agreement |
| --- | --- |
| facility | Reuse Feature 1 Facility unchanged: ID, name, coordinates, last_reported_at |
| capacity | Reuse Feature 2 ServiceCapacityResult unchanged |

Return only hospitals that offer the selected service. A hospital that does not
offer it is not unavailable and must not be inserted with zero capacity. Unknown
service ID returns 200, service_name null and facilities []; malformed query uses
the existing 422 invalid_request envelope. An empty network returns services []
and an appropriate empty dashboard. Do not silently substitute a default service.

Keep snake_case, existing IDs/units/enums, null versus zero, reason_codes,
profile_version, and observation provenance. Do not introduce another capacity
calculation or copy the engine into the network module/frontend.

## Calculation and reliability agreement

The backend captures now once and loads one snapshot per participating facility.
Validate/load requirement profiles once per overview request and pass these
snapshots directly into the existing pure capacity engine. Do not make internal
HTTP requests, read another module's repository, or load a second snapshot to
calculate a row. Add narrowly scoped public facilities service methods if needed.
Use request-local snapshots; this milestone does not guarantee a transactionally
atomic nationwide snapshot when another user updates data during the request.

Fail the whole request on a database/configuration/unexpected calculation error.
Show a request failure rather than omit hospitals or turn technical failures into
unknown/zero estimates. Unknown is reserved for the documented data conditions.
Hide old results while refreshing; discard out-of-order responses when the user
switches services or refreshes rapidly. Fetch again on returning to /overview;
manual Refresh is sufficient, with no polling/WebSocket requirement.

Display summaries are computed from the current filtered rows. They count and
group existing results; they do not recalculate hospital capacity:
- counts for each of the four existing capacity statuses;
- known estimate count = calculated + unavailable;
- unresolved count = unknown + not_configured;
- modeled subtotal = sum of calculated estimates and unavailable zeros, only
  when all known rows share the same non-null profile_version and capacity_unit.
  If profiles differ (including a known row with no profile), display no subtotal
  and explain that assumptions differ. If no rows are known, subtotal is null.
- Label a subtotal with coverage, e.g. "5 modeled places; 2 of 3 hospitals have
  known estimates; 1 unresolved". It is not a complete network capacity total
  when some hospitals are unresolved. Never add different services together.

The subtotal assumes independent hospital resources. This demo has no shared
cross-hospital staff/equipment assignments. Do not label it spare admission or
transfer capacity. Mark demo data and fictional profile assumptions prominently.
last_reported_at is receipt time, not proof that every required resource is fresh;
use capacity.reason_codes/resource_limits for evidence warnings.

Default attention order: unavailable -> calculated zero -> unknown ->
not_configured -> remaining calculated results; use facility_id to break ties.
Positive calculated results still show bottlenecks, but do not label them as a
shortage without demand evidence. Keep filters and counts accessible if map tiles
fail; the table must remain usable.

## Three focused tasks

### Teammate 1 — Dashboard interface

Own apps/web/src/app/overview/page.tsx and the new
apps/web/src/features/network/ components, plus apps/web/src/lib/api/network.ts.
Build selector, cards, map, table and attention list against shared examples.
Use generated API types. Integrate teammate 3's display-summary helper rather
than writing a competing count/subtotal policy. Add links to /facilities/{id},
loading/error/empty states, latest as_of, Refresh and request-order protection.

Done: the same filtered hospitals appear everywhere; Demo A/B/C show their agreed
statuses; selecting a row opens Feature 1/2; returning refreshes the view. Browser
validation is performed by the user; no agent browser/build checks are required.

### Teammate 2 — Network API and shared schemas

Own the new apps/api/app/modules/network/ module, router registration, any public
facilities service additions, contracts/openapi.json and contract JSON examples.
Implement both GET routes and NetworkOverviewResponse using existing model types.
Reuse existing observations and capacity engine; do not add a database migration.
Publish Pydantic schemas/OpenAPI first so frontend type generation can proceed.

Done: a fixed-clock request matches the shared example; missing query is 422;
unknown service is an empty 200; service exclusions are correct; one shared as_of
is used; an observation update changes the network result without modifying history.

### Teammate 3 — Data, summary rules and verification

Own data/synthetic/feature-3/ documentation/scenario inputs,
apps/web/src/features/network/summary.ts and its type-only support definitions,
plus apps/api/tests/test_network_api.py. Coordinate test interfaces with teammate 2.
Implement a pure display helper `summarizeNetwork(rows)` returning
`facility_count`, `calculated_count`, `unavailable_count`, `unknown_count`,
`not_configured_count`, `known_estimate_count`, `unresolved_count`,
`modeled_capacity_subtotal` (integer/null), `subtotal_status`
(available/no_known_estimates/incompatible_profiles), and
`attention_facility_ids` (ordered IDs excluding positive calculated rows).
Input is the filtered NetworkFacilityResult[]; never fetch data or recalculate
capacity in this helper. Frontend teammate owns filters and UI integration.

Prepare expected cases for empty filters, all unknown, unavailable zero, calculated
zero, mixed profile versions, a service offered by only some hospitals, and
post-update capacity. Use existing fictional IDs; do not reseed or overwrite the
developer's working database. Keep helper examples and expected results documented
for the frontend owner; API tests use disposable databases.

Done: counts/subtotals match the rules, unresolved hospitals remain visible, and
API integration demonstrates the shared three-hospital scenario below.

## Shared demo and merge agreement

At 2026-10-10T09:00:00Z, existing fixtures yield:
- DEMO-A: unknown, null estimate, limited service and missing monitor observation.
- DEMO-B: calculated, 5 places, monitors are the bottleneck.
- DEMO-C: unavailable, 0 places, stale required reports remain visible.
- All rows: 3 hospitals, 1 calculated, 1 unknown, 1 unavailable, 0 not_configured;
  2 known estimates, 1 unresolved, modeled subtotal 5 under demo-v1.
- Save 8 monitors for DEMO-B at a newer valid time: its row and the subtotal become
  8; previous observations remain unchanged. Live data ages normally; the fixture
  clock is only for repeatable tests/examples.

1. Backend owns wire schemas and contract examples; all three agree here before
   coding. Teammate 3 owns display-summary semantics; frontend owns presentation.
2. Use feature-3/frontend, feature-3/api and feature-3/data branches in separate
   clones. Shared files and existing-module edits go through their owners.
3. Commit schemas and examples first. Frontend generates API types, then UI and
   helper work proceed in parallel with the endpoint. No hand-written duplicate
   wire interfaces or silent API-error fallback to fixtures.
4. Any field/rule change updates this agreement, examples, OpenAPI and consumers
   together. Keep existing Feature 1/2 endpoints backward compatible.
5. Merge helper and API, then frontend integration. Joint finish: overview ->
   Demo B -> update monitors -> overview refresh -> new row and subtotal.

The full product roadmap is unchanged. The next crisis feature can use these
facility/service IDs and capacity baselines to compare an incident scenario.
