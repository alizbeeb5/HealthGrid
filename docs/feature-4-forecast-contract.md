# Feature 4: Capacity prediction and preventive alerts

Status: backend schemas, history storage/import and the endpoint are implemented.
The endpoint returns HTTP 500 until the forecasting engine is merged. The `/forecasts`
screen, engine and eight-week dataset are pending.

Note: `feature-4-contract.md` (emergency intake and incident baseline) describes a
different milestone. The team should decide its order and renumber one of them.

## Outcome

Predict modeled service capacity and expected demand for the next seven days and
highlight where demand may exceed capacity. Demo: Hospital B supports 5 places;
demand is forecast to reach 8 in three days, so HealthGrid flags a possible gap of 3.
Both measures are simultaneous service places. Data is synthetic. A gap is a model
output, not a calibrated shortage probability. Response choices (OR-Tools) come later.

## API

`GET /api/v1/forecasts/facilities/{facility_id}?service_id=emergency-care`

- 200 `FacilityForecastResponse`. Insufficient history is a 200 with
  `status: insufficient_history`, no forecast and no alerts.
- 404 `facility_not_found`; 422 `invalid_request` for a missing/malformed
  `service_id` or a service the facility does not offer (Feature 1 error envelope).
- 500 for configuration or engine failures; never a silent zero or empty forecast.

Pydantic definitions: `apps/api/app/modules/forecasting/schemas.py` (backend-owned,
extra fields forbidden). Frontend generates types from `contracts/openapi.json`.

`FacilityForecastResponse`: `facility_id`, `service_id`, `generated_at` (server time),
`horizon_days` (7), `capacity_unit` (`simultaneous_service_place`), `profile_version`
(null only when `not_configured`), `status` (`forecasted` / `insufficient_history` /
`not_configured`), `history`, `forecast`, `alerts`, `validation` (null unless forecasted).

- `HistoryDay`: `date`, `capacity` (int or null when a required resource is missing
  that day), `demand` (int or null with no record), `sources` (sorted labels),
  `data_quality` (lowest quality among that day's records, or null).
- `ForecastDay`: `date`, `predicted_capacity`, `predicted_demand`, `capacity_lower`,
  `capacity_upper`, `demand_lower`, `demand_upper`, `expected_gap`. Lower <= predicted
  <= upper; `expected_gap = max(0, predicted_demand - predicted_capacity)`.
- `ForecastAlert`: `date`, `code` (`predicted_gap`), `expected_gap`, `message`. Exactly
  one alert per forecast day with a positive gap, ordered by date.
- `ForecastValidation`: `method`, `holdout_days`, `evaluated_from`, `evaluated_to`,
  `capacity_mae`, `demand_mae` (mean absolute error on withheld historical days).

Enforced: 7 consecutive forecast days starting after the last history day, ascending
unique dates, and matching alerts. The backend rejects engine output that breaks these.

## Historical data

Stored in `daily_resource_records` and `daily_service_demand` (migration
`0002_daily_history`), separate from Feature 1 observations. Insert-only: an
identical re-import is skipped, a different value for an existing day rejects the
whole import, and nothing is overwritten. Forecasts are never stored.

Import format `DailyHistoryImport`: `resource_records` and `demand_records`.
- `DailyResourceRecord`: `facility_id`, `resource_id`, `date`, `available_quantity`,
  `unit`, `source`, `data_quality` (`reported` / `estimated`).
- `DailyDemandRecord`: `facility_id`, `service_id`, `date`, `peak_required_places`
  (integer), `source`, `data_quality`.

Validated: known facility, applicable resource, catalog unit, whole numbers where
fractions are not allowed, offered service, no future dates, no duplicates. Missing
days have no record; they stay unknown and are never imported as zero.

`python apps/api/scripts/import_daily_history.py [path]` (default
`data/synthetic/feature-4/daily-history.json`), after migrating and seeding Feature 1.

## Engine interface (forecasting/data teammate)

```python
# apps/api/app/engines/forecasting.py
forecast_service_capacity(inputs: ForecastInput) -> FacilityForecastResponse
```

`ForecastInput`: `facility_id`, `service_id`, `service_status`, `requirement`
(Feature 2 `ServiceRequirement`, or null), `resource_records` (this facility, by date
then resource), `demand_records` (this facility and service, by date), `generated_at`,
`horizon_days` (7). Pure: no database, HTTP, clock or AI calls. The engine computes
historical capacity from the requirement profile, forecasts capacity and demand
separately (weekly seasonal baseline first), validates on withheld days, and decides
the insufficient-history threshold. Reject incompatible data with `ValueError`.

## Examples and ownership

`contracts/examples/feature-4/`: `DEMO-B.forecast.response.json`,
`insufficient-history.forecast.response.json`, `daily-history.import.json`,
`service-not-offered.response.json`. The two forecast responses currently hold
schema-valid illustrative numbers for the B demo. The forecasting teammate owns
calculations and example expectations: replace them with the engine's output for the
dataset at the fixture clock `2026-10-10T09:00:00Z`. `test_forecast_api.py` then
requires the live endpoint to match `DEMO-B.forecast.response.json` exactly.

Backend owns schemas, storage, import, endpoint and OpenAPI; frontend owns the
`/forecasts` screen; the forecasting teammate owns the engine, dataset and expectations.
Field changes go through the backend owner and update schemas, examples and types together.
