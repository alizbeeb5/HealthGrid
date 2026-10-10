import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createNetworkClient, type NetworkOverviewResponse } from "../src/lib/api/network";
import { FacilityClientError } from "../src/lib/api/facilities";
import { createNetworkLoader, type NetworkState } from "../src/features/network/network-loader";
import { SummaryCards } from "../src/features/network/summary-cards";
import { HospitalTable } from "../src/features/network/hospital-table";
import { AttentionList } from "../src/features/network/attention-list";
import { capacityFilter, evidenceWarnings, facilityLink, filterHospitals, hasMapLocation, initialService } from "../src/features/network/presentation";
import { summarizeNetwork } from "../src/features/network/summary";
import { overviewReturnPath } from "../src/features/network/return-navigation";
import bundle from "../src/lib/api/network-fixtures.generated.json";
import canonical from "../../../contracts/examples/feature-3/emergency-care.overview.response.json";
import canonicalServices from "../../../contracts/examples/feature-3/services.response.json";
import canonicalUnknown from "../../../contracts/examples/feature-3/unknown-service.overview.response.json";

const returnTo = "/overview?service_id=emergency-care&name=Hospital&status=unknown";
const example = () => structuredClone(canonical) as NetworkOverviewResponse;
const text = (html: string) => html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test("frozen preview matches published examples, returns unknown services empty, and never mutates shared data", async () => {
  const client = createNetworkClient("example");
  assert.deepEqual(bundle.overview, canonical);
  assert.deepEqual(bundle.services, canonicalServices);
  assert.deepEqual(bundle.unknownService, canonicalUnknown);
  assert.deepEqual(await client.listServices(), canonicalServices);
  const result = await client.getOverview("emergency-care");
  assert.deepEqual(result, canonical);
  result.facilities[1].capacity.estimated_capacity = 99;
  assert.equal((await client.getOverview("emergency-care")).facilities[1].capacity.estimated_capacity, 5);
  assert.deepEqual(await client.getOverview("maternity"), canonicalUnknown);
});

test("service selection prefers emergency care, otherwise sorts IDs; explicit unknown selection is preserved", () => {
  const services = [{ service_id: "z-service", name: "Z" }, { service_id: "a-service", name: "A" }];
  assert.equal(initialService(services, null), "a-service");
  assert.equal(initialService([...services, ...canonicalServices.items], null), "emergency-care");
  assert.equal(initialService(services, "missing"), "missing");
  assert.equal(initialService([], null), undefined);
  assert.equal(capacityFilter("not_configured"), "not_configured");
  assert.equal(capacityFilter("invalid"), "all");
});

test("baseline cards, table and ordered attention list preserve known coverage, zero, missing and stale evidence", () => {
  const rows = example().facilities;
  const summary = summarizeNetwork(rows);
  const cards = text(renderToStaticMarkup(<SummaryCards summary={summary} />));
  assert.match(cards, /5 modeled places; 2 of 3 hospitals have known estimates; 1 unresolved/);
  assert.match(cards, /not spare admission or transfer capacity/);
  const table = renderToStaticMarkup(<HospitalTable rows={rows} returnTo={returnTo} />);
  assert.match(table, /5 modeled places/); assert.match(table, /0 modeled places/); assert.match(table, /Not determined/);
  assert.match(table, /Working monitors/); assert.match(table, /OBS-DEMO-B-4/);
  assert.match(table, /Required resource reports are missing/); assert.match(table, /Required resource reports are outdated/);
  assert.match(table, /2026-10-09T07:05:00Z/);
  assert.match(table, /return_to=/);
  const attention = renderToStaticMarkup(<AttentionList rows={rows} attentionIds={summary.attention_facility_ids} returnTo={returnTo} />);
  assert.ok(attention.indexOf("Demo Hospital C") < attention.indexOf("Demo Hospital A"));
  assert.doesNotMatch(attention, /Demo Hospital B/);
});

test("name and status filters supply the same rows to every view, and never turn an empty selection into zero capacity", () => {
  const all = example().facilities;
  for (const [name, status] of [["Hospital B", "all"], ["", "unknown"], ["  demo HOSPITAL c  ", "unavailable"], ["missing", "all"], ["", "not_configured"]] as const) {
    const rows = filterHospitals(all, name, status);
    const summary = summarizeNetwork(rows);
    const table = renderToStaticMarkup(<HospitalTable rows={rows} returnTo={returnTo} />);
    const attention = renderToStaticMarkup(<AttentionList rows={rows} attentionIds={summary.attention_facility_ids} returnTo={returnTo} />);
    assert.equal(summary.facility_count, rows.length);
    assert.equal(rows.filter(hasMapLocation).length, rows.length);
    for (const row of all) {
      assert.equal(table.includes(row.facility.name), rows.includes(row));
      assert.equal(attention.includes(row.facility.name), summary.attention_facility_ids.includes(row.facility.facility_id));
    }
    if (!rows.length) assert.equal(summary.modeled_capacity_subtotal, null);
  }
  assert.equal(all.length, 3);
});

test("summary presentation handles incompatible assumptions, missing profiles, valid calculated zero and all unknown", () => {
  const rows = example().facilities;
  rows[2].capacity.profile_version = "other-profile";
  const incompatible = text(renderToStaticMarkup(<SummaryCards summary={summarizeNetwork(rows)} />));
  assert.match(incompatible, /Subtotal unavailable/); assert.match(incompatible, /Their assumptions differ/);
  assert.doesNotMatch(incompatible, /5 modeled places/);
  const unknown = text(renderToStaticMarkup(<SummaryCards summary={summarizeNetwork([rows[0]])} />));
  assert.match(unknown, /no known estimates/); assert.doesNotMatch(unknown, /0 modeled places/);
  const zero = example().facilities[1];
  zero.capacity.estimated_capacity = 0;
  zero.capacity.resource_limits.find((resource) => resource.resource_id === "working-monitors")!.available_quantity = 0;
  zero.capacity.resource_limits.find((resource) => resource.resource_id === "working-monitors")!.capacity_limit = 0;
  assert.match(evidenceWarnings(zero).join(" "), /zero modeled places/);
  const missing = example().facilities[0];
  missing.capacity = { ...missing.capacity, status: "not_configured", profile_version: null, resource_limits: [], reason_codes: ["requirements_not_configured"] };
  assert.match(renderToStaticMarkup(<HospitalTable rows={[missing, zero]} returnTo={returnTo} />), /No calculation profile configured/);
  const attention = renderToStaticMarkup(<AttentionList rows={[missing, zero]} attentionIds={summarizeNetwork([missing, zero]).attention_facility_ids} returnTo={returnTo} />);
  assert.ok(attention.indexOf("Demo Hospital B") < attention.indexOf("Demo Hospital A"));
});

test("network API uses one typed overview route with no caching or silent fixture fallback", async () => {
  const original = globalThis.fetch;
  try {
    const paths: string[] = [];
    globalThis.fetch = async (path, init) => {
      assert.equal(init?.cache, "no-store"); paths.push(String(path));
      return new Response(JSON.stringify(String(path).endsWith("services") ? canonicalServices : canonical));
    };
    const client = createNetworkClient("api");
    assert.deepEqual(await client.listServices(), canonicalServices);
    assert.deepEqual(await client.getOverview("id/with space"), canonical);
    assert.deepEqual(paths, ["/api/v1/network/services", "/api/v1/network/overview?service_id=id%2Fwith+space"]);
    globalThis.fetch = async () => new Response("Bad configuration", { status: 500 });
    await assert.rejects(client.getOverview("emergency-care"), /API is unavailable/);
    globalThis.fetch = async () => new Response("Missing endpoint", { status: 404 });
    await assert.rejects(client.listServices(), /Network reports could not be loaded/);
    globalThis.fetch = async () => new Response(JSON.stringify({ error: { code: "invalid_request", message: "Invalid service", fields: [] } }), { status: 422 });
    await assert.rejects(client.getOverview("invalid"), (error: unknown) => error instanceof FacilityClientError && error.detail?.code === "invalid_request");
  } finally { globalThis.fetch = original; }
});

test("network loader hides old results, publishes updated capacity, and handles empty/error catalogs visibly", async () => {
  const states: NetworkState[] = [];
  const loader = createNetworkLoader((state) => states.push(state));
  await loader.refresh(createNetworkClient("example"), "example", null);
  const after = example(); after.facilities[1].capacity.estimated_capacity = 8;
  await loader.refresh({ listServices: async () => canonicalServices, getOverview: async () => after }, "api", "emergency-care");
  assert.equal(states[2].phase, "updating");
  const ready = states.at(-1)!;
  assert.equal(ready.phase, "ready");
  if (ready.phase === "ready") assert.equal(summarizeNetwork(ready.data.facilities).modeled_capacity_subtotal, 8);
  await loader.refresh({ listServices: async () => ({ items: [] }), getOverview: async () => { throw new Error("Should not request overview"); } }, "api", null);
  assert.deepEqual(states.at(-1), { phase: "empty", services: [] });
  await loader.refresh({ listServices: async () => { throw new Error("Database offline"); }, getOverview: async () => after }, "api", null);
  assert.deepEqual(states.at(-1), { phase: "error", message: "Database offline" });
});

test("out-of-order successes, failures, canceled requests and service switches cannot replace newer results", async () => {
  const states: NetworkState[] = [];
  const loader = createNetworkLoader((state) => states.push(state));
  const firstResponse = deferred<NetworkOverviewResponse>();
  const entered = deferred<boolean>();
  const first = loader.refresh({ listServices: async () => canonicalServices, getOverview: () => { entered.resolve(true); return firstResponse.promise; } }, "api", "emergency-care");
  await entered.promise;
  await loader.refresh(createNetworkClient("example"), "example", "maternity");
  const newer = states.at(-1);
  firstResponse.resolve(example()); await first;
  assert.equal(states.at(-1), newer);
  const oldCatalog = deferred<typeof canonicalServices>();
  const old = loader.refresh({ listServices: () => oldCatalog.promise, getOverview: async () => example() }, "api", null);
  await loader.refresh(createNetworkClient("example"), "example", null);
  const current = states.at(-1);
  oldCatalog.reject(new Error("Old failure")); await old;
  assert.equal(states.at(-1), current);
  const canceled = deferred<typeof canonicalServices>();
  const pending = loader.refresh({ listServices: () => canceled.promise, getOverview: async () => example() }, "api", null);
  loader.cancel(); const count = states.length;
  canceled.resolve(canonicalServices); await pending;
  assert.equal(states.length, count);
  await loader.refresh({ listServices: async () => canonicalServices, getOverview: async () => example() }, "api", "maternity");
  assert.equal(states.at(-1)?.phase, "error");
});

test("hospital navigation preserves filters and only accepts safe overview return paths", () => {
  const href = facilityLink("DEMO-B", returnTo);
  assert.equal(new URL(href, "http://local").searchParams.get("return_to"), returnTo);
  assert.equal(overviewReturnPath(returnTo), returnTo);
  for (const value of ["https://evil.test/overview", "//evil.test/overview", "/facilities", "/overview/other", "/overview\\evil", ["/overview"]]) assert.equal(overviewReturnPath(value), undefined);
  assert.equal(overviewReturnPath(undefined), undefined);
  const invalid = example().facilities[0]; invalid.facility.latitude = Number.NaN;
  assert.equal(hasMapLocation(invalid), false);
});
