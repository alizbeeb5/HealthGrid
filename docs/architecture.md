# HealthGrid architecture
One monorepo, one FastAPI application with domain modules, one PostgreSQL database,
and one Next.js frontend. This is a modular monolith.

## Flow
Reported facility/resource observations -> usable service capacity -> forecast gaps
-> saved scenario -> response and funding alternatives -> dashboard comparison.

The finalized scope is in `product-scope.md`; immediate teammate assignments are
in `next-tasks.md`. Routine and crisis modes share the same modules. An incident
is a versioned overlay managed by scenarios. Intelligence interprets reports;
capacity and allocation engines recompute from confirmed inputs. Crisis mode does
not require a separate backend or an autonomous dispatch agent.

## Boundaries
- `apps/web`: presentation, inputs, charts and maps; no authoritative calculations.
- `modules/*/router.py`: HTTP and validation boundaries.
- `schemas.py`: Pydantic request/response contracts.
- `service.py`: coordinates use cases, engines and persistence.
- `repository.py`: database access owned by the domain module.
- `engines/`: pure numerical functions; no HTTP, database or OpenAI calls.
- `intelligence/`: server-side OpenAI adapter, report interpretation and explanation.
- `core/`: configuration, database sessions and future authorization.

Use services/contracts across module boundaries; do not reach into another
module's repository. The API/data owner coordinates all shared ORM and migrations.
Every future scenario run records immutable input snapshots, units, assumptions,
engine version, source freshness and timestamps. Changes to scenarios never modify
reported observations. A stored result must expose infeasibility and uncertainty.

Usable capacity is limited by combined service requirements: staffing, equipment,
supplies and infrastructure. Physical beds alone are not usable capacity.
Forecasting uses time-based validation; OR-Tools enforces explicit constraints.
AI-generated interpretations require evidence and review, and cannot override hard
constraints. Human approval is required before any operational action.

## Current state
The hospital snapshot frontend connects to Feature 1 facility persistence:
facilities, services, resource definitions and append-only observations, with list,
snapshot and observation endpoints. An optional synthetic demo stores updates in
the browser. Investments remains a page shell. The API liveness endpoint,
database connection setup and migration infrastructure exist. The Feature 2
capacity endpoint, engine and hospital capacity panel return and show modeled
single-service capacity from demo requirement profiles. The Feature 3 network
endpoints and overview dashboard compare hospitals per service. Feature 4 daily
history storage/import, forecasting engine, seven-day forecast endpoint and screen
are connected. Forecasts use complete UTC daily history and preserve historical
service status. Missing or stale history returns an insufficient-history state.
Feature 5 incident drafts, confirmed revisions, immutable baselines and saved
baseline-versus-scenario simulation runs exist in the backend and connect to the
incident screen. Decisions assessment and Responses extraction are server-side
endpoints invoked only by explicit review actions when configured with an API key.
Manual incident entry remains available without AI. Feature 6 allocation runs
(saved transfer proposals from a frozen simulation) exist in the backend; the
OR-Tools engine and planning screen are connected: reviewed constraints create and save a monitor-transfer proposal, and its URL reopens the frozen result. Domain routers are
registered in `app/routes.py`. Authentication is not implemented. Paid AI behavior
requires live account verification.
