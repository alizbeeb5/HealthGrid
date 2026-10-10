# Feature 8 — Decision tracking and outcome review

Status: backend implemented — `modules/decisions` (schemas, pure `transitions.py`
state machine, router, service, repository, models), migration `0007_decisions`,
all six endpoints (registered in `app/routes.py`), OpenAPI and examples in
`contracts/examples/feature-8/`. Review capture returns HTTP 500 until
`engines/outcomes.py` provides `evaluate_outcome`; decision tracking works now.

Backend interface decisions for the outcome-engine owner (`decisions/schemas.py`):
- `OutcomeEvaluationInput`: `service_id`, `capacity_unit`, frozen `requirement`,
  `expected_at`, `target_completion_at` (separate), `observation_window_starts_at`,
  `captured_at`, `stale_after_hours`, `decision_status`, `facilities` (frozen
  required places, `capacity_before`, `expected_capacity` and the snapshot captured
  at review time) and the source's `excluded_facilities`.
- `OutcomeEvaluationResult`: `engine_version`, `timing` (`too_early` /
  `on_or_after_expected`), signed `captured_offset_minutes`, per-facility
  `FacilityOutcome` (classification, expected/observed capacity, difference, the
  capacity-engine result, per-resource `evidence`, reasons and
  `unmet_against_planned_demand`), `coverage` and reasons.
- Evidence rule (`decisions.service.evidence_status`): `missing` without an
  observation; `outside_window` before the window or after capture; `stale` when the
  captured report is not current; otherwise `fresh`. A row is comparable only when
  the review is on/after the expected date and every required resource is fresh;
  observed capacity must equal the capacity engine on the captured snapshot. A
  limited reported service is therefore `not_comparable` (capacity not quantified).
- The backend re-checks rows, expected values, evidence, timing, comparability and
  observed capacity before saving; a failing evaluation is a 500 and is never saved.
- Decision record: frozen `expectation` (expected date, facilities, profile,
  proposed costs split from optional actual costs), generated `actions`
  (`ACT-<route_id>` / `ACT-<candidate_id>`, prerequisites mapped) and the event
  timeline. `start` and `occurred_at` are explicit; future times beyond the 5-minute
  skew are 422. Correct a completed action with `correct_action_report`.
- Errors: shared envelope with `invalid_request` (422), `source_run_not_found`,
  `decision_not_found`, `review_not_found` (404), `invalid_transition`,
  `prerequisite_not_met`, `duplicate_source_decision`, `version_conflict`,
  `idempotency_conflict` (409); `current_version` / `existing_decision_id` when set.
- Examples come from the live API with the real allocation and investment engines
  and a contract-faithful reference evaluator. Event/decision IDs are generated, so
  tests compare examples after normalizing ID values.

Features 6 and 7 provide saved allocation/investment
proposals; this milestone records human choices, reported execution and follow-up
evidence. It does not change or rerun those proposals.

## Purpose and first scope

Answer “Which plan did we choose, who is responsible, and what happened afterward?”
Create a decision from a validated saved proposal, record review, track its action
items and compare newly reported resources with the frozen expected capacity.
Start with the same emergency-care transfer and investment demonstration.

Approval is a recorded human decision. Completion is a reported execution state.
Outcome review is a separate comparison backed by observations; it does not prove
that the chosen action caused a change or delivered clinical benefits.

The existing application has no authentication. Actor names and persona views in
this milestone are explicitly self-reported demo identities, not enforced ministry
permissions or verified signatures. Keep this visible in records and API metadata.
Actual dispatch, purchasing, notifications and automatic model retraining are not
part of this feature. No new OpenAI or OR-Tools call is required.

## User workflow

1. Open a saved allocation/investment proposal and select “Record a decision.”
2. Review its frozen actions, cost assumptions, expected capacity and remaining
   gaps. Supply the decision owner, rationale and target completion timestamp.
3. Submit for review; record approval or rejection with a reviewer and explanation.
4. Report action-item progress, actual completion times, optional actual costs and
   evidence notes. Blockers and prerequisites remain visible.
5. Submit hospital resource updates through Feature 1; do not create inventory by
   marking a task completed.
6. Capture a follow-up review from those reports. Compare expected and observed
   modeled capacity, display missing/stale data and retain the evidence snapshot.

## State and action rules

Decision states use existing product vocabulary:

```text
draft -> pending_review -> approved -> in_progress -> completed
                       -> rejected
draft/pending_review/approved/in_progress -> cancelled
```

Only draft details can be edited. Submission freezes owner, rationale, target date
and source selection. Review and cancellation require an explanation. Rejected,
cancelled and completed decisions are terminal; reconsideration creates a new
decision linked by `supersedes_decision_id` and preserves the old timeline.

Action states: `pending`, `in_progress`, `blocked`, `completed`, `cancelled`.
Starting work requires decision approval. Completion requires a reported timestamp
and evidence note; actual cost is optional and unknown is not zero. A decision can
be marked completed only after every required action is reported completed.
Completed prerequisite actions are required before dependent work starts.
Blocked work leaves the overall decision in progress and exposes its blocker.
Cancelling a decision cancels unfinished actions but preserves completed ones.
Terminal action records are not overwritten; corrections append a correction event
with a reason while preserving earlier values and the reported/verified distinction.

Allocation decisions generate one action per saved transfer. Investment decisions
generate one action per selected project, including prerequisite-only projects.
For an investment source that assumes transfers, require a
`prerequisite_decision_id` referring to the exact source allocation run. That
decision must be reported completed before investment actions can start. Display
that prerequisite explicitly; do not duplicate transfer execution inside the
investment decision. If the source has no transfers, no prerequisite is needed.

Select only saved results with `validation_passed=true` and a proposed summary.
Support `no_improvement` results with an explicit rationale for choosing no action;
they have zero actions and can complete after approval with a completion note.
Sources with no solution or missing inputs cannot become executable decisions.
Allow at most one non-rejected/non-cancelled decision per exact source run to avoid
duplicated execution tracking. Completed records also block duplicate selection.

## Shared interfaces before splitting

Backend/data owns Pydantic schemas, state transitions, migrations and examples.
The outcome-engine owner reviews numerical inputs/results. Frontend uses the same
examples/generated types. Use snake_case, existing IDs, UTC timestamps, integer
USD cents and `simultaneous_service_place`; no independent UI calculations.

Add a `decisions` domain module and register these proposed endpoints:

```text
POST /api/v1/decisions
GET  /api/v1/decisions
GET  /api/v1/decisions/{decision_id}
POST /api/v1/decisions/{decision_id}/events
POST /api/v1/decisions/{decision_id}/reviews
GET  /api/v1/decisions/{decision_id}/reviews/{review_id}
```

`DecisionCreateRequest`: `source_type` (`allocation`/`investment`), `source_run_id`,
`title`, `owner_name`, `rationale`, `target_completion_at`, `actor_name`, nullable
`prerequisite_decision_id` and nullable `supersedes_decision_id`.

`DecisionRecord`: decision/source/incident/revision/baseline IDs, `status`,
`version`, owner/rationale/target timestamps, `identity_mode=demo_self_reported`,
immutable source evidence and expectation snapshot, action items, prerequisite
references, and append-only event timeline. Preserve proposed costs separately
from optional reported actual costs. Do not compare project operating allowances
with partial payments as though they were the same accounting measure.

`DecisionEventRequest`: `event_type`, `expected_version`, `request_id` (idempotency
key), `actor_name`, `note`, plus a typed payload for the event. Supported commands:
`edit_draft`, `submit`, `approve`, `reject`, `start`, `update_action`, `complete`,
`cancel`, `correct_action_report`. Define a discriminated payload for each rather
than an unrestricted dictionary. Record server `recorded_at` separately from
human-reported `occurred_at`; reject future execution timestamps. Corrections do
not bypass legal state transitions or rewrite the frozen source proposal.

Use transactional version checks: outdated version is 409; repeating the same
request ID with identical payload returns its saved result; reusing it with a
different payload is 409. Invalid transitions/prerequisites are 409; malformed
fields are 422; missing sources/decisions are 404. Prevent duplicate source
decisions transactionally, not only through a frontend check.

`OutcomeReviewRequest`: `actor_name`, `note`, `request_id` and
`observation_window_starts_at`. Capture time is server-controlled, not a client
claim to reconstruct arbitrary historical state. Window start must be no earlier
than the frozen source baseline capture and no later than capture time.

`OutcomeReview`: review/decision/source IDs, `captured_at`, window, decision
status/version at capture, immutable reported snapshots and observation IDs,
frozen requirement profile, expected capacities and dates, observed modeled
capacities, signed `capacity_difference`, fresh/missing/stale evidence reasons,
coverage, and evaluation engine/schema versions. Server capture freezes the
currently reported service status; it does not claim a historical status.

Commit examples under `contracts/examples/feature-8/` before integration: draft,
approved, blocked, completed, supported outcome, insufficient evidence, and
transition/conflict errors. Regenerate OpenAPI and frontend types when implemented.

## Follow-up comparison agreement

Use one pure interface:

```python
evaluate_outcome(input: OutcomeEvaluationInput) -> OutcomeEvaluationResult
```

Inputs are the frozen proposal expectations, review timing, newly captured facility
snapshots and the same source requirement profile. Backend obtains snapshots
through public services; the engine has no database, HTTP, clock or AI calls.

- Investment expected date is its saved `evaluation_at`; allocation expected date
  is incident start plus its saved planning horizon. Preserve the decision's target
  completion date separately; it does not silently replace the model's expected date.
- Show exact observed capture/date offsets. Reviews before expected date are
  `too_early` for a target assessment. Later reviews do not prove the target was
  achieved on time.
- Required observations must fall inside the chosen follow-up window, not after
  capture, and satisfy the existing freshness rule relative to capture. Old
  baseline evidence outside the window cannot establish a follow-up outcome.
- Reuse the existing capacity engine and frozen source profile. Unknown or stale
  evidence remains unknown. Distinguish confirmed zero/unavailable from missing.
- For comparable facility rows, classify `at_or_above_expected` or
  `below_expected`, with difference = observed minus expected. Otherwise use
  `insufficient_evidence`, `too_early` or `not_comparable` with reasons.
- Required service demand is the frozen planning assumption. Any displayed
  follow-up unmet-demand calculation must say “against planned demand”; it is not
  newly measured patient demand or actual patient outcomes.
- Do not report a national success percentage from incomplete facilities. Expose
  comparable/excluded coverage and facility results separately. Progress completion
  and outcome evidence remain independent dimensions.
- Reopening returns the captured review. A later report creates a new review, not
  a rewrite. No observations are inserted by approval or action completion.

## Three focused teammate tasks

### Task 1 — Frontend: Decision board, timeline and follow-up panel

Own `apps/web/src/features/decisions/` and a `/decisions` page. Add “Record a
decision” to saved allocation/investment results. Build owner/rationale inputs,
status filters, due-date/blocked indicators, event timeline and action progress
forms. Show prerequisites, reported identity and outcome evidence separately.
Link to Feature 1 for report updates; capture/reopen a follow-up review.

Done: the demo can move from proposal to review, reported completion and a visible
capacity comparison. Use shared mocks first; user performs web review. No frontend
tests/builds/browser checks unless requested.

### Task 2 — Backend/data: Decision persistence and legal transitions

Own `modules/decisions/{schemas,router,service,repository,models}.py`, coordinated
migrations and endpoint registration. Publish shared contracts/examples; freeze
source expectations, generate action items, enforce prerequisites/state rules,
implement concurrency/idempotency, and capture immutable follow-up snapshots via
existing public services. Regenerate OpenAPI and coordinate frontend types.

Done: approval cannot execute inventory updates; invalid/double transitions and
duplicate source selection fail consistently; saved decisions/reviews reopen
unchanged. Backend tests cover state transitions, prerequisites, transactions,
retries and persistence. Outcome engine integration uses the same shared types.

### Task 3 — Data/evaluation: Outcome engine and end-to-end evidence fixtures

Own `engines/outcomes.py`, numerical evaluation tests and
`data/synthetic/feature-8/`. Agree typed input/output with teammate 2, reuse the
capacity engine, implement timing/evidence/comparison rules and supply matching
expected result fixtures. No new forecasting, optimization or AI provider work.

Done: tests distinguish reported completion from supported capacity, handle partial
and stale/missing reports, early/later reviews, preserve confirmed zero, and avoid
mixing observed capacity with invented demand. Include a backend integration case
that proves updating reports changes only a new review, never previous evidence.

## Demonstration and build order

Record and complete the Feature 6 transfer decision. Create the Feature 7 repair
and commissioning decision with that allocation prerequisite. Approve it, report
repair completion and commissioning completion, and show B's expected capacity 8.

Capture a review without fresh required reports: insufficient evidence even though
the tasks are reported completed. Then append fresh Feature 1 reports for B: 8
monitors, 18 beds and 9 nurses, with operating status. At a valid follow-up time,
the frozen profile yields observed capacity 8 versus expected 8. A separate fixture
with only 6 working monitors yields capacity 6 and difference -2. Report fresh A
resources as well before displaying a complete network comparison. All data is
fictional; neither comparison claims causal or clinical validation.

Build order: shared state table/schemas/examples -> backend state workflow, UI
against mocks, pure outcome evaluation -> connect the demonstration -> backend
and numerical verification plus user web review. This completes the mindmap loop:
understand -> predict -> respond -> invest -> record -> review evidence.
