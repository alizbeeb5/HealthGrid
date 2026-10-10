# Seven-day forecast frontend

`/forecasts` loads the published forecast API by default. Hospital and service
selectors use the Feature 1 API catalog. Requests are uncached and race guarded;
errors never substitute examples. Refresh reloads both catalog and forecast.

`/forecasts?mode=example` explicitly uses the backend-owned shared JSON examples.
The bundled files are synchronized by `scripts/sync-forecast-fixtures.mjs` during
predev/prebuild. B shows seven forecast days and the first supplied gap on day 3:
8 expected places, 5 modeled places, gap 3. C demonstrates insufficient history;
no shared A forecast example is published, so selecting A shows a visible error.

Generated OpenAPI types define the wire response. `demo-client.ts` maps fields for
presentation only; quantities, bounds, gaps, alerts and validation come from Python.
No forecasting, resource capacity or gap arithmetic runs in the frontend. Gap
ranges and exact observation timestamps are absent from the contract and are not
invented. Null history quantities display as unknown and break chart lines.

Evidence exposes the generated timestamp, latest history date, provenance, quality,
profile and held-out validation. Synthetic source labels stay visible. Capacity and
demand share simultaneous-service-place units; modeled capacity is not confirmed
spare admission capacity, and ranges are not calibrated confidence intervals.
Forecasts use separate daily history, so current resource updates do not rewrite it.

Agreement: `docs/feature-4-forecast-contract.md`. The similarly named incident
contract describes a different milestone. Backend owns the endpoint/engine adapter,
history imports, schemas and canonical fixture expectations. The pulled endpoint
calls a one-argument ForecastInput interface while the engine exposes a three-
argument daily-record interface; API execution requires the backend owner to align
them. This frontend preserves the published endpoint and visible failure state.

Checks: `npm run typecheck --prefix apps/web` and
`npm run test:forecasting --prefix apps/web`. Browser/chart validation remains with
the user; no browser tests or production build were run for this change.
