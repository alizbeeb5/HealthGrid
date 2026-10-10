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

## Live AI review and explicit example mode

API mode posts the entered report to `/api/v1/intelligence/incidents/assess`
(OpenAI Decisions) and `/api/v1/intelligence/incidents/extract` (OpenAI Responses).
Generated wire types map the independent component statuses into the review panel.
The panel displays actual returned flags, model and elapsed time; extraction retains
source excerpts, questions and warnings. Unavailable, refused, failed, invalid-report
and transport failures never substitute example flags or change manual input.
Report changes discard responses and manual edits block stale proposal application.
Requests happen only on explicit button presses and are never automatically retried.

Set `OPENAI_API_KEY` in the repository-root `.env` or API environment, then restart
or recreate the API process. Never put it in `NEXT_PUBLIC_*`, frontend storage or Git.
`OPENAI_ASSESSMENT_MODEL=gpt-6-luna` is the Decisions default. To enable the separate
Responses extraction, also set `OPENAI_EXTRACTION_MODEL=gpt-6-luna` (or a compatible
Responses model your project supports). Docker Compose forwards these settings.
The key's API project needs access and billing. No key was configured during checks,
so paid provider behavior and account access have not been verified.

Demo: open `/scenarios`, choose **Load sample report for AI review**, then
**Assess report · live**. The report is fictional; the classification is requested
from OpenAI. Optionally choose **Extract fields · live**, inspect the evidence,
use the reviewed proposal, edit/confirm assumptions and simulate/save. Reopen the
saved comparison after refreshing. The separate **Load synthetic B outage** action
fills manual fields without making an AI request.

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

The user requested integrated checks: backend tests, Python lint, frontend typecheck,
frontend tests and a production build. `npm run test:intelligence --prefix apps/web`
checks real endpoint routing, provider-response mapping, rendered metadata and
failure states with stub HTTP responses. No paid AI calls run in tests. The webpack
production build passes; this environment blocks Turbopack's local helper port.
Live account verification and a complete browser save/reopen walkthrough remain
manual acceptance checks once the local services and API key are configured.

## Emergency next-step guidance

API mode also renders `EmergencyAdvicePanel`. Its explicit live button posts the
current draft to `/api/v1/intelligence/incidents/advice`. Suggestions display priority,
hospital IDs, steps, rationale, prerequisites, supplied evidence values and questions.
Changes to any incident field discard previous/pending guidance. No advice is copied
into assumptions automatically, saved as a run or executed. The backend uses current
snapshots and calculated capacity, not the fixed browser example. The preview mode
has no emergency-guidance calls. Feature 6 remains investments and broader planning.
