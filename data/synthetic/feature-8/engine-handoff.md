# Outcome numerical handoff

Canonical `OutcomeEvaluationInput` and `OutcomeEvaluationResult` now exist in
`modules/decisions/schemas.py`. The public `evaluate_outcome(input) -> result` binding
is connected to captured API reviews and independent backend verification. Numerical
fixtures remain separate from public HTTP contracts; production imports no test types.
API review history returns saved records without rerunning calculations.

Owner files: `apps/api/app/engines/outcomes.py`, `apps/api/tests/outcome_fixture_types.py`,
`apps/api/tests/test_outcome_engine.py`, `apps/api/tests/test_outcome_evidence_api.py`
and `data/synthetic/feature-8/`. Other modules are unchanged.

## Internal input to map

`_evaluate_outcome(data)` accepts the private `_Problem` structural interface:

- `service_id`, `capacity_unit=simultaneous_service_place`, `expected_profile_version`.
- `requirement`: frozen `ServiceRequirement` or null for an explicitly not-comparable review.
- `baseline_captured_at`, `expected_at`, `captured_at`, `observation_window_starts_at`:
  aware UTC timestamps, supplied by the backend. Window must be within baseline and
  capture; expected date cannot precede the baseline.
- `expectations`: unique facility rows containing `facility_id`, `expected_capacity`
  and `required_service_places`. Counts are nonnegative integers or null. Include
  inherited excluded facilities with null expectations so coverage stays visible.
- `snapshots`: captured `FacilitySnapshotResponse` records, each `as_of` exactly
  equal to capture. Omitted facilities remain explicit missing rows; unknown or
  duplicate facility IDs are rejected.

No decision approval/completion state or execution claims enter the calculation.
Backend records those alongside the result. Use the source modeled expected date,
not the decision owner deadline. Reopening a saved review must not rerun this kernel.

## Internal output to map

`_KernelResult` has engine version `outcome-review-v1`, service/unit/profile,
capture/expected/window timestamps, signed `seconds_from_expected_at`, rows and
coverage. It contains no overall success status or invented network percentage.

Each `_Row` contains facility ID, nullable `expected_capacity`, `observed_capacity`,
`capacity_difference` and classification:

- `at_or_above_expected` / `below_expected`: target date reached and comparable
  modeled evidence; difference is observed minus expected.
- `too_early`: target assessment withheld; observable capacity may still be shown.
- `insufficient_evidence`: required follow-up evidence missing, stale, outside
  window, future/inconsistent, or service restricted without a numerical limit.
- `not_comparable`: expected capacity/profile/service unavailable for comparison.
  This differs from the reported service status `unavailable`, which yields zero.

Unknown comparison reasons take precedence over timing when there is no valid
expected/profile/service pair. Only comparable rows have a signed difference.
Any capture after the expected date explicitly states that it cannot establish
on-time completion. Nothing asserts causality, clinical outcomes or verified execution.

Rows also retain sorted reason codes/bottleneck IDs, frozen planned demand,
nullable `expected_unmet_against_planned_demand` / `observed_unmet_against_planned_demand`,
complete per-required-resource `_Evidence` and the original capacity result model.
Evidence retains quantity/unit/observation ID/observed/received times plus computed
current/stale/unknown and reasons. Missing receipt timestamps make a resource
unusable as follow-up evidence; delayed but pre-capture receipts are allowed.
All required resource reports must be within the inclusive follow-up window and
at most `stale_after_hours` old; exact 24 hours is current for the demo. Freshness
is recalculated from times rather than trusting cached resource labels.

Reported unavailable service is current captured service evidence: capacity zero
remains comparable even if resource reports are missing; their reasons stay visible.
Operating services require every profile resource. Reported limited service stays
unknown. The capture does not reconstruct historical service operating status.

`_Coverage`: all expected facility IDs, comparable IDs, excluded IDs and complete
flag. Rows are always sorted and retained, including null expectations. Empty scope
is not complete. A/B may be comparable while C remains excluded; do not call those
rows a complete national comparison.

## Errors and integration

`OutcomeValidationError(ValueError)` has a clear field/context message for invalid
or incompatible inputs: IDs, counts, UTC timing, mismatched clocks/profile/unit,
duplicate rows, invalid resource quantities. Missing or unusable evidence produces
classified rows rather than numerical zero. Backend maps request errors to its
normal field-level envelope and treats corrupted frozen internal data visibly.

The Feature 1 integration test proves new observations change only a new capture
and leave earlier captured inputs/results unchanged. Full decision-review persistence, source conversion and POST/GET/history review
checks now pass against the real engine. Approval/actions must never insert
observations as part of invoking this engine.


## Frontend preview check

The pushed decisions frontend includes allocation/investment examples for missing
evidence, supported capacity, below-expected capacity and early reviews. Eight
numerical fixture checks reproduce their values, signed differences and comparable
facility coverage using the Python kernel. Frontend transport/rendering tests and production build checks pass; automated
browser interaction remains unverified. The display model omits receipt timestamps; these checks explicitly
assume fictional receipts to verify only the arithmetic and classification. Live
backend capture must supply actual recorded_at values, frozen service status and
source profile; the display is not a canonical evidence payload. Decision writes and live review capture are connected using generated types.


## Canonical result mapping

The public input supplies frozen expected facilities and separately inherited
exclusions. Baseline/window validation happens in the decision service; the kernel
never invents a source baseline. Aware input window/expected/deadline times are
normalized to UTC internally. The deadline/status do not affect target comparison.

Public results use `facilities`, `classification`, `observed_capacity`, `observed`
(capacity-engine result), `evidence`, `unmet_against_planned_demand`, timing and signed
capture offset minutes. Public `observed_capacity` and difference are reserved for
comparable rows. A fresh early estimate remains available in `observed`, displayed
separately from a target verdict. Fresh limited services are `not_comparable`.
Resource evidence retains its original captured data_status and an independently
calculated missing/outside_window/stale/fresh evidence_status. Receipts remain frozen
in review.snapshots. Reported unavailable status yields explicit zero and preserves
missing resource evidence warnings. Backend independent verification checks every
classification and evidence record, including missing resource definitions.
