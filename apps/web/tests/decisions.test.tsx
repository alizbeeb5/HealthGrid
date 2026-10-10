import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import completed from "../../../contracts/examples/feature-8/decision-completed.response.json";
import supported from "../../../contracts/examples/feature-8/review-supported.response.json";
import insufficient from "../../../contracts/examples/feature-8/review-insufficient-evidence.response.json";
import below from "../../../contracts/examples/feature-8/review-below-expected.response.json";
import type { components } from "../src/lib/api/schema";
import { captureReview, createDecision, decisionEventRequest, getReview, listReviews, postDecisionEvent, presentDecision, presentReview } from "../src/features/decisions/source";
import { OutcomePanel } from "../src/features/decisions/outcome-panel";
import { DecisionDetail } from "../src/features/decisions/decision-detail";
import { FacilityClientError } from "../src/lib/api/facilities";

const record = completed as components["schemas"]["DecisionRecord"];
const review = supported as components["schemas"]["OutcomeReview"];

test("saved decision retains canonical actions, frozen expectations and reported costs", () => {
  const shown = presentDecision(record);
  assert.equal(shown.source.example, false);
  assert.equal(shown.source.expected_at, record.expectation.expected_at);
  assert.equal(shown.source.baseline_at, record.expectation.baseline_captured_at);
  assert.equal(shown.version, record.version);
  assert.deepEqual(shown.actions.map((a) => a.action_id), record.actions.map((a) => a.action_id));
  assert.equal(shown.actions[0].actual_cost_minor_units, record.actions[0].actual_cost_minor_units);
  assert.deepEqual(shown.actions[0].requires_action_ids, record.actions[0].requires_action_ids);
  const html = renderToStaticMarkup(<DecisionDetail decision={shown} all={[shown]} reviews={[]} send={() => {}} disabled={false} open={() => {}} />);
  assert.ok(html.includes("Append-only event timeline"));
  assert.ok(html.includes("Not reviewed"));
});

test("each command uses the discriminated payload and supplied version/idempotency key", () => {
  for (const type of ["submit", "approve", "reject", "cancel"] as const) {
    const request = decisionEventRequest(5, "Planner", "Explanation", { type }, "REQ-1");
    assert.deepEqual(request.payload, { event_type: type });
    assert.equal(request.request_id, "REQ-1"); assert.equal(request.expected_version, 5);
  }
  const progress = decisionEventRequest(5, "Planner", "Progress", { type: "update_action", action_id: "ACT-1", status: "blocked", occurred_at: "2026-10-10T09:00:00Z", evidence_note: "Waiting for delivery", actual_cost_minor_units: null }, "REQ-2");
  assert.equal(progress.payload.event_type, "update_action");
  if (progress.payload.event_type === "update_action") {
    assert.equal(progress.payload.blocker_note, "Waiting for delivery");
    assert.equal(progress.payload.actual_cost_minor_units, null);
  }
  assert.throws(() => decisionEventRequest(1, "Planner", "", { type: "approve" }, "REQ"), /requires an explanation/);
  assert.throws(() => decisionEventRequest(1, "Planner", "", { type: "update_action", action_id: "ACT", status: "in_progress", occurred_at: null, evidence_note: "Started", actual_cost_minor_units: null }, "REQ"), /reported progress time/);
});

test("create and event writes submit once using backend field names", async () => {
  const original = globalThis.fetch; const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (url, init) => { calls.push({ url: String(url), init }); return Response.json(record); };
  try {
    const shown = presentDecision(record);
    await createDecision(shown.source, { title: record.title, owner_name: record.owner_name, rationale: record.rationale, target_completion_at: record.target_completion_at, prerequisite_decision_id: record.prerequisite_decision_id, supersedes_decision_id: null }, "Planner");
    const body = JSON.parse(calls[0].init?.body as string);
    assert.equal(calls[0].url, "/api/v1/decisions"); assert.equal(body.source_run_id, record.source_run_id);
    assert.equal(body.actor_name, "Planner"); assert.equal(body.prerequisite_decision_id, record.prerequisite_decision_id);
    const event = decisionEventRequest(2, "Planner", "Approved", { type: "approve" }, "REQ-APPROVE");
    await postDecisionEvent(record.decision_id, event);
    assert.deepEqual(JSON.parse(calls[1].init?.body as string), event); assert.equal(calls.length, 2);
  } finally { globalThis.fetch = original; }
});

test("capture uses an explicit window and server capture time; reopen is GET only", async () => {
  const original = globalThis.fetch; const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (url, init) => { calls.push({ url: String(url), init }); return Response.json(review); };
  try {
    const result = await captureReview(record.decision_id, "Reviewer", "Follow-up", review.observation_window_starts_at, "REQ-CAPTURE");
    const body = JSON.parse(calls[0].init?.body as string);
    assert.equal(body.observation_window_starts_at, review.observation_window_starts_at);
    assert.equal(body.request_id, "REQ-CAPTURE"); assert.ok(!("captured_at" in body));
    assert.equal(result.captured_at, review.captured_at);
    assert.deepEqual(await getReview(record.decision_id, review.review_id), result);
    assert.equal(calls[1].init?.method, undefined); assert.equal(calls.length, 2);
  } finally { globalThis.fetch = original; }
});

test("review display preserves limited services, receipt times and source exclusion", () => {
  const result = presentReview(review);
  assert.equal(result.rows[0].service_status, "limited"); assert.equal(result.rows[0].observed, null);
  assert.equal(result.rows[1].observed, 8); assert.equal(result.rows[1].capacity_difference, 0);
  assert.equal(result.rows[1].observations[0].recorded_at, review.snapshots[1].resources[0].recorded_at);
  assert.deepEqual(result.comparable_facility_ids, ["DEMO-B"]);
  const html = renderToStaticMarkup(<OutcomePanel review={result} />);
  assert.ok(html.includes("Saved outcome review")); assert.ok(html.includes("Captured service status: limited"));
  assert.ok(html.includes("DEMO-C")); assert.ok(!html.includes("no live report capture"));
});

for (const fixture of [insufficient, below]) {
  test(`${fixture.facilities[1].classification} preserves unknown or signed shortfall`, () => {
    const result = presentReview(fixture as components["schemas"]["OutcomeReview"]);
    const b = result.rows[1];
    assert.equal(b.observed, fixture.facilities[1].observed_capacity);
    assert.equal(b.capacity_difference, fixture.facilities[1].capacity_difference);
    if (b.observed === null) {
      assert.ok(b.observations.some((o) => o.evidence_status === "outside_window"));
      assert.ok(renderToStaticMarkup(<OutcomePanel review={result} />).includes("Unknown"));
    } else { assert.equal(b.observed, 6); assert.equal(b.capacity_difference, -2); }
  });
}

test("version/field errors stay visible and failed writes never retry or load previews", async () => {
  const original = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({ error: { message: "Refresh the changed decision", fields: [{ field: "expected_version", message: "Version changed" }], current_version: 7, existing_decision_id: null, code: "version_conflict" } }, { status: 409 }); };
  try {
    const request = decisionEventRequest(3, "Planner", "Approved", { type: "approve" }, "REQ");
    await assert.rejects(postDecisionEvent(record.decision_id, request), (error: unknown) => error instanceof FacilityClientError && error.status === 409 && error.detail?.fields[0].field === "expected_version");
    assert.equal(calls, 1);
    globalThis.fetch = async () => { calls++; throw new Error("Disconnected"); };
    await assert.rejects(postDecisionEvent(record.decision_id, request), /save could not be confirmed/);
    assert.equal(calls, 2);
  } finally { globalThis.fetch = original; }
});

test("a review for a different decision is rejected", async () => {
  const original = globalThis.fetch; globalThis.fetch = async () => Response.json(review);
  try { await assert.rejects(getReview("OTHER", review.review_id), /does not match/); }
  finally { globalThis.fetch = original; }
});


test("saved review history uses GET and preserves frozen classifications", async () => {
  const original = globalThis.fetch; let calls = 0;
  globalThis.fetch = async (url, init) => {
    calls++; assert.equal(url, `/api/v1/decisions/${record.decision_id}/reviews`);
    assert.equal(init?.method, undefined); return Response.json({ items: [review] });
  };
  try { assert.deepEqual(await listReviews(record.decision_id), [presentReview(review)]); assert.equal(calls, 1); }
  finally { globalThis.fetch = original; }
});
