// Pass the compiled summary.js path. Runs without a browser or extra packages.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const { summarizeNetwork } = require(process.argv[2]);
const cases = JSON.parse(readFileSync(new URL("summary-cases.json", import.meta.url)));

for (const scenario of cases) {
  test(scenario.case, () => {
    const original = structuredClone(scenario.rows);
    assert.deepEqual(summarizeNetwork(scenario.rows), scenario.expected);
    assert.deepEqual(scenario.rows, original, "summary must not modify input rows");
    assert.deepEqual(summarizeNetwork([...scenario.rows].reverse()), scenario.expected);
  });
}

function baseline() {
  return structuredClone(cases[0].rows);
}

test("mismatched units suppress subtotal", () => {
  const rows = baseline();
  rows[2].capacity.capacity_unit = "other_unit";
  const result = summarizeNetwork(rows);
  assert.equal(result.subtotal_status, "incompatible_profiles");
  assert.equal(result.modeled_capacity_subtotal, null);
});

test("different services cannot be combined", () => {
  const rows = baseline();
  rows[0].capacity.service_id = "demo-outpatient";
  assert.throws(() => summarizeNetwork(rows), /only one service/);
});

test("duplicate facilities cannot inflate coverage", () => {
  assert.throws(() => summarizeNetwork([baseline()[1], baseline()[1]]), /Duplicate/);
});

test("invalid known estimates fail rather than become plausible totals", () => {
  for (const value of [null, -1, 0.5, Infinity, NaN, Number.MAX_SAFE_INTEGER + 1]) {
    const rows = baseline();
    rows[1].capacity.estimated_capacity = value;
    assert.throws(() => summarizeNetwork(rows), /safe integers/);
  }
  const rows = baseline();
  rows[2].capacity.estimated_capacity = 3;
  assert.throws(() => summarizeNetwork(rows), /estimate of zero/);
});

test("unknown estimate cannot be silently counted as zero", () => {
  const rows = baseline();
  rows[0].capacity.estimated_capacity = 0;
  assert.throws(() => summarizeNetwork(rows), /remain null/);
});

test("subtotal overflow fails visibly", () => {
  const rows = baseline();
  rows[0].capacity.status = "calculated";
  rows[0].capacity.estimated_capacity = Number.MAX_SAFE_INTEGER;
  assert.throws(() => summarizeNetwork(rows), /safe integer precision/);
});

test("unknown attention precedes unconfigured, then IDs break ties", () => {
  const rows = baseline();
  rows[1].capacity = { ...rows[0].capacity, status: "not_configured", profile_version: null };
  rows[2].capacity = { ...rows[0].capacity };
  assert.deepEqual(summarizeNetwork(rows).attention_facility_ids, ["DEMO-A", "DEMO-C", "DEMO-B"]);
});

test("full existing contract examples produce the baseline summary", () => {
  const examples = new URL("../../../contracts/examples/", import.meta.url);
  const rows = ["A", "B", "C"].map(letter => ({
    facility: JSON.parse(readFileSync(new URL(`feature-1/DEMO-${letter}.snapshot.response.json`, examples))).facility,
    capacity: JSON.parse(readFileSync(new URL(`feature-2/DEMO-${letter}.capacity.response.json`, examples))).services[0],
  }));
  assert.deepEqual(summarizeNetwork(rows), cases[0].expected);
});


test("published network overview produces the agreed summary", () => {
  const overview = JSON.parse(readFileSync(new URL(
    "../../../contracts/examples/feature-3/emergency-care.overview.response.json", import.meta.url
  )));
  assert.deepEqual(summarizeNetwork(overview.facilities), cases[0].expected);
});
