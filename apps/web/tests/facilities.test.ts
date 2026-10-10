import assert from "node:assert/strict";
import { test } from "node:test";
import { createDemoClient } from "../src/lib/api/facilities-demo";
import { facilityRequest, FacilityClientError } from "../src/lib/api/facilities";
import { toLocalInput, validateObservationInput } from "../src/features/facilities/validation";
import type { ObservationCreate } from "../src/lib/api/feature-1";
import generatedFixtures from "../src/lib/api/facilities-fixtures.generated.json";
import sharedList from "../../../contracts/examples/feature-1/facilities.response.json";
import sharedA from "../../../contracts/examples/feature-1/DEMO-A.snapshot.response.json";
import sharedB from "../../../contracts/examples/feature-1/DEMO-B.snapshot.response.json";
import sharedC from "../../../contracts/examples/feature-1/DEMO-C.snapshot.response.json";

function memoryStorage() {
  const values = new Map<string, string>();
  return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); } };
}
const update: ObservationCreate = { resource_id: "available-beds", available_quantity: 10, unit: "bed", observed_at: "2026-10-10T08:55:00Z" };

test("the bundled examples match the canonical shared fixtures", () => {
  assert.deepEqual(generatedFixtures, { list: sharedList, snapshots: { "DEMO-A": sharedA, "DEMO-B": sharedB, "DEMO-C": sharedC } });
});

test("fixtures distinguish stale zero from unknown, using the fixture clock", async () => {
  const demo = createDemoClient(memoryStorage());
  const a = await demo.getFacilitySnapshot("DEMO-A");
  const c = await demo.getFacilitySnapshot("DEMO-C");
  assert.equal(a.resources.find((item) => item.resource_id === "working-monitors")?.available_quantity, null);
  assert.equal(a.resources.find((item) => item.resource_id === "working-monitors")?.data_status, "unknown");
  assert.equal(c.resources[0].available_quantity, 0);
  assert.equal(c.resources[0].data_status, "stale");
  assert.equal(a.as_of, "2026-10-10T09:00:00.000Z");
});

test("an appended update survives a new client; historical reports do not replace latest values", async () => {
  const storage = memoryStorage();
  const firstClient = createDemoClient(storage);
  const saved = await firstClient.createResourceObservation("DEMO-A", update);
  const reloaded = createDemoClient(storage);
  assert.equal((await reloaded.getFacilitySnapshot("DEMO-A")).resources[0].available_quantity, 10);
  const historical = await reloaded.createResourceObservation("DEMO-A", { ...update, available_quantity: 3, observed_at: "2026-10-09T08:00:00Z" });
  const snapshot = await reloaded.getFacilitySnapshot("DEMO-A");
  assert.equal(snapshot.resources[0].observation_id, saved.observation_id);
  assert.equal(snapshot.facility.last_reported_at, historical.recorded_at);
  assert.equal((await reloaded.listFacilities()).items[0].last_reported_at, historical.recorded_at);
  assert.equal(JSON.parse(storage.getItem("healthgrid:synthetic-observations:v1")!).length, 2);
  assert.equal((await reloaded.getFacilitySnapshot("DEMO-B")).resources[0].available_quantity, 18);
});

test("equal observation times use latest receipt; exactly 24 hours remains current", async () => {
  const demo = createDemoClient(memoryStorage());
  await demo.createResourceObservation("DEMO-A", update);
  const latest = await demo.createResourceObservation("DEMO-A", { ...update, available_quantity: 0 });
  assert.equal((await demo.getFacilitySnapshot("DEMO-A")).resources[0].observation_id, latest.observation_id);
  await demo.createResourceObservation("DEMO-A", { resource_id: "working-monitors", available_quantity: 1, unit: "item", observed_at: "2026-10-09T09:00:03Z" });
  assert.equal((await demo.getFacilitySnapshot("DEMO-A")).resources[3].data_status, "current");
  await demo.createResourceObservation("DEMO-B", update);
  assert.equal((await demo.getFacilitySnapshot("DEMO-A")).resources[3].data_status, "stale");
});

test("demo rejects invalid units, quantities, applicability, future times and missing hospitals", async () => {
  const demo = createDemoClient(memoryStorage());
  for (const payload of [
    { ...update, unit: "liter" as const }, { ...update, available_quantity: 1.5 },
    { ...update, available_quantity: -1 }, { ...update, available_quantity: Infinity },
    { ...update, resource_id: "missing" }, { ...update, observed_at: "2026-10-10T09:05:01Z" },
  ]) {
    await assert.rejects(demo.createResourceObservation("DEMO-A", payload), (error: unknown) => error instanceof FacilityClientError && error.status === 422);
  }
  await assert.rejects(demo.getFacilitySnapshot("missing"), (error: unknown) => error instanceof FacilityClientError && error.status === 404);
});

test("corrupt or unwritable browser storage never reports save success", async () => {
  await assert.rejects(createDemoClient({ getItem: () => "broken", setItem: () => {} }).listFacilities(), /could not be read/);
  await assert.rejects(createDemoClient({ getItem: () => null, setItem: () => { throw new Error("Full"); } }).createResourceObservation("DEMO-A", update), /could not be stored/);
});

test("form validates blanks, whole numbers, finite values, fractional quantities and UTC conversion", async () => {
  const snapshot = await createDemoClient(memoryStorage()).getFacilitySnapshot("DEMO-A");
  const now = new Date(snapshot.as_of);
  const local = toLocalInput(new Date(update.observed_at));
  const beds = snapshot.resources[0];
  for (const quantity of ["", "-1", "Infinity", "1.2"]) {
    assert.ok(validateObservationInput(beds, quantity, local, now).errors.available_quantity);
  }
  assert.ok(validateObservationInput(beds, "1", "", now).errors.observed_at);
  assert.ok(validateObservationInput(beds, "1", toLocalInput(new Date("2026-10-10T09:06:00Z")), now).errors.observed_at);
  assert.ok(validateObservationInput(undefined, "1", local, now).errors.resource_id);
  assert.equal(validateObservationInput(beds, "0", local, now).payload?.available_quantity, 0);
  assert.equal(validateObservationInput(beds, "10", local, now).payload?.observed_at, "2026-10-10T08:55:00.000Z");
  assert.equal(validateObservationInput(snapshot.resources[2], "1.5", local, now).payload?.available_quantity, 1.5);
});

test("API transport sends JSON, maps contract errors and does not retry ambiguous POST", async () => {
  const original = globalThis.fetch;
  const requests: { path: string; init?: RequestInit }[] = [];
  try {
    globalThis.fetch = async (path, init) => {
      requests.push({ path: String(path), init });
      return new Response(JSON.stringify({ ...update, observation_id: "OBS-1", facility_id: "DEMO-A", recorded_at: "2026-10-10T09:01:00Z" }), { status: 201 });
    };
    const response = await facilityRequest("/api/v1/facilities/DEMO-A/observations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(update) });
    assert.equal((response as { observation_id: string }).observation_id, "OBS-1");
    assert.equal(requests[0].init?.cache, "no-store");
    assert.deepEqual(JSON.parse(requests[0].init?.body as string), update);
    globalThis.fetch = async () => new Response(JSON.stringify({ error: { code: "invalid_observation", message: "Invalid quantity", fields: [{ field: "available_quantity", message: "Whole numbers only" }] } }), { status: 422 });
    await assert.rejects(facilityRequest("/api/v1/facilities/DEMO-A/observations", { method: "POST" }), (error: unknown) => error instanceof FacilityClientError && error.detail?.fields[0].field === "available_quantity");
    let calls = 0;
    globalThis.fetch = async () => { calls++; throw new Error("Connection dropped"); };
    await assert.rejects(facilityRequest("/api/v1/facilities/DEMO-A/observations", { method: "POST" }), /Refresh the snapshot/);
    assert.equal(calls, 1);
    globalThis.fetch = async () => new Response("Proxy down", { status: 502 });
    await assert.rejects(facilityRequest("/api/v1/facilities"), /API is unavailable/);
  } finally { globalThis.fetch = original; }
});

test("API mode connects all three client methods to the agreed endpoints without a demo fallback", async () => {
  const originalFetch = globalThis.fetch;
  const originalMode = process.env.NEXT_PUBLIC_FACILITIES_DATA_MODE;
  const modulePath = require.resolve("../src/lib/api/facilities");
  const cachedModule = require.cache[modulePath];
  const requests: { path: string; init?: RequestInit }[] = [];
  try {
    process.env.NEXT_PUBLIC_FACILITIES_DATA_MODE = "api";
    delete require.cache[modulePath];
    const client: typeof import("../src/lib/api/facilities") = require(modulePath);
    globalThis.fetch = async (path, init) => {
      requests.push({ path: String(path), init });
      const response = init?.method === "POST" ? { ...update, facility_id: "DEMO-A", observation_id: "OBS-NEW", recorded_at: "2026-10-10T09:01:00Z" }
        : String(path).endsWith("snapshot") ? sharedA : { items: [] };
      return new Response(JSON.stringify(response), { status: init?.method === "POST" ? 201 : 200 });
    };
    assert.equal(client.facilityDataMode, "api");
    assert.deepEqual(await client.listFacilities(), { items: [] });
    assert.deepEqual(await client.getFacilitySnapshot("DEMO-A"), sharedA);
    await client.createResourceObservation("DEMO-A", update);
    assert.deepEqual(requests.map((item) => item.path), ["/api/v1/facilities", "/api/v1/facilities/DEMO-A/snapshot", "/api/v1/facilities/DEMO-A/observations"]);
    assert.equal(requests[2].init?.method, "POST");
    assert.deepEqual(JSON.parse(requests[2].init?.body as string), update);
    globalThis.fetch = async () => new Response("Endpoint missing", { status: 404 });
    await assert.rejects(client.listFacilities(), (error: unknown) => error instanceof FacilityClientError && error.status === 404);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalMode === undefined) delete process.env.NEXT_PUBLIC_FACILITIES_DATA_MODE;
    else process.env.NEXT_PUBLIC_FACILITIES_DATA_MODE = originalMode;
    require.cache[modulePath] = cachedModule;
  }
});
