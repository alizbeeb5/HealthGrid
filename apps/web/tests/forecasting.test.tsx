import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { forecastCatalog, getForecastExample, getForecast, type ForecastPreview } from "../src/features/forecasting/demo-client";
import { createForecastLoader, type ForecastState } from "../src/features/forecasting/forecast-loader";
import { ForecastAlert, ForecastEvidence, ForecastTable, InsufficientHistory } from "../src/features/forecasting/forecast-results";
import { chartPoints, forecastDate } from "../src/features/forecasting/presentation";
import facilities from "../src/lib/api/facilities-fixtures.generated.json";
import capacity from "../src/lib/api/capacity-fixtures.generated.json";

const text = (html: string) => html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test("preview hospital/service IDs reuse the shared catalog; missing selections never substitute another hospital", async () => {
  const catalog = forecastCatalog();
  assert.deepEqual(catalog.map((item) => item.facility), facilities.list.items);
  assert.equal(catalog.find((item) => item.facility.facility_id === "DEMO-B")?.services[0].service_id, "emergency-care");
  await assert.rejects(getForecastExample("missing", "emergency-care"), /No forecast preview/);
  await assert.rejects(getForecastExample("DEMO-B", "missing"), /No forecast preview/);
  const data = await getForecastExample("DEMO-B", "emergency-care");
  assert.equal(data.baseline_capacity, capacity.responses["DEMO-B"].services[0].estimated_capacity);
  data.forecast[0].demand = 99;
  assert.equal((await getForecastExample("DEMO-B", "emergency-care")).forecast[0].demand, 4);
});

test("B shows seven future rows and highlights the first central gap on day three", async () => {
  const data = await getForecastExample("DEMO-B", "emergency-care");
  assert.equal(data.forecast.length, 7);
  assert.equal(data.history.length, 56);
  assert.deepEqual(data.first_gap, { date: "2026-10-12", day_number: 3, capacity: 5, demand: 8, gap: 3 });
  assert.equal(data.forecast.find((point) => point.gap > 0)?.date, data.first_gap?.date);
  const alert = text(renderToStaticMarkup(<ForecastAlert data={data} />));
  assert.match(alert, /First expected gap: day 3/);
  assert.match(alert, /8 expected places − 5 modeled places → possible gap of 3 places/);
  assert.match(alert, /not a confirmed shortage/);
  const table = renderToStaticMarkup(<ForecastTable data={data} />);
  assert.equal((table.match(/<tr/g) ?? []).length, 8);
  assert.equal((table.match(/First expected gap/g) ?? []).length, 1);
  assert.match(table, /2026-10-12/);
  assert.match(text(table), /Range 6.5–9.5/);
  assert.doesNotMatch(text(table), /Gap range/);
});

test("chart projection preserves supplied historical/future values and bounds without manufacturing data", async () => {
  const data = await getForecastExample("DEMO-B", "emergency-care");
  const before = structuredClone(data);
  const points = chartPoints(data);
  assert.equal(points.length, 63);
  assert.equal(points[0].historical_demand, 4);
  assert.equal(points[0].forecast_demand, null);
  assert.equal(points[56].historical_demand, null);
  assert.equal(points[58].forecast_demand, 8);
  assert.equal(points[58].forecast_capacity, 5);
  assert.deepEqual(points[58].demand_range, [6.5, 9.5]);
  assert.deepEqual(points[58].capacity_range, [4, 5]);
  assert.deepEqual(data, before);
  assert.ok(forecastDate("2026-10-12").includes("12"));
});

test("insufficient history and missing profiles do not manufacture future zeroes", async () => {
  const c = await getForecastExample("DEMO-A", "emergency-care");
  assert.match(text(renderToStaticMarkup(<InsufficientHistory data={c} />)), /Insufficient history/);
  assert.deepEqual(c.forecast, []);
  assert.equal(c.first_gap, null);
  assert.ok(chartPoints(c).some((point) => point.historical_capacity === null));
  assert.match(text(renderToStaticMarkup(<InsufficientHistory data={{ ...c, status: "not_configured", profile_version: null }} />)), /profile not configured/);
});

test("evidence displays published validation, provenance and timestamp limits", async () => {
  const data = await getForecastExample("DEMO-B", "emergency-care");
  const html = renderToStaticMarkup(<ForecastEvidence data={data} />);
  assert.match(html, /dateTime="2026-10-10T09:00:00Z"/);
  assert.match(html, /synthetic-demo-v1/);
  assert.match(html, /weekly_seasonal_baseline/);
  assert.match(html, /not calibrated confidence intervals/);
  assert.match(html, /not patients arriving per day/);
  assert.match(html, /demo-v1/);
  assert.match(html, /Exact observation timestamps/);
});

test("loader replaces previous results with pending state and preserves request failures", async () => {
  const states: ForecastState[] = [];
  const loader = createForecastLoader(getForecastExample, (state) => states.push(state));
  await loader.refresh("DEMO-B", "emergency-care");
  assert.equal(states[0].phase, "loading");
  await loader.refresh("DEMO-A", "emergency-care");
  assert.deepEqual(states[2], { phase: "updating" });
  const last = states.at(-1)!;
  assert.equal(last.phase, "ready");
  if (last.phase === "ready") assert.equal(last.data.status, "insufficient_history");
  await loader.refresh("missing", "emergency-care");
  assert.equal(states.at(-1)?.phase, "error");
  const wrong = createForecastLoader(() => getForecastExample("DEMO-B", "emergency-care"), (state) => states.push(state));
  await wrong.refresh("DEMO-A", "emergency-care");
  assert.equal(states.at(-1)?.phase, "error");
  const failure = createForecastLoader(async () => { throw new Error("Forecast API unavailable"); }, (state) => states.push(state));
  await failure.refresh("DEMO-B", "emergency-care");
  assert.deepEqual(states.at(-1), { phase: "error", message: "Forecast API unavailable" });
});

test("older successes, failures and canceled requests cannot replace the latest hospital forecast", async () => {
  const states: ForecastState[] = [];
  const requests = [deferred<ForecastPreview>(), deferred<ForecastPreview>(), deferred<ForecastPreview>(), deferred<ForecastPreview>()];
  let index = 0;
  const loader = createForecastLoader(() => requests[index++].promise, (state) => states.push(state));
  const old = loader.refresh("DEMO-B", "emergency-care");
  const next = loader.refresh("DEMO-A", "emergency-care");
  requests[1].resolve(await getForecastExample("DEMO-A", "emergency-care")); await next;
  const newest = states.at(-1);
  requests[0].resolve(await getForecastExample("DEMO-B", "emergency-care")); await old;
  assert.equal(states.at(-1), newest);
  const oldError = loader.refresh("DEMO-B", "emergency-care");
  const canceled = loader.refresh("DEMO-A", "emergency-care");
  loader.cancel(); const count = states.length;
  requests[2].reject(new Error("Old failure")); await oldError;
  requests[3].resolve(await getForecastExample("DEMO-A", "emergency-care")); await canceled;
  assert.equal(states.length, count);
});

test("API requests use the agreed route and never fall back to examples", async () => {
  const previous = globalThis.fetch;
  const example = await getForecastExample("DEMO-B", "emergency-care");
  try {
    let requested = "";
    globalThis.fetch = async (input, init) => {
      requested = String(input);
      assert.equal(init?.cache, "no-store");
      return new Response(JSON.stringify(example), { status: 200 });
    };
    const result = await getForecast("DEMO-B", "emergency-care");
    assert.equal(requested, "/api/v1/forecasts/facilities/DEMO-B?service_id=emergency-care");
    assert.equal(result.first_gap?.gap, 3);
    globalThis.fetch = async () => new Response("failure", { status: 500 });
    await assert.rejects(getForecast("DEMO-B", "emergency-care"), /API is unavailable/);
    globalThis.fetch = async () => { throw new Error("offline"); };
    await assert.rejects(getForecast("DEMO-B", "emergency-care"), /Could not connect/);
  } finally { globalThis.fetch = previous; }
});
