# Hospital operational snapshot

`/facilities` lists hospitals; `/facilities/{facility_id}` displays services,
reported resources, and a resource observation form. JSON keys and types come
from the agreed Feature 1 contract; location is latitude/longitude, with no
invented address field. The UI keeps zero, unknown, and stale reports distinct.

## Data source

API mode is the default and uses the implemented FastAPI endpoints through the
existing server proxy (`API_BASE_URL`). Run the migration and seed commands in
the root README first. Saved API observations append to the backend database.

The optional `NEXT_PUBLIC_FACILITIES_DATA_MODE=demo` uses the shared synthetic
examples in `contracts/examples/feature-1`. Observations append to localStorage
under `healthgrid:synthetic-observations:v1`, survive browser refresh, and stay
separate from API data. This is a browser demonstration, not database persistence.
The fixture snapshot clock starts at `2026-10-10T09:00:00Z` and advances one second
per save; it controls demo freshness and the five-minute future-time tolerance.
The form starts at that clock in demo mode. All displayed times use the browser's
local timezone; submissions convert to UTC. Clearing site data resets the demo.

`npm run sync:facilities` generates the committed
`src/lib/api/facilities-fixtures.generated.json` bundle from the shared examples.
Development startup and production builds run it automatically. Docker uses
the committed bundle because its frontend image contains only `apps/web`.
Tests check the bundle against the canonical examples; do not edit it by hand.

Set `NEXT_PUBLIC_FACILITIES_DATA_MODE=api` or `demo` in `apps/web/.env.local` and
restart Next.js (rebuild for production) when changing modes.
API mode uses GET list, GET snapshot, and POST observations with no mock fallback.
The typed client exports `listFacilities`, `getFacilitySnapshot`, and
`createResourceObservation` from `src/lib/api/facilities.ts`. No backend schemas,
database models, or migrations were changed for this frontend task.

Every save refetches the snapshot. A historical report may save successfully
without changing the displayed latest quantity. The form disables repeat saves
while pending; ambiguous network/5xx save failures require refreshing before
another submission. Client checks provide input feedback; Python owns authoritative
validation in API mode.

## Verify

```bash
npm run typecheck --prefix apps/web
npm run test:facilities --prefix apps/web
npm run build --prefix apps/web
```

Manual demo acceptance: select Demo Hospital A, enter a whole-number bed quantity,
keep the default demo observation time, save, then refresh the browser. Confirm
the quantity remains. Submit a historical observation and confirm the latest
quantity stays unchanged. Demo Hospital C shows stale zero quantities; Hospital A
has unknown monitors. Search for a nonexistent hospital to inspect the empty
state. Submit blank or fractional bed quantities to inspect validation. API
mode acceptance uses the migrated, seeded backend: submit an observation at the
current local time, refresh the browser, and confirm the saved value remains.

## Feature 2: current capacity and bottlenecks

The hospital details page now includes a capacity panel per service. It displays
the backend estimate as “Modeled service places”, all tied bottleneck names,
resource quantities and units, requirements per place, supplied resource limits,
observation timestamps/IDs, profile version, and capacity's own `as_of` timestamp.
Unknown, unavailable/zero, not-configured, no-services, loading, updating, and
request-error states are distinct. Explanations preserve every returned reason.
The panel labels demo assumptions and states that estimates apply to each service
separately and are not confirmed spare admission capacity. No numerical capacity
calculations execute in the frontend.

`src/lib/api/capacity.ts` requests
`GET /api/v1/capacity/facilities/{facility_id}` through the same proxy. A saved
observation and the hospital refresh action refetch both snapshot and capacity.
Capacity errors stay inside the panel and do not turn a successful observation
save into a failed save. Old capacity is hidden while updating; a generation
counter prevents older requests or errors from replacing newer results.

API mode uses the implemented capacity endpoint and Python engine. Response types
in `src/lib/api/feature-2.ts` alias the generated OpenAPI `components["schemas"]`
types. After a backend contract export, run `npm run generate:api --prefix apps/web`
from the repository root to refresh them. API errors never display sample results.

Browser demo mode starts with a frozen synthetic capacity preview and offers a
“View synthetic example” button after refresh. These examples never claim to
reflect saved updates; refreshing invalidates the example because browser demo
mode cannot calculate capacity for its local observations. Use API mode to test
capacity changes. Shared examples are bundled by `scripts/sync-capacity-fixtures.mjs`;
do not edit `capacity-fixtures.generated.json` by hand. Additional display fixtures
cover not-configured and no-services states for frontend tests.

```bash
npm run test:capacity --prefix apps/web
npm run test:facilities --prefix apps/web
npm run typecheck --prefix apps/web
npm run build --prefix apps/web -- --webpack
```

Capacity tests render the contract examples, exercise unknown/stale/unavailable,
valid zero, tied bottlenecks, empty and not-configured states, and verify request
ordering and consumption of an updated API estimate from 5 to 8 using mocked
responses. For live acceptance in API mode, open Demo Hospital B and save current
observations for 18 available beds, 9 on-shift nurses, and 5 working monitors.
Confirm capacity is 5 with monitors as the bottleneck. Save 8 working monitors
with a newer observation timestamp, then refresh the page and confirm capacity
remains 8. With a real runtime clock, old seed data can be stale; every required
resource needs a current report. Historical updates do not replace newer reports.
The user handles browser checks as agreed in `docs/feature-2-contract.md`.
