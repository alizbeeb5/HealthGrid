# Feature 4 synthetic forecasting data

All hospitals and histories are fictional. Sources say fictional-weekly-demo-v1;
import quality is estimated. These are daily peak required simultaneous places,
not admissions/day. Eight weeks span 2026-08-15 through 2026-10-09.

Run `python data/synthetic/feature-4/generate_demo.py` to deterministically regenerate
standalone daily-snapshot fixtures, expected engine outputs, the combined
DailyHistoryImport dataset daily-history.json, and canonical API examples.
This command never modifies a database. Then sync the frontend example bundle.

Import with `python apps/api/scripts/import_daily_history.py`, after migrations and
Feature 1 seeding. Missing resources are omitted, never zero-filled. Daily demand
records preserve historical service_status. Synthetic rows are labeled estimated.
The import is insert-only: identical data is skipped; conflicting data is rejected.

The API engine boundary is forecast_service_capacity(ForecastInput), returning the
backend-owned FacilityForecastResponse. forecast_daily_history(records, profile,
generated_at) remains the pure internal seasonal model. It repeats the last weekly
baseline, validates on 14 held-out days, and returns empirical error bands. The
bands are uncalibrated, not 90% coverage guarantees or shortage probabilities.

At 2026-10-10T09:00:00Z: Demo B predicts capacity 5 and a first gap of 3 on October
12; capacity and demand MAE are each 1.5. Demo A returns insufficient_history due
to missing monitors/restricted service. Demo C retains its historic operating days
and later outage zeros; positive demand still produces gap alerts.

The live API uses completed UTC dates only. Today's aggregate is excluded. Missing
or aged history returns insufficient_history with history visible and no forecasts.
The fixed histories are not automatically shifted into the present. A fresh daily
record is required as time advances. Reported observations are never overwritten.

Checks: pytest apps/api/tests/test_forecasting_engine.py
apps/api/tests/test_forecast_integration.py apps/api/tests/test_migrations.py.
No OpenAI calls, frontend builds or browser checks are needed.
