import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import improved from "../../../contracts/examples/feature-7/improved.response.json";
import unknown from "../../../contracts/examples/feature-7/timeout.response.json";
import incomplete from "../../../contracts/examples/feature-7/needs-inputs.response.json";
import catalog from "../../../contracts/examples/feature-7/catalog.response.json";
import type { components } from "../src/lib/api/schema";
import { createInvestment, formFromRequest, loadCatalogForm, loadInvestment, previewFromRun, requestFromForm } from "../src/features/investments/source";
import { validateInvestment } from "../src/features/investments/model";
import { PackageComparison } from "../src/features/investments/package-comparison";
import { FacilityClientError } from "../src/lib/api/facilities";

const run = improved as components["schemas"]["InvestmentRun"];

test("editor round-trips the canonical request without calculating benefits", () => {
  const form = formFromRequest(run.input);
  assert.deepEqual(requestFromForm(form), run.input);
  assert.deepEqual(validateInvestment(form, previewFromRun(run).source), []);
  const missing = structuredClone(form); missing.candidates[0].source_note = ""; missing.candidates[0].confirmed_at = "";
  assert.equal(requestFromForm(missing).candidates[0].source_note, null);
  assert.equal(requestFromForm(missing).candidates[0].confirmed_at, null);
});

test("live calculation submits once and reopening uses the saved result only", async () => {
  const original = globalThis.fetch; const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (url, init) => { calls.push({ url: String(url), init }); return Response.json(run); };
  try {
    const result = await createInvestment(formFromRequest(run.input));
    assert.equal(calls.length, 1); assert.equal(calls[0].url, "/api/v1/investments/runs");
    assert.equal(calls[0].init?.method, "POST");
    assert.deepEqual(JSON.parse(calls[0].init?.body as string), run.input);
    assert.equal(result.total_cost_minor_units, 240000);
    assert.equal(result.source.summary.covered_service_places, 6);
    assert.equal(result.proposed?.covered_service_places, 11);
    assert.deepEqual(await loadInvestment(result.id), result);
    assert.equal(calls.length, 2);
    assert.equal(calls[1].url, `/api/v1/investments/runs/${result.id}`);
    assert.equal(calls[1].init?.method, undefined);
  } finally { globalThis.fetch = original; }
});

test("catalog loads canonical project IDs while planning dates stay explicit", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (url) => { assert.equal(url, "/api/v1/investments/catalog"); return Response.json(catalog); };
  try {
    const form = await loadCatalogForm("ALLOC-1");
    assert.equal(form.allocation_run_id, "ALLOC-1"); assert.equal(form.planning_starts_at, "");
    assert.equal(form.evaluation_at, ""); assert.equal(form.catalog_version, catalog.catalog_version);
    assert.deepEqual(requestFromForm(form).candidates, catalog.candidates);
  } finally { globalThis.fetch = original; }
});

test("field-level errors survive; failed saves do not retry or load a demo", async () => {
  const original = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({ error: { code: "invalid_request", message: "Invalid investment inputs", fields: [{ field: "evaluation_at", message: "Must follow planning start" }] } }, { status: 422 }); };
  try {
    await assert.rejects(createInvestment(formFromRequest(run.input)), (error: unknown) => error instanceof FacilityClientError && error.detail?.fields[0].field === "evaluation_at");
    assert.equal(calls, 1);
    globalThis.fetch = async () => { calls++; throw new Error("Disconnected"); };
    await assert.rejects(createInvestment(formFromRequest(run.input)), /save could not be confirmed/);
    assert.equal(calls, 2);
  } finally { globalThis.fetch = original; }
});

test("mismatched saved IDs are rejected", async () => {
  const original = globalThis.fetch; globalThis.fetch = async () => Response.json(run);
  try { await assert.rejects(loadInvestment("OTHER"), /does not match/); }
  finally { globalThis.fetch = original; }
});

test("package panel shows real solver, costs, evidence and ready dates", () => {
  const html = renderToStaticMarkup(<PackageComparison proposal={previewFromRun(run)} />);
  assert.ok(html.includes("Saved OR-Tools funding proposal"));
  assert.ok(html.includes("investment-cpsat-v1")); assert.ok(html.includes("DEMO-C"));
  assert.ok(html.includes("Commission five repaired monitors"));
  assert.ok(!html.includes("no OR-Tools solve executed"));
});

for (const payload of [unknown, incomplete]) {
  test(`${payload.solver_status} does not present selected projects or invented capacity`, () => {
    const proposal = previewFromRun(payload as components["schemas"]["InvestmentRun"]);
    assert.equal(proposal.proposed, null); assert.deepEqual(proposal.selected_projects, []);
    const html = renderToStaticMarkup(<PackageComparison proposal={proposal} />);
    assert.ok(html.includes("No independently validated package"));
    assert.ok(html.includes("No proposal")); assert.ok(html.includes("Not supplied"));
  });
}
