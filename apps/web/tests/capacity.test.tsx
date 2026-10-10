import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { CapacityPanel } from "../src/features/facilities/capacity-panel";
import { createCapacityLoader, type CapacityState } from "../src/features/facilities/capacity-loader";
import { getCapacityExample, getFacilityCapacity } from "../src/lib/api/capacity";
import { FacilityClientError } from "../src/lib/api/facilities";
import type { FacilityCapacityResponse } from "../src/lib/api/feature-2";
import type { FacilitySnapshotResponse } from "../src/lib/api/feature-1";
import bundle from "../src/lib/api/capacity-fixtures.generated.json";
import canonicalA from "../../../contracts/examples/feature-2/DEMO-A.capacity.response.json";
import canonicalB from "../../../contracts/examples/feature-2/DEMO-B.capacity.response.json";
import canonicalC from "../../../contracts/examples/feature-2/DEMO-C.capacity.response.json";
import snapshotA from "../../../contracts/examples/feature-1/DEMO-A.snapshot.response.json";
import snapshotB from "../../../contracts/examples/feature-1/DEMO-B.snapshot.response.json";
import snapshotC from "../../../contracts/examples/feature-1/DEMO-C.snapshot.response.json";

function panel(data: FacilityCapacityResponse, snapshot: unknown = snapshotB, source: "api" | "example" = "api") {
  return renderToStaticMarkup(<CapacityPanel state={{ phase: "ready", data, source }} snapshot={snapshot as FacilitySnapshotResponse} onRefresh={() => {}} />);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test("capacity bundles preserve the shared examples without computing results", () => {
  assert.deepEqual(bundle.responses, { "DEMO-A": canonicalA, "DEMO-B": canonicalB, "DEMO-C": canonicalC });
  const example = getCapacityExample("DEMO-B");
  example.services[0].estimated_capacity = 99;
  assert.equal(getCapacityExample("DEMO-B").services[0].estimated_capacity, 5);
  assert.throws(() => getCapacityExample("missing"), /No synthetic capacity example/);
});

test("Demo B renders modeled places, bottleneck, per-resource assumptions, provenance and its own clock", () => {
  const html = panel(getCapacityExample("DEMO-B"));
  assert.match(html, /5 simultaneous service places/);
  assert.match(html, /Working monitors/);
  assert.match(html, /Bottleneck/);
  assert.match(html, /0\.5 person/);
  assert.match(html, /18 places/);
  assert.match(html, /OBS-DEMO-B-4/);
  assert.match(html, /dateTime="2026-10-10T09:00:00Z"/);
  assert.match(html, /Fictional demo rules/);
  assert.match(html, /Do not add estimates across services/);
  assert.match(html, /not confirmed spare admission capacity/);
  assert.doesNotMatch(html, /Available oxygen stock/);
});

test("unknown, unavailable and not-configured explain the distinct states; zero stays numeric", () => {
  const unknown = panel(getCapacityExample("DEMO-A"), snapshotA);
  assert.match(unknown, /Capacity cannot be determined/);
  assert.match(unknown, /restriction has not been quantified/);
  assert.match(unknown, /no observation/);
  assert.doesNotMatch(unknown, /0 simultaneous service places/);
  const unavailable = panel(getCapacityExample("DEMO-C"), snapshotC);
  assert.match(unavailable, /0 simultaneous service places/);
  assert.match(unavailable, /service is reported as unavailable/);
  assert.match(unavailable, /observations are outdated/);
  assert.match(unavailable, /Cannot determine/);
  const notConfigured = panel(bundle.stateExamples.notConfigured as FacilityCapacityResponse);
  assert.match(notConfigured, /Not configured/);
  assert.match(notConfigured, /No resource requirements are configured/);
  const noServices = panel(bundle.stateExamples.noServices as FacilityCapacityResponse);
  assert.match(noServices, /No services are configured/);
  const zero = getCapacityExample("DEMO-B");
  zero.services[0].estimated_capacity = 0;
  assert.match(panel(zero), /0 simultaneous service places/);
});

test("all tied bottlenecks render; frozen examples are visibly separate from saved reports", () => {
  const data = getCapacityExample("DEMO-B");
  data.services[0].bottleneck_resource_ids = ["available-beds", "working-monitors"];
  const html = panel(data, snapshotB, "example");
  assert.match(html, /Bottlenecks \(tied\)/);
  assert.match(html, /Available physical beds, Working monitors/);
  assert.match(html, /Synthetic capacity example/);
  assert.match(html, /does not reflect saved resource updates/);
});

test("loading, updating and failed requests show no previous estimate", () => {
  for (const state of [{ phase: "loading" }, { phase: "updating" }, { phase: "error", message: "Capacity API offline" }] as CapacityState[]) {
    const html = renderToStaticMarkup(<CapacityPanel state={state} snapshot={snapshotB as FacilitySnapshotResponse} onRefresh={() => {}} onShowExample={() => {}} />);
    assert.doesNotMatch(html, /5 simultaneous service places/);
    if (state.phase === "updating") assert.match(html, /Previous results are hidden/);
    if (state.phase === "error") { assert.match(html, /Capacity API offline/); assert.match(html, /View synthetic example/); }
  }
});

test("refresh consumes the changed API estimate from 5 to 8 without frontend calculations", async () => {
  const before = getCapacityExample("DEMO-B");
  const after = getCapacityExample("DEMO-B");
  after.services[0].estimated_capacity = 8;
  const monitor = after.services[0].resource_limits.find((item) => item.resource_id === "working-monitors")!;
  monitor.available_quantity = 8; monitor.capacity_limit = 8;
  let response = before;
  const states: CapacityState[] = [];
  const loader = createCapacityLoader(async () => response, (state) => states.push(state));
  await loader.refresh();
  response = after;
  await loader.refresh();
  const final = states.at(-1)!;
  assert.equal(states[2].phase, "updating");
  assert.equal(final.phase, "ready");
  if (final.phase === "ready") assert.match(panel(final.data), /8 simultaneous service places/);
});

test("older successes, older failures and canceled requests cannot replace newer results", async () => {
  const requests = [deferred<FacilityCapacityResponse>(), deferred<FacilityCapacityResponse>(), deferred<FacilityCapacityResponse>(), deferred<FacilityCapacityResponse>()];
  let index = 0;
  const states: CapacityState[] = [];
  const loader = createCapacityLoader(() => requests[index++].promise, (state) => states.push(state));
  const first = loader.refresh();
  const second = loader.refresh();
  const next = getCapacityExample("DEMO-B"); next.services[0].estimated_capacity = 8;
  requests[1].resolve(next); await second;
  requests[0].resolve(getCapacityExample("DEMO-B")); await first;
  assert.deepEqual(states.at(-1), { phase: "ready", source: "api", data: next });
  const oldFailure = loader.refresh();
  loader.showExample(next);
  requests[2].reject(new Error("Old error")); await oldFailure;
  assert.equal(states.at(-1)?.phase, "ready");
  const canceled = loader.refresh(); loader.cancel();
  const count = states.length;
  requests[3].resolve(next); await canceled;
  assert.equal(states.length, count);
});

test("refresh invalidates a displayed example and independently handles request failures", async () => {
  const states: CapacityState[] = [];
  const loader = createCapacityLoader(async () => { throw new Error("Capacity unavailable"); }, (state) => states.push(state));
  loader.showExample(getCapacityExample("DEMO-B"));
  await loader.refresh();
  assert.equal(states[1].phase, "updating");
  assert.deepEqual(states.at(-1), { phase: "error", message: "Capacity unavailable" });
});

test("capacity client uses the agreed route, preserves 404 contract errors, and never silently falls back", async () => {
  const original = globalThis.fetch;
  try {
    let path: string | undefined;
    globalThis.fetch = async (input, init) => {
      path = String(input); assert.equal(init?.cache, "no-store");
      return new Response(JSON.stringify(canonicalB));
    };
    assert.deepEqual(await getFacilityCapacity("DEMO-B"), canonicalB);
    assert.equal(path, "/api/v1/capacity/facilities/DEMO-B");
    await getFacilityCapacity("id/with space");
    assert.equal(path, "/api/v1/capacity/facilities/id%2Fwith%20space");
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 });
    await assert.rejects(getFacilityCapacity("DEMO-B"), /Capacity could not be loaded/);
    globalThis.fetch = async () => new Response(JSON.stringify({ error: { code: "facility_not_found", message: "Facility absent", fields: [] } }), { status: 404 });
    await assert.rejects(getFacilityCapacity("missing"), (error: unknown) => error instanceof FacilityClientError && error.detail?.code === "facility_not_found");
  } finally { globalThis.fetch = original; }
});
