import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createIncidentApiClient } from "../src/features/scenarios/api-client";
import { AIReview } from "../src/features/scenarios/review-panel";
import { outageExample, outageReport } from "../src/features/scenarios/model";
import { requestEmergencyAdvice, EmergencyAdviceResult } from "../src/features/scenarios/emergency-advice";
import guidance from "../../../contracts/examples/feature-5/emergency-advice.response.json";
import type { EmergencyAdvice } from "../src/features/scenarios/emergency-advice";

test("emergency guidance displays the backend field errors instead of hiding the invalid input", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ error: { fields: [
    { field: "incident.affected_facility_ids.0", message: "Unknown facility DEMO-X." },
  ] } }, { status: 422 });
  try {
    await assert.rejects(requestEmergencyAdvice(outageExample()),
      /incident\.affected_facility_ids\.0: Unknown facility DEMO-X/);
  } finally { globalThis.fetch = original; }
});

test("connected assessment posts the actual report once and displays provider flags and metadata", async () => {
  const original = globalThis.fetch;
  const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return Response.json({ assessment_status: "completed", model: "gpt-6-luna", elapsed_ms: 123,
      rubric_version: "emergency-review-v1", answers: [
        { name: "outage_reported", value: "yes", answer_status: "completed" },
        { name: "multiple_facilities_reported", value: "no", answer_status: "completed" },
        { name: "resource_loss_reported", value: null, answer_status: "refused" },
        { name: "clarification_needed", value: "unclear", answer_status: "completed" },
      ] });
  };
  try {
    const result = await createIncidentApiClient().assess(outageReport);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "/api/v1/intelligence/incidents/assess");
    assert.equal(calls[0].init?.method, "POST");
    assert.equal(calls[0].init?.cache, "no-store");
    assert.deepEqual(JSON.parse(calls[0].init?.body as string), { report_text: outageReport });
    assert.deepEqual(calls[0].init?.headers, { "Content-Type": "application/json" });
    const html = renderToStaticMarkup(<AIReview assessment={{ phase: "ready", data: result }} extraction={{ phase: "idle" }} assess={() => {}} extract={() => {}} sample={() => {}} accept={() => {}} canAccept={false} hasReport pending={false} allowSample={false} />);
    for (const expected of ["Live OpenAI review", "Decisions assessment", "outage reported", "Refused", "gpt-6-luna", "123 ms"]) assert.ok(html.includes(expected), expected);
    assert.ok(!html.includes("Show synthetic review example"));
  } finally { globalThis.fetch = original; }
});

test("Responses extraction retains the canonical proposal and exact source evidence", async () => {
  const original = globalThis.fetch;
  const candidate = outageExample();
  const evidence = [{ field_path: "service_overrides.0.status", source_excerpt: "is unavailable" }];
  globalThis.fetch = async (url, init) => {
    assert.equal(String(url), "/api/v1/intelligence/incidents/extract");
    assert.deepEqual(JSON.parse(init?.body as string), { report_text: outageReport });
    return Response.json({ extraction_status: "completed", candidate, evidence, questions: ["Confirm this report."], warnings: [], model: "gpt-6-luna", elapsed_ms: 321 });
  };
  try {
    const result = await createIncidentApiClient().extract(outageReport);
    assert.deepEqual(result.candidate, candidate);
    assert.deepEqual(result.evidence, evidence);
    assert.deepEqual(result.questions, ["Confirm this report."]);
    assert.equal(result.status, "completed");
  } finally { globalThis.fetch = original; }
});

test("unavailable, failed and refused assessments never substitute synthetic flags", async () => {
  const original = globalThis.fetch;
  try {
    for (const status of ["unavailable", "failed", "refused"] as const) {
      const answers = status === "refused" ? ["outage_reported", "multiple_facilities_reported", "resource_loss_reported", "clarification_needed"].map((name) => ({ name, value: null, answer_status: "refused" })) : [];
      globalThis.fetch = async () => Response.json({ assessment_status: status, answers, model: status === "unavailable" ? null : "gpt-6-luna", elapsed_ms: 0, rubric_version: "emergency-review-v1" });
      const result = await createIncidentApiClient().assess(outageReport);
      assert.equal(result.status, status);
      assert.ok(result.answers.every((answer) => answer.value === null));
      assert.ok(!result.message.includes("Synthetic"));
    }
  } finally { globalThis.fetch = original; }
});

test("validation, network and unreadable failures stay local to AI review and are never retried", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  try {
    globalThis.fetch = async () => { ++calls; return Response.json({ error: { fields: [{ field: "report_text", message: "Report must not be blank." }] } }, { status: 422 }); };
    await assert.rejects(createIncidentApiClient().assess(" "), /report_text: Report must not be blank/);
    assert.equal(calls, 1);
    globalThis.fetch = async () => { ++calls; throw new Error("sensitive transport detail"); };
    await assert.rejects(createIncidentApiClient().assess(outageReport), /Could not reach AI review/);
    assert.equal(calls, 2);
    globalThis.fetch = async () => { ++calls; return new Response("not JSON", { status: 502 }); };
    await assert.rejects(createIncidentApiClient().extract(outageReport), /unreadable response/);
    assert.equal(calls, 3);
  } finally { globalThis.fetch = original; }
});

test("plain-text incident server failure exposes recovery guidance and retains uncertain save state", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response("Internal Server Error", { status: 500 });
  try {
    await assert.rejects(createIncidentApiClient().list(), /database connection and apply pending migrations/);
    await assert.rejects(createIncidentApiClient().saveDraft(outageExample()), (error: unknown) => {
      assert.ok(error instanceof Error && "uncertain" in error);
      assert.equal(error.uncertain, true);
      assert.match(error.message, /Refresh saved incidents/);
      return true;
    });
  } finally { globalThis.fetch = original; }
});

test("emergency guidance sends current draft once and renders steps, prerequisites and evidence", async () => {
  const original = globalThis.fetch;
  const incident = outageExample();
  const before = structuredClone(incident);
  let calls = 0;
  globalThis.fetch = async (url, init) => {
    ++calls;
    assert.equal(String(url), "/api/v1/intelligence/incidents/advice");
    assert.equal(init?.method, "POST");
    assert.deepEqual(JSON.parse(init?.body as string), { incident });
    return Response.json(guidance);
  };
  try {
    const response = await requestEmergencyAdvice(incident);
    const html = renderToStaticMarkup(<EmergencyAdviceResult data={response} />);
    for (const expected of ["backup power", "Verify before acting", "Information needed", "Supporting report and hospital data", "gpt-6-luna", "1100 ms"]) assert.ok(html.includes(expected), expected);
    assert.equal(calls, 1);
    assert.deepEqual(incident, before);
  } finally { globalThis.fetch = original; }
});

test("guidance failure states never show proposed actions", () => {
  for (const advice_status of ["unavailable", "failed", "refused"] as const) {
    const data = { ...guidance, advice_status, proposal: null, evidence: [] } as EmergencyAdvice;
    const html = renderToStaticMarkup(<EmergencyAdviceResult data={data} />);
    assert.ok(!html.includes("Verify Hospital B outage scope"));
    assert.ok(html.includes("manually"));
  }
});
