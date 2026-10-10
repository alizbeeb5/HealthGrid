# Fictional capacity and demand forecasting: Task 3

This folder implements the forecasting assignment in the current user brief.
The repository's `docs/feature-4-contract.md` still describes emergency intake;
coordinate that shared document with its owner. This task does not alter it or
backend-owned Pydantic schemas, persistence, routes or frontend components.

## Demo history and expected cases

All 168 records are manually designed synthetic daily data: 56 consecutive days
per facility, 2026-08-16 through 2026-10-10. Coordinates remain illustrative.
`generate_demo.py` deterministically rebuilds the three history JSON files from
the Feature 1 fixtures; it never connects to a database. No patient information
or clinical staffing standard is represented.

Each record contains `date`, a full Feature 1 `snapshot`, `demand`, `source`,
`data_quality`, `capacity_unit` and `profile_version`. This is an engine input
fixture, not a proposed database table or alternate HTTP request. Every daily
resource quantity and observation ID is distinct from live reports; importing
these records must not overwrite Feature 1 observations. Demand is the fictional
**daily peak required simultaneous service places**, not admissions/day,
occupancy or a sum of hourly counts. Its unit is the same simultaneous-place unit
as modeled capacity. The snapshot represents that day's synthetic resource
report; capacity is recomputed through the existing Feature 2 engine.

Daily snapshots have an explicit 23:59 UTC as_of and observations at 08:30 UTC.
The fixed generation clock is **2026-10-10T23:59:59Z**, after those complete
fictional daily records. Predictions cover October 11–17. At a live daytime
request, the backend should use complete preceding days and choose an agreed
forecast-origin policy; the present engine requires the final history date to
match the supplied UTC generation date. Do not silently shift dates or fabricate
an incomplete daily peak to satisfy that rule; coordinate any policy change.

| Facility | Expected result |
| --- | --- |
| DEMO-A | Reject as inadequate: monitors are missing in the last two weeks; the final week's service restriction is unquantified. Unknown is not zero. |
| DEMO-B | Forecasted: capacity 5 each day; demand 4, 5, 8, 7, 6, 5, 5. First gap October 13: demand 8 minus capacity 5 = 3. |
| DEMO-C | Forecasted: recent service status unavailable gives modeled capacity zero. Demand remains positive; alerts describe possible gaps under continued unavailability. |

`DEMO-B.expected-engine-result.json` and `DEMO-C.expected-engine-result.json`
freeze complete outputs, including history provenance and validation errors.
They are internal engine expectations; teammate 2 owns the HTTP examples and
mapping to the final response schemas. Timestamps in these internal serialized
outputs may use `+00:00`; the API must return UTC with `Z` consistently with the
existing contracts.

## Pure Python boundary for teammate 2

Import from `app.engines.forecasting`:

```python
forecast_service_capacity(
    records: Sequence[DailyHistoryRecord],
    requirement: ServiceRequirement,
    generated_at: datetime,
) -> ForecastResult
```

`DailyHistoryRecord` is a frozen dataclass containing the input fields listed
above; snapshot is a validated `FacilitySnapshotResponse`, date is `datetime.date`,
demand is a nonnegative integer or None, and generated_at is explicit and aware.
The same profile version and unit must apply across all supplied records. Use
one facility and service per call. The backend validates/loads the profile
against its catalog, builds daily snapshots with correct freshness statuses,
then supplies the existing `ServiceRequirement` instance.

The engine calls `calculate_service_capacity` for every historical day. It
performs no I/O, database writes, HTTP, AI calls or implicit clock reads, and
preserves all supplied observations. Missing/stale or restricted-day capacities
remain None in history. A service unavailable on a reported day yields zero
according to the existing capacity contract.

`ForecastResult` has the agreed top-level names: facility_id, service_id,
generated_at, horizon_days, capacity_unit, profile_version, status, history,
forecast, alerts and validation. The day fields match the user brief. Additional
nested history/validation details are engine data, subject to backend schema
agreement; these dataclasses do not replace Pydantic/OpenAPI contracts.

The proposed successful status is `forecasted`. Invalid/inadequate inputs raise
`ForecastInputError` with an explanation; teammate 2 decides its agreed wire
status and error mapping, including the frontend's insufficient-history state.
Do not catch failures and publish an empty successful forecast or zero estimate.
Configuration/model errors from the capacity engine must also fail visibly.

## Baseline, validation and uncertainty

Use at least 56 consecutive unique dates and at least 42 days where both measures
are known. Input ordering is normalized without modifying records. Train on all
but the final 14 days, repeating the last seven training values to forecast those
withheld days. Evaluate capacity and demand separately using mean absolute error
in simultaneous places. Refit the final prediction to the last seven supplied
days and produce a seven-day horizon. The baseline is seasonal naive; it does not
learn a trend or use future observations during evaluation.

The training baseline's final seven days, all withheld days and the final
forecasting baseline must be complete. Earlier missing values remain visible and
are not imputed. Invalid demand, dates, source/quality, facility/service, units,
profile versions, and stale history are rejected. The backend must retain the
historical profile content/version; silently recomputing an old record with a
changed profile bearing the same version is outside this demo's compatibility
assumptions.

Capacity and demand ranges use their own nearest-rank 90th percentile of absolute
held-out errors as symmetric radii, clipping lower bounds at zero. These are
**uncalibrated empirical error bands**, not 90% coverage guarantees or shortage
probabilities. They can collapse to zero width for a perfectly repeated synthetic
series. Abrupt service changes, trends, missing reports and eight weeks of invented
data limit applicability; synthetic accuracy is not evidence of real accuracy.

For Hospital B both MAEs are **1.5 places**, both error radii are **2**. On October
13 capacity is 5 with range 3–7; demand is 8 with range 6–10; expected gap is 3.
`expected_gap = max(0, predicted_demand - predicted_capacity)` uses point estimates,
not bounds or a probability. Every positive gap gets a dated alert. Alerts support
review; they authorize no transfer, staffing change or resource allocation.
Hospital C's abrupt outage produces capacity MAE 4, exposing the baseline's
failure to anticipate that change rather than hiding it.

## Verification

Run focused checks from the repository root in the selected environment:

```bash
.venv/bin/python -m pytest apps/api/tests/test_forecasting_engine.py -q
.venv/bin/python data/synthetic/feature-4/generate_demo.py
```

The tests verify the three eight-week histories, frozen outputs, first upcoming
gap, separate validation errors, missing/stale data rejection, units/profile
compatibility, exact dates, zero capacity, unmodified observations and held-out
validation that does not train on future targets. No database or provider is used.
The user requested Python 3.14 for this workspace; repository guidance still
specifies Python 3.12, so report the interpreter used for checks.

Backend storage/import and HTTP integration remain teammate 2's responsibility;
forecast UI remains teammate 1's. Neither is implied by these engine tests.
