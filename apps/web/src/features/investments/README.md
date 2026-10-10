# Connected investment planning

The investment screen uses generated backend schemas through the existing API
proxy. It loads a saved, validated allocation and the canonical starter catalog,
submits the complete reviewed candidate list to `POST /api/v1/investments/runs`,
and reopens the immutable saved result using `GET /api/v1/investments/runs/{id}`.
The result URL is `/investments?proposal_id=...`. Reopening uses the saved baseline,
inputs and project evidence; it does not reload current observations or catalog.

Editor feedback checks quantities, dates, IDs, dependencies and units. Definitive
validation, project readiness/costs, optimization and capacity calculations are
server-side. Field errors remain visible. Failed saves are never retried or
substituted with examples; edited inputs invalidate displayed results. Outdated
calculation responses cannot replace a newly selected source.

API calculations save immediately for human review. Changed inputs create another
run. No purchase, dispatch or budget approval happens. Source transfers remain
assumptions; the full operating allowance is charged and missing demand remains
excluded rather than zero. Engine/solver versions and objective are displayed.

`mode=example` is an explicitly isolated fixed synthetic browser preview. Its
catalog matches the canonical IDs and evidence; edited inputs require API solving.

Checks: typecheck, `test:investments`, all frontend suites and production webpack
build. See the repository README for database startup and migrations.
