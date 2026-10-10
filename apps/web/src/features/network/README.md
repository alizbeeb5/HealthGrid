# Network capacity overview — Feature 3 Task 1

The `/overview` dashboard compares one service across participating hospitals.
It uses the backend-owned network types generated from `contracts/openapi.json`
and the Task 3 `summarizeNetwork` helper unchanged. Capacity remains calculated
in the Python engine. No backend schemas, migrations or observations are modified
by this frontend task.

## Data and consistency

API mode calls `GET /api/v1/network/services`, then
`GET /api/v1/network/overview?service_id=...` through the existing Next.js proxy.
It defaults to emergency care when offered, otherwise the first service by ID.
An explicitly requested unknown service stays selected and returns an empty view.
An empty service catalog has its own empty state. Failures show a whole-view error;
no API failure substitutes synthetic examples or silently omits hospitals.

The same name/status-filtered rows feed the summary helper, map, comparison table,
and attention list. Subtotals and attention ordering come only from the owned
helper. Null is displayed as unavailable, distinct from a valid zero. Incompatible
known requirement profiles suppress the subtotal and explain the differing
assumptions. Coverage and unresolved counts remain visible.

One API overview provides all rows and their shared `as_of`. The table exposes
service status, bottlenecks, profile versions, reason codes as explanations,
resource quantities/units/requirements, observed timestamps and observation IDs.
Receipt timestamps never stand in for individual-resource freshness. Fictional
demo assumptions and independent hospital resources are labeled; no subtotal is
presented as spare admission or transfer capacity.

The map is loaded on the client with React Leaflet. Markers include name/status
text and keyboard-accessible popups linking to hospital details. Map tile failures
leave the filters, cards, attention list and table usable. Invalid coordinates,
if ever received, are reported without dropping hospitals from other views.

## Examples and navigation

In API mode, the Reports selector explicitly opens a frozen synthetic preview at
`/overview?mode=example`. It uses the canonical Feature 3 examples bundled by
`scripts/sync-network-fixtures.mjs`; development/build startup syncs the bundle.
Docker retains the committed bundle when shared contracts are outside its image.
Never edit `network-fixtures.generated.json` manually. Refresh in preview mode
reloads fixed examples, not saved resource updates. Browser-demo configuration
always uses this preview, so it cannot mix API results with browser-only saves.

Name, status, service and source are kept in the URL. Hospital links include a
validated local `return_to` path; the existing details page displays “Back to
network overview” and restores those filters. Other hospital entry points retain
“All hospitals”. Mounting the overview fetches again, with a `pageshow` handler
for browser cache restoration and a manual Refresh button. Generation guards
discard older responses/errors, including service/catalog races. Previous results
are hidden throughout a refresh. Name/status filters do not make network requests.

## Checks and browser acceptance

From the repository root:

```bash
npm run generate:api --prefix apps/web
npm run typecheck --prefix apps/web
npm run test:network --prefix apps/web
npm run test:facilities --prefix apps/web
npm run test:capacity --prefix apps/web
node data/synthetic/feature-3/check-summary.mjs "$PWD/apps/web/.test-build/apps/web/src/features/network/summary.js"
```

The frontend tests verify published fixtures, summary/attention presentation,
filtered-row consistency, null/zero distinction, incompatible assumptions,
missing profiles, safe return navigation, API errors and request ordering.
The helper's policy tests and API acceptance tests remain teammate-owned.

The user performs browser/map validation as agreed in `docs/feature-3-contract.md`:

1. Open the frozen preview. Confirm A is unknown, B has 5 modeled places with
   monitors limiting it, C is unavailable/0, and coverage is 2 of 3 with 1 unresolved.
2. Filter name/status; confirm cards, markers, table and attention match. Clear
   filters. Inspect the stale/missing resource timestamps and evidence warnings.
3. In Connected reports, open B, save a newer monitor observation, use Back to
   network overview, and refresh. Confirm B and the compatible known subtotal
   reflect the saved backend result. To reproduce 5→8, use a disposable seeded
   database and current required observations (18 beds, 9 nurses, 5 monitors),
   then save 8 monitors. Preserve working reports; do not reseed a working database.
4. Confirm filters survive the round trip. Block map tiles and verify the table,
   filters and cards remain usable. Try an empty name filter, unknown service URL,
   and an offline API; none should produce an invented zero or a silent demo fallback.

Live freshness uses actual request time; old synthetic seed reports may become
stale. The preview's fixed clock is only for repeatable examples.
