# Feature 3 demo cases and Task 3 handoff

All examples are fictional. Use the Feature 1/2 fixtures at
`2026-10-10T09:00:00Z`; do not reseed or overwrite a working database. Resource
assumptions remain `demo-v1`, not clinical staffing standards. A modeled subtotal
assumes independent hospital resources and is not spare admission or transfer
capacity.

## Files and ownership

- `summary-cases.json`: display-only projections and expected summaries. These
  are scenario inputs, not competing API response schemas. Full baseline rows
  come from the existing Feature 1 facility and Feature 2 capacity examples.
- `monitor-update.request.json`: submit to
  `POST /api/v1/facilities/DEMO-B/observations` in the disposable test database.
- `check-summary.mjs`: executable checks against the actual compiled TypeScript
  helper, including the existing full contract examples and input immutability.
- `apps/web/src/features/network/summary.ts`: Task 3's pure helper and display
  result type. Its minimal input projection reuses generated Feature 1/2 types;
  it does not duplicate the network wire schema. Once published, a generated
  `NetworkFacilityResult[]` is structurally compatible and can be passed directly.
- `apps/api/tests/test_network_api.py`: acceptance tests for teammate 2's actual
  endpoints, real capacity engine and disposable SQLite fixture database.

Teammate 1 owns components, filtering, generated type integration and navigation.
Teammate 2 owns network endpoints, wire schemas, contract examples and registration.
No Feature 3 network endpoints or wire schemas are implemented by this task.

## Expected display cases

| Case | Known / hospitals | Unresolved | Subtotal | Attention order |
| --- | --- | --- | --- | --- |
| Baseline A/B/C | 2 / 3 | 1 | 5 | C, A |
| B monitors updated to 8 | 2 / 3 | 1 | 8 | C, A |
| Empty filter | 0 / 0 | 0 | null | none |
| All unknown A/B | 0 / 2 | 2 | null | A, B |
| Only unavailable C | 1 / 1 | 0 | 0 | C |
| Only calculated zero B | 1 / 1 | 0 | 0 | B |
| Known rows with different profiles | 2 / 2 | 0 | null | C |
| Known unavailable C has no profile | 2 / 2 | 0 | null | C |
| A unconfigured, B calculated | 1 / 2 | 1 | 5 | A |
| Only an unconfigured service at B | 0 / 1 | 1 | null | B |
| Only positive calculated B | 1 / 1 | 0 | 5 | none |

The baseline label is **5 modeled places; 2 of 3 hospitals have known estimates;
1 unresolved**. A zero subtotal is visible as zero, never as a missing value.
For `no_known_estimates`, show that no estimates are known. For
`incompatible_profiles`, explain that assumptions differ and no subtotal is shown.
Profiles on unresolved rows do not prevent summing compatible known rows.

The subset scenario adds fictional `demo-outpatient` only at DEMO-B in a disposable
test database. A and C must be excluded, not marked unavailable. The service has no
profile, so B is `not_configured`. A catalog service with no offering must not
appear in the selector.

## Frontend integration

Pass the **same already-filtered rows** used by map and table to
`summarizeNetwork(rows)`. Use its counts, coverage, subtotal status and ordered
`attention_facility_ids`; resolve those IDs against the filtered rows. Positive
calculated rows do not belong in the attention list. The helper does not fetch,
filter, mutate input, format clinical warnings or calculate a hospital's capacity.

Mixed services and duplicate facility IDs are programmer errors and throw rather
than produce misleading totals. Invalid estimates and unsafe integer sums also
fail visibly. Different known profile versions/units suppress the subtotal while
preserving coverage and counts. Render resource evidence from the original rows.

Run the focused checks with Node 22 from the repository root (no browser/build):

```bash
apps/web/node_modules/.bin/tsc apps/web/src/features/network/summary.ts --strict --target ES2022 --module commonjs --moduleResolution node --skipLibCheck --rootDir apps/web/src --outDir /tmp/healthgrid-feature-3-summary
node data/synthetic/feature-3/check-summary.mjs /tmp/healthgrid-feature-3-summary/features/network/summary.js
```

## Backend test integration

Use the existing `client`, `engine` and `clock` fixtures from `tests/conftest.py`.
They create a separate in-memory SQLite database with synthetic records. The
network router should reuse the existing `facilities.router.server_now` dependency
(or coordinate its override in tests) to keep all calculations at one frozen time.

Tests exercise the public `facilities.service.get_snapshot`,
`capacity.service.get_profiles`, and `engines.capacity.calculate_service_capacity`
boundaries. Spies verify one snapshot per participating facility, one profile
validation/load per request, one timestamp and direct snapshot reuse. If teammate
2 binds functions differently, coordinate spy targets without weakening these
behavioral assertions. No cross-module repository access is needed in production.

```bash
.venv/bin/python -m pytest apps/api/tests/test_network_api.py -q
```

The test suite checks selector ordering, service exclusions, missing/malformed
query errors, unknown service, empty network, exact existing evidence, current
zero, stale reports, whole-request failures and a saved 5-to-8 monitor update.
Repeated overview reads must reflect the new observation without modifying the
old report or adding observations. The frozen receipt clock advances to 09:01
for that update; observed_at is 08:58. Live data ages against real request time.

The pulled backend now supplies the network endpoints and four published examples.
Acceptance tests compare real responses with all four examples, including the
missing-query error. Integration checks pass with the actual backend, capacity
engine and disposable SQLite database under the requested Python 3.14 environment.
The summary helper also checks the published network overview directly.

If the sandbox stalls at TestClient startup, run the test command with approved
execution outside the sandbox. No working database is used. Browser verification
belongs to the user; frontend dashboard integration remains teammate 1's task.
