# HealthGrid
Ministry-level health planning: what can we deliver, what should we do, and what
should we fund?

## Structure
- `apps/web`: Next.js, TypeScript, Tailwind, shadcn configuration, Recharts and React Leaflet.
- `apps/api`: modular FastAPI backend, PostgreSQL/SQLAlchemy/Alembic, numerical engines.
- `contracts`: generated OpenAPI and shared example payloads.
- `data`: synthetic fixtures and import templates.
- `docs`: architecture, team ownership and demo scenario.

This is a development scaffold with a hospital snapshot frontend, `/health` and
the Feature 1 facility endpoints (list, snapshot, append observation). Other
frontend routes remain page shells. Forecasting,
allocations, investments, import, authentication and remaining domain models are
placeholders. Existing PyCharm `main.py` is preserved and is not the API entry point.

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
broad workstreams are in `docs/next-tasks.md`. The active Feature 1 contract and
three focused assignments are in `docs/feature-1-contract.md`.
Read `docs/team-ownership.md` before starting. Coordinate shared contracts first,
then develop frontend, data services and numerical engines independently.
Use synthetic data until authentication and permissions are implemented.

## Scaffold verification
The scaffold was checked with a frontend production build, TypeScript, Python lint,
API smoke checks and scientific-library imports. Docker is not installed on the
setup machine, so container startup and a live PostgreSQL connection are unverified.
