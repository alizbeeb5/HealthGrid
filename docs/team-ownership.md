# Three-person workflow

See `product-scope.md` for the finalized routine/crisis workflow and `next-tasks.md`
for broad workstreams. The active Feature 7 assignments and shared interfaces
are in `feature-7-contract.md`. Frontend owns investment inputs and package comparison;
backend/data owns investment schemas, catalog endpoints, frozen source integration
and saved runs; the third teammate owns the pure package solver and numerical
fixtures/tests. Features 1–6 retain their existing contracts and ownership.

| Owner | Primary files | Deliverable |
| --- | --- | --- |
| Frontend | apps/web | Overview, facilities, forecasts, scenarios, investments |
| Backend/data | core, facilities, ingestion, capacity, scenarios, migrations | Validated data, usable capacity, saved scenarios |
| Forecasting/AI | forecasting, allocation, investments, intelligence | Forecasts, feasible response/funding plans, report interpretation |

For Feature 2, the third teammate owns `engines/capacity.py`, while backend/data
owns the capacity API and Pydantic schemas. Outside this milestone, the
backend/data owner owns `engines/capacity.py`; the forecasting/AI owner owns
other numerical engines. Domain owners maintain their routers and schemas, with
backend/data review for persistence changes.

## Work independently
1. Agree on IDs, units, scenario inputs, outputs and error cases before feature work.
2. Commit Pydantic schemas and matching example responses in `contracts/examples`.
3. Frontend uses those examples as mocks while backend endpoints are implemented.
4. Numerical engines accept typed data and return results without database access.
5. Backend integrates the engines through services using the same input contracts.
6. Each person uses a separate clone, local database and feature branch.
7. Merge small changes frequently; regenerate OpenAPI/types when contracts change.

Coordinate edits to requirements, compose.yaml, shared settings, API router
registration and migrations. Keep `requirements.lock` and the frontend `package-lock.json` in sync with
dependency changes. The initial Python constraints were resolved on Linux/Python 3.12. Do not overwrite
another teammate's work or commit secrets. No branch protection is configured yet.
