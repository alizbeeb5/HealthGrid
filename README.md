# HealthGrid
Ministry-level health planning: what can we deliver, what should we do, and what
should we fund?

## Run the Beirut demonstration

Use your installed Python 3.12 environment. From the repository root:

```bash
python apps/api/scripts/run_beirut_demo.py
```

The web app also reads the root `.env` for server-side login settings. Existing shell,
Docker and `apps/web/.env.local` settings take precedence. Restart the web server after
changing credentials; do not copy secrets into `NEXT_PUBLIC_` variables.

In a second terminal:

```bash
cd apps/web
API_BASE_URL=http://127.0.0.1:8000 NEXT_PUBLIC_FACILITIES_DATA_MODE=api npm run dev
```

Open **http://localhost:3000/overview**. Stop any older HealthGrid server occupying
these ports first. Install the dependencies below if this is a fresh checkout.
No PostgreSQL or OpenAI key is needed for this exercise.

The launcher creates/resumes a dedicated SQLite file under `work/beirut-demo/`,
applies migrations, and calculates saved incident, response and investment runs.
It does not use or overwrite the normal database in `.env`. To restart the story,
stop the demo API and run `python apps/api/scripts/run_beirut_demo.py --fresh`;
old exercise files remain available. `--prepare-only` prepares without serving.
Restart the frontend if changing its proxy/data-mode environment.

The banner holds the exercise clock in August 2020. Use the Outcomes screen’s rehearsal buttons to
advance from assessment to simulated transfer reports, then recovery evidence.
These controls explicitly simulate approvals, completion and separate report
arrivals; normal approval buttons never change inventory. The presenter script
is in [docs/demo-scenario.md](docs/demo-scenario.md).

All five hospitals and operational values are fictional. Nineteen resource types
are displayed; five constrain emergency stabilization capacity. Saved calculations
show 28 → 36 → 48 supported simultaneous places under explicit assumptions.
Only monitors are transferred by the current allocator. Live AI buttons remain
optional billable requests when a server-side key is configured; startup and
rehearsal controls make no AI calls.

## Structure
- `apps/web`: Next.js, TypeScript, Tailwind, shadcn configuration, Recharts and React Leaflet.
- `apps/api`: modular FastAPI backend, PostgreSQL/SQLAlchemy/Alembic, numerical engines.
- `contracts`: generated OpenAPI and shared example payloads.
- `data`: synthetic fixtures and import templates.
- `docs`: architecture, team ownership and demo scenario.

The hospital snapshot frontend includes `/health` and
facility endpoints (list, snapshot, append observation). The network
overview and seven-day forecast screen/API are implemented. Incident simulation and monitor allocation screens/APIs are connected. Investment planning is connected to the OR-Tools package solver and saved-run API. Decision tracking and outcome review are connected. Optional shared sign-in is implemented; individual accounts and roles are not. Existing PyCharm `main.py` is preserved and is not the API entry point.

## Requirements
Use Python **3.12**, Node.js **22** with npm **9.5+**, and PostgreSQL **17** (or Docker Compose).
The existing `.venv` may use another Python version; create a Python 3.12 environment
for the numerical dependencies. `requirements.txt` includes the API requirements;
`requirements-dev.txt` adds developer tools. Frontend packages live in `apps/web/package.json`.
Python versions are constrained by `requirements.lock`; frontend versions are locked
in `apps/web/package-lock.json`. Refresh these deliberately when changing dependencies.

## Docker development
```bash
cp .env.example .env
docker compose up --build
```
Open http://localhost:3000 and API docs at http://localhost:8000/docs.
The database is local-only on port 5432. Docker handles Python/Node versions.
If frontend dependencies change, reinstall them in the web container and restart it.

Shared login is enabled when `SECURITY_PASSWORD` and a random 32+ character
`SECURITY_SESSION_SECRET` are configured in the ignored root `.env`; the default
username is `healthgrid`. The browser uses `/login`; direct API clients use HTTP
Basic. Recreate `api` and `web`
containers after changing credentials. See [security controls and deployment
limits](docs/security-review.md) before exposing the application remotely.

## Local development
From the repository root, create a separate Python 3.12 environment:
```bash
python3.12 -m venv .venv-healthgrid
source .venv-healthgrid/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
# Start local PostgreSQL, or run only the database using Docker:
docker compose up -d db
python -m uvicorn app.main:app --app-dir apps/api --reload
```
The web app also reads the root `.env` for server-side login settings. Existing shell,
Docker and `apps/web/.env.local` settings take precedence. Restart the web server after
changing credentials; do not copy secrets into `NEXT_PUBLIC_` variables.

In a second terminal:
```bash
cd apps/web
npm ci
npm run dev
```
Frontend page shells and the API `/health` endpoint work without a database or
OpenAI key. The facility endpoints need migrated, seeded tables (see below). For a
separately configured PostgreSQL instance, update DATABASE_URL in the root `.env`.

The hospital list, details, and resource update form are available at `/facilities`.
They default to the implemented API, with updates persisted by the backend.
Run the migration and seed commands below before using them. For a frontend-only
demo, set `NEXT_PUBLIC_FACILITIES_DATA_MODE=demo` in `apps/web/.env.local` and
restart/rebuild the frontend; those synthetic updates persist only in the same
browser. See `apps/web/src/features/facilities/README.md` for acceptance checks.

## Contracts and checks
```bash
python apps/api/scripts/export_openapi.py
cd apps/web
npm run generate:api
npm run typecheck
npm run test:facilities
npm run build
```
From the repository root, `ruff check apps/api` checks Python style and `pytest`
runs the API and migration tests on in-memory SQLite (no PostgreSQL needed).

## Database migrations
```bash
alembic -c apps/api/alembic.ini revision --autogenerate -m "describe change"
alembic -c apps/api/alembic.ini upgrade head
```
Add ORM models and register them in `migrations/env.py` first; inspect generated
migrations before applying. Revision `0001_facility_snapshot` creates the Feature 1
tables. Load the synthetic fixtures from `contracts/examples/feature-1` (safe to rerun;
existing observations are never modified):
```bash
python apps/api/scripts/seed_feature_1.py
```
Revision `0002_daily_history` adds the Feature 4 daily history tables. Import daily
history after seeding (all-or-nothing; existing days are never overwritten):
```bash
python apps/api/scripts/import_daily_history.py [path/to/daily-history.json]
```

## Team handoff
The finalized product workflow is in `docs/product-scope.md`; the next three
broad workstreams are in `docs/next-tasks.md`. The active Feature 4 contract is in `docs/feature-4-forecast-contract.md`.
Read `docs/team-ownership.md` before starting. Coordinate shared contracts first,
then develop frontend, data services and numerical engines independently.
Use synthetic data until authentication and permissions are implemented.

## Scaffold verification
The scaffold was checked with a frontend production build, TypeScript, Python lint,
API smoke checks and scientific-library imports. Docker is not installed on the
setup machine, so container startup and a live PostgreSQL connection are unverified.

## Forecasting startup

After activating your Python environment and choosing DATABASE_URL, run:
```bash
alembic -c apps/api/alembic.ini upgrade head
python apps/api/scripts/seed_feature_1.py
python apps/api/scripts/import_daily_history.py
```
Then start the API and frontend as above. Open /forecasts in API mode. The supplied
synthetic history ends on 2026-10-09; forecasts are valid at the fixture clock on
2026-10-10. Later dates correctly return insufficient_history until updated daily
records are imported. Frozen previews are available at /forecasts?mode=example.
Current resource updates do not rewrite daily history. This feature needs no AI key.

## Live incident AI review

`/scenarios` connects to the incident backend and optional OpenAI review. Add your
key to the repository-root `.env` (ignored by Git), never to the frontend:

```dotenv
OPENAI_API_KEY=your_api_project_key
OPENAI_ASSESSMENT_MODEL=gpt-6-luna
OPENAI_EXTRACTION_MODEL=gpt-6-luna
```

Restart the API after configuration (recreate the API container if using Compose).
Open `/scenarios`, click **Load sample report for AI review**, then
**Assess report · live** to see the actual Decisions flags, model and request time.
**Extract fields · live** independently requests a Responses proposal with evidence.
Review/edit the proposal and confirm assumptions before simulation. Each explicit
AI button sends a billable provider request when configured; nothing runs at startup.
Missing configuration or provider failures preserve manual input. The isolated
`/scenarios?mode=example` preview never calls OpenAI.

The local checks pass with Python 3.14 and Node 22; Python 3.12 remains the shared
project target. For environments that restrict Turbopack's local helper port, use
`npm run build --prefix apps/web -- --webpack` for production build verification.

On the same scenario screen, **Suggest emergency next steps · live** requests
prioritized guidance directly from the report and current hospital data, even when
field extraction fails. It uses the same API key; the default guidance model is
`gpt-6-luna` (`OPENAI_EMERGENCY_MODEL` can override it). Suggestions include steps,
reasons, prerequisites, evidence and questions. They do not dispatch resources or
calculate feasible transfer quantities. Changing the incident clears old guidance.


## Investment planning

Apply migrations through `0006_investment_runs` before using saved funding proposals.
Open a saved validated allocation, choose **Plan investments**, review the starter
catalog, enter UTC planning/evaluation dates and acknowledge the assumptions. **Calculate
and save funding proposal** calls the investment API and returns a persisted result.
The `proposal_id` URL reopens the frozen result without recalculating or reloading
current hospital observations/catalog. Edited constraints create a separate run.

The fictional $3,000 / three-month / 30-day demonstration selects repair plus
commissioning for $2,400, increases Hospital B from 3 to 8 modeled places and closes
its five-place modeled gap. Repair alone has no working-resource benefit. Different
budgets and deadlines change the result. No AI call, purchase or dispatch occurs.
Explicit `/investments?mode=example` remains an isolated fixed browser demonstration.

Additional checks: `npm run test:investments --prefix apps/web` and
`python -m pytest apps/api/tests/test_investments_api.py apps/api/tests/test_investment_engine.py`.


## Decision tracking and outcome reviews

Apply migration `0007_decisions` before using `/decisions`. Open a saved allocation
or investment proposal and choose **Record a decision**. Supply the owner,
rationale and deadline, submit and record approval. Record work started before
reporting action progress/completion; prerequisites are enforced by the backend.
Approval and reported completion do not alter hospital inventory.

Append resource reports using the hospital screen, select an explicit follow-up
observation window, and **Capture and save current evidence**. Reviews compare the
frozen proposal with reported capacity, show missing/stale reports and retain
capture time/status/version. The board reopens saved decisions and their review
history; later reports create a new review rather than changing previous evidence.
Expected proposal dates and human deadlines remain separate. Before the proposal's
expected date, reviews correctly return `too_early`. Identities are simulated demo
names. This feature uses no AI/optimization calls.

Additional checks: `npm run test:decisions --prefix apps/web` and
`python -m pytest apps/api/tests/test_decisions_api.py apps/api/tests/test_outcome_contract.py`.
