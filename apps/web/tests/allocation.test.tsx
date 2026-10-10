import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import runExample from "../../../contracts/examples/feature-6/improved.response.json";
import simulationExample from "../../../contracts/examples/feature-5/simulation-run.response.json";
import revisionExample from "../../../contracts/examples/feature-5/incident-confirmed.response.json";
import type { components } from "../src/lib/api/schema";
import { allocationPayload, calculateAllocation, exampleSource, presentAllocation, reopenAllocation } from "../src/features/allocation/source";
import { validatePlanning } from "../src/features/allocation/model";
import { ProposalPanel } from "../src/features/allocation/proposal-panel";

const run = runExample as components["schemas"]["AllocationRun"];
const source = { ...exampleSource(), example: false, simulation_run_id: run.simulation_run_id };

test("shared request is submitted once and the saved result is displayed without recalculation", async () => {
  const proposal = presentAllocation(run, source);
  assert.deepEqual(validatePlanning(proposal.input, source), []);
  assert.deepEqual(allocationPayload(proposal.input), run.input);
  const original = globalThis.fetch;
  const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init }); return Response.json(run, { status: 201 });
  };
  try {
    const result = await calculateAllocation(proposal.input, source);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "/api/v1/allocation/runs");
    assert.equal(calls[0].init?.method, "POST");
    assert.deepEqual(JSON.parse(calls[0].init?.body as string), run.input);
    assert.equal(result.id, run.allocation_run_id);
    assert.equal(result.baseline.covered, 5);
    assert.equal(result.proposed?.covered, 6);
    assert.equal(result.proposed?.unmet, 5);
    const html = renderToStaticMarkup(<ProposalPanel proposal={result} />);
    assert.ok(html.includes("OR-Tools proposal"));
    assert.ok(html.includes("Transfer constraints independently validated"));
    assert.ok(!html.includes("no OR-Tools solve executed"));
    assert.ok(html.includes("DEMO-C"));
  } finally { globalThis.fetch = original; }
});

test("field-level errors stay visible and failures never load a preview or retry a save", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls++; return Response.json({ error: { message: "Invalid constraints", fields: [
      { field: "routes.0.to_facility_id", message: "Hospital needs planning constraints" },
    ] } }, { status: 422 });
  };
  try {
    await assert.rejects(calculateAllocation(presentAllocation(run, source).input, source),
      /routes\.0\.to_facility_id: Hospital needs planning constraints/);
    assert.equal(calls, 1);
    globalThis.fetch = async () => { calls++; throw new Error("Disconnected"); };
    await assert.rejects(calculateAllocation(presentAllocation(run, source).input, source),
      /save could not be confirmed/);
    assert.equal(calls, 2);
  } finally { globalThis.fetch = original; }
});

test("missing form quantities and zero route limits are rejected before submission", () => {
  const form = presentAllocation(run, source).input;
  form.facility_constraints[0].transferable_quantity = "";
  form.routes[0].maximum_quantity = "0";
  const errors = validatePlanning(form, source);
  assert.ok(errors.some((error) => error.includes("unknown is not zero")));
  assert.ok(errors.some((error) => error.includes("positive whole number")));
});

test("reopening retrieves the immutable proposal and saved incident using only GET requests", async () => {
  const original = globalThis.fetch;
  const calls: string[] = [];
  const simulation = structuredClone(simulationExample);
  simulation.run_id = run.simulation_run_id;
  simulation.impact.incident_id = run.incident_id;
  simulation.impact.revision_id = run.revision_id;
  simulation.impact.baseline_id = run.baseline_id;
  globalThis.fetch = async (url, init) => {
    assert.ok(!init?.method || init.method === "GET");
    calls.push(String(url));
    return Response.json(String(url).includes("/allocation/") ? run : String(url).includes("/scenarios/runs/") ? simulation : revisionExample);
  };
  try {
    const reopened = await reopenAllocation(run.allocation_run_id);
    assert.deepEqual(calls, [
      `/api/v1/allocation/runs/${run.allocation_run_id}`,
      `/api/v1/scenarios/runs/${run.simulation_run_id}`,
      `/api/v1/scenarios/incidents/${run.incident_id}/revisions/${run.revision_id}`,
    ]);
    assert.equal(reopened.saved_at, run.created_at);
    assert.deepEqual(allocationPayload(reopened.input), run.input);
    assert.equal(reopened.proposed?.covered, 6);
    assert.equal(reopened.source.baseline_id, run.baseline_id);
  } finally { globalThis.fetch = original; }
});
