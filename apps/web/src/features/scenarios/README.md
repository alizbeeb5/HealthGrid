# Emergency assessment and impact frontend

Agreement: `docs/feature-5-contract.md`. Frontend ownership is `apps/web`.

## Connected manual flow

`/scenarios` defaults to the implemented incident API through the same-origin proxy.
The overview **Declare incident** link opens it. Facility/service/resource options
come from the live Feature 1 catalog. Generated OpenAPI types define incident input,
service/resource overrides, revisions, saved runs and conflict/error payloads.

Enter an incident manually (or load the explicitly synthetic B outage form):

1. Save/reopen a draft. Editing a saved draft creates a new incident; no PATCH
   overwrites exist. URLs include both incident and revision IDs for direct reopening.
2. Review the complete visible input, resource units, reporting limitations and
   temporal assumptions. Confirm with an explicit acknowledgement and demo reviewer
   display name. The backend captures immutable reports and full profile content.
3. Simulate/save through the Python engine. The comparison shows supplied before,
   after and signed change, including unknown/null and unavailable/zero states.
   Applied service/resource overrides are labeled assumptions; resources outside the
   requirement profile are explicitly marked as not affecting the estimate.
4. Reopen the saved `run_id` URL after refresh. Repeating simulation for a confirmed
   revision retrieves the same saved run. The API has no run-list endpoint, so the
   UI shows runs loaded in the current workspace and offers saved confirmed incidents as the
   path to retrieving other runs; it never simulates on startup to discover them.

The live B baseline depends on the reports captured at confirmation; a prior monitor
update to 8 correctly produces 8 -> 0 instead of forcing the frozen example's 5 -> 0.
Missing/stale reports and unquantified limited services remain visible. No capacity,
impact, shortage, network subtotal or patient-flow calculation runs in the browser.
Start/end dates describe one post-incident state, not past reconstruction or automatic
recovery. No observation/history writes are issued by this feature.

POSTs are never automatically retried. Ambiguous failures block further saves until
saved incidents are successfully refreshed/reopened. 409 conflicts expose the existing
revision link; validation failures expose the backend field paths. Requests are
uncached and route loads discard outdated responses. Server errors never use examples.

## AI handoff and explicit example mode

The pulled intelligence router/schemas still have no endpoints. Assess/extract return
clearly unavailable presentation states without making invented HTTP or OpenAI calls.
Manual entry works without an AI key. Assessment/extraction states are independent;
report changes discard proposals and manual edits block stale proposal application.
Connect these adapters after the AI owner publishes generated schemas and examples.

`/scenarios?mode=example` is a separate browser-only synthetic preview. Its versioned
storage is independent from API incidents and operational demo reports. It supports
local drafts/confirmation and only the fixed B emergency-unavailable comparison.
Other assumptions fail visibly rather than using that fixture. No Python/AI call runs
in this mode. **Show synthetic review example** demonstrates evidence/questions and
editable proposal presentation without pretending it is provider output.

`outage-preview.json` is a frontend display fixture, not a backend wire contract or
engine calculation. API mode does not read it for outcomes. `preview-client.ts` is
isolated from `api-client.ts`; `model.ts` aliases generated input types and maps saved
outputs for presentation. Future wire changes belong to the backend/data owner.

## Verification and startup

`npm run generate:api --prefix apps/web` regenerates types from committed OpenAPI.
`npm run typecheck --prefix apps/web` checks the frontend. Focused backend checks:
`python -m pytest apps/api/tests/test_scenarios_api.py -q`.

Before local API startup, apply the pulled migration without resetting existing reports:
`alembic -c apps/api/alembic.ini upgrade head`, then restart the API process to load
its new incident routes. The database must already have the Feature 1 catalog/data.

Per the Feature 5 agreement, no automatic frontend tests/builds or live AI calls were
run. User browser acceptance: manual outage save/reopen, confirmation acknowledgement,
B capacity comparison, saved run refresh, resource assumptions, unknown/stale reports,
AI unavailable/manual fallback, error/conflict recovery, and a later hospital report
update that leaves a reopened run unchanged.
