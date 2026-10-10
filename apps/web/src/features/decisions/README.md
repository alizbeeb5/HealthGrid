# Connected decision tracking

`/decisions` loads the API decision board. Saved allocation/investment panels link
here with source IDs. Enter an owner, rationale, UTC deadline and demo actor to
save a draft, submit it and record review. Generated backend types define requests;
the server owns transitions, prerequisites, concurrency and idempotency.

After approval, record the decision as started. Pending actions can start or become
blocked. Actions in progress can become blocked or reported completed. Blocked
work must resume before completion. Investment work requires the exact completed
allocation decision, and commissioning requires reported repair completion.
Terminal reports use appended corrections, retaining previous reported values.
Optional actual costs stay unknown when blank and separate from proposal costs.

The screen keeps approval, reported execution and outcome evidence distinct. It
never writes hospital inventory through a decision event. Use the facility links
to append real resource reports; then choose an explicit observation window and
capture a review. The server controls capture time and evaluates the frozen profile.
Owner deadlines do not replace expected modeled dates. Early evidence can show a
fresh observation but cannot claim target achievement. Later evidence does not
establish on-time completion or causation. Limited service remains not comparable;
reported unavailable service preserves modeled zero and missing resource warnings.

Decision and review URLs reopen API records. Review history is returned by
`GET /api/v1/decisions/{decision_id}/reviews`, newest first, and never re-evaluated.
The review view retains captured status/version, resource and receipt times,
profile, units, coverage and evaluation versions. Null never becomes zero.

Writes are sent once. Field errors, duplicate-source errors and stale-version
conflicts remain visible; failures never silently fall back to browser examples.
Older requests cannot replace a newly selected workspace. Actor identities are
explicitly self-reported demo names until authentication exists.

`mode=example` remains an isolated synthetic browser workflow with fixed evidence
samples. It does not call decision or outcome endpoints. No AI or OR-Tools call is
needed for decision events or evidence comparisons.

Checks: TypeScript, `npm run test:decisions --prefix apps/web`, the full frontend
suites and production webpack build. Backend tests cover real proposal -> decision
-> review persistence and immutable review history. Live PostgreSQL/browser review
are separate from these SQLite API and rendered-component checks.
