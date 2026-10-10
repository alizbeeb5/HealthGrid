import examples from "./demo-display.json";
import type { components } from "../../lib/api/schema";
import { facilityRequest } from "../../lib/api/facilities";
import type { DecisionSource } from "./model";
export const exampleSources = () => structuredClone(examples.sources) as DecisionSource[];
export async function loadDecisionSource(type: "allocation" | "investment", id: string): Promise<DecisionSource> {
  if (type === "allocation") {
    const run = await facilityRequest<components["schemas"]["AllocationRun"]>(`/api/v1/allocation/runs/${encodeURIComponent(id)}`);
    if (run.allocation_run_id !== id || !run.validation_passed || !run.proposed_summary || !["optimal", "feasible"].includes(run.solver_status)) throw new Error("Choose a saved validated allocation with a proposed summary.");
    return { source_type: type, source_run_id: id, allocation_run_id: null, has_transfer_prerequisite: false, example: false, total_cost_minor_units: run.total_cost_minor_units, expected_at: null, baseline_at: null, expectations: run.proposed_summary.rows.map((row) => ({ facility_id: row.facility_id, capacity: row.estimated_capacity, planned_demand: row.required_service_places })), exclusions: run.coverage.excluded.map((item) => `${item.facility_id}: ${item.reasons.join(", ")}`), actions: run.transfers.map((item) => ({ action_id: item.route_id, title: `${item.quantity} ${item.unit} ${item.resource_id}: ${item.from_facility_id} → ${item.to_facility_id}`, requires_action_ids: [] })), evidence: ["Saved validated allocation; source expectations and actions are frozen.", "Expected date and baseline capture require the decision service when saving; no browser timestamp is invented."] };
  }
  const run = await facilityRequest<components["schemas"]["InvestmentRun"]>(`/api/v1/investments/runs/${encodeURIComponent(id)}`);
  if (run.investment_run_id !== id || !run.validation_passed || !run.proposed_summary || !["optimal", "feasible"].includes(run.solver_status)) throw new Error("Choose a saved validated investment with a proposed summary.");
  return { source_type: type, source_run_id: id, allocation_run_id: run.allocation_run_id, has_transfer_prerequisite: run.assumed_transfers.length > 0, example: false, total_cost_minor_units: run.total_cost_minor_units, expected_at: run.input.evaluation_at, baseline_at: null, expectations: run.proposed_summary.rows.map((row) => ({ facility_id: row.facility_id, capacity: row.estimated_capacity, planned_demand: row.required_service_places })), exclusions: run.coverage.excluded_facilities.map((item) => `${item.facility_id}: ${item.reasons.join(", ")}`), actions: run.selected_projects.map((item) => ({ action_id: item.candidate_id, title: run.input.candidates.find((candidate) => candidate.candidate_id === item.candidate_id)?.name ?? item.candidate_id, requires_action_ids: item.requires_candidate_ids })), evidence: ["Saved investment evaluation date is separate from the human target completion date.", "Proposed operating allowances and optional reported actual payments are separate measures."] };
}

export type DecisionWire = components["schemas"]["DecisionRecord"];
type ReviewWire = components["schemas"]["OutcomeReview"];
type EventRequest = components["schemas"]["DecisionEventRequest"];
type Command = Parameters<import("./preview-client").PreviewStore["event"]>[4];

export function presentDecision(record: DecisionWire, all: DecisionWire[] = []): import("./model").Decision {
  const expected = record.expectation;
  const prerequisite = all.find((item) => item.decision_id === record.prerequisite_decision_id);
  return { ...record, source: { source_type: record.source_type, source_run_id: record.source_run_id, allocation_run_id: prerequisite?.source_run_id ?? null, has_transfer_prerequisite: record.prerequisite_decision_id !== null, example: false, total_cost_minor_units: expected.proposed_cost_minor_units, expected_at: expected.expected_at, baseline_at: expected.baseline_captured_at, expectations: expected.facilities.map((f) => ({ facility_id: f.facility_id, capacity: f.expected_capacity, planned_demand: f.required_service_places })), exclusions: expected.excluded_facilities.map((f) => `${f.facility_id}: ${f.reasons.join(", ")}`), actions: record.actions.map((a) => ({ action_id: a.action_id, title: a.description, requires_action_ids: a.requires_action_ids })), evidence: [`Source engine: ${expected.source_engine_version}; frozen profile: ${expected.requirement.profile_version}`, JSON.stringify(expected)] }, actions: record.actions.map((a) => ({ action_id: a.action_id, title: a.description, requires_action_ids: a.requires_action_ids, status: a.status, note: a.blocker_note ?? a.evidence_note ?? "", occurred_at: a.reported_completed_at, actual_cost_minor_units: a.actual_cost_minor_units, corrections: a.corrections.map((c) => ({ actor: c.actor_name, reason: c.reason, occurred_at: c.previous_completed_at, evidence_note: c.previous_evidence_note ?? "", actual_cost_minor_units: c.previous_actual_cost_minor_units, recorded_at: c.corrected_at, previous: true })) })), events: record.events.map((e) => ({ event_id: e.event_id, type: e.event_type, actor: e.actor_name, note: e.note ?? "", recorded_at: e.recorded_at, occurred_at: e.occurred_at, payload: e.payload })) };
}

export function presentReview(review: ReviewWire): import("./model").OutcomeReview {
  return { ...review, actor: review.actor_name, note: review.note ?? "", window_starts_at: review.observation_window_starts_at, profile_version: review.requirement.profile_version, example: false, comparable_facility_ids: review.coverage.comparable_facility_ids, excluded: review.coverage.excluded_facilities.map((f) => `${f.facility_id}: ${f.reasons.join(", ")}`), rows: review.facilities.map((f) => { const snapshot = review.snapshots.find((s) => s.facility.facility_id === f.facility_id); return { facility_id: f.facility_id, expected: f.expected_capacity, observed: f.observed?.estimated_capacity ?? f.observed_capacity, capacity_difference: f.capacity_difference, classification: f.classification, reasons: f.reasons, service_status: f.observed?.service_status ?? snapshot?.services.find((s) => s.service_id === review.requirement.service_id)?.status, observations: f.evidence.map((e) => { const resource = snapshot?.resources.find((r) => r.resource_id === e.resource_id); return { observation_id: e.observation_id, resource_id: e.resource_id, quantity: e.available_quantity, unit: resource?.unit ?? review.requirement.requirements.find((rule) => rule.resource_id === e.resource_id)?.unit ?? "Unknown unit", observed_at: e.observed_at, recorded_at: resource?.recorded_at ?? null, data_status: e.data_status, evidence_status: e.evidence_status }; }) }; }) };
}

export function decisionEventRequest(version: number, actor: string, note: string, command: Command, requestId: string, occurredAt?: string): EventRequest {
  if (!actor.trim()) throw new Error("Enter a self-reported actor name.");
  if (["approve", "reject", "cancel", "complete", "correct_action_report"].includes(command.type) && !note.trim()) throw new Error("This action requires an explanation.");
  if ("actual_cost_minor_units" in command && command.actual_cost_minor_units !== null && (!Number.isSafeInteger(command.actual_cost_minor_units) || command.actual_cost_minor_units < 0)) throw new Error("Actual cost must be a nonnegative whole USD-cent amount or blank.");
  let payload: EventRequest["payload"];
  switch (command.type) {
    case "edit_draft": payload = { event_type: "edit_draft", title: command.details.title, owner_name: command.details.owner_name, rationale: command.details.rationale, target_completion_at: command.details.target_completion_at }; break;
    case "start": case "complete": payload = { event_type: command.type, occurred_at: occurredAt ?? new Date().toISOString() }; break;
    case "update_action":
      if (!["in_progress", "blocked", "completed"].includes(command.status)) throw new Error("Choose a supported progress status.");
      if (!command.occurred_at) throw new Error("Enter the reported progress time in UTC.");
      if (command.actual_cost_minor_units !== null && (!Number.isSafeInteger(command.actual_cost_minor_units) || command.actual_cost_minor_units < 0)) throw new Error("Actual cost must be a nonnegative whole USD-cent amount or blank.");
      payload = { event_type: "update_action", action_id: command.action_id, status: command.status as "in_progress" | "blocked" | "completed", occurred_at: command.occurred_at, evidence_note: command.evidence_note.trim() || null, actual_cost_minor_units: command.actual_cost_minor_units, blocker_note: command.status === "blocked" ? command.evidence_note.trim() || null : null }; break;
    case "correct_action_report":
      payload = { event_type: "correct_action_report", action_id: command.action_id, reason: note.trim(), completed_at: command.occurred_at || null, evidence_note: command.evidence_note.trim() || null, actual_cost_minor_units: command.actual_cost_minor_units }; break;
    default: payload = { event_type: command.type }; break;
  }
  return { event_type: command.type, expected_version: version, request_id: requestId, actor_name: actor.trim(), note: note.trim() || null, payload };
}

export const listDecisionRecords = () => facilityRequest<components["schemas"]["DecisionListResponse"]>("/api/v1/decisions");
export const getDecisionRecord = (id: string) => facilityRequest<DecisionWire>(`/api/v1/decisions/${encodeURIComponent(id)}`);
export async function createDecision(source: DecisionSource, details: import("./model").DecisionDetails, actor: string): Promise<DecisionWire> {
  const errors = (await import("./model")).validateDetails(details, actor); if (errors.length) throw new Error(errors.join("\n"));
  const request: components["schemas"]["DecisionCreateRequest"] = { ...details, source_type: source.source_type, source_run_id: source.source_run_id, actor_name: actor.trim() };
  return facilityRequest("/api/v1/decisions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) });
}
export const postDecisionEvent = (id: string, request: EventRequest) => facilityRequest<DecisionWire>(`/api/v1/decisions/${encodeURIComponent(id)}/events`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) });
export async function captureReview(id: string, actor: string, note: string, window: string, requestId: string): Promise<import("./model").OutcomeReview> {
  if (!actor.trim() || !window.endsWith("Z") || !Number.isFinite(Date.parse(window))) throw new Error("Enter a reviewer and a valid UTC observation window start.");
  const request: components["schemas"]["OutcomeReviewRequest"] = { actor_name: actor.trim(), note: note.trim() || null, observation_window_starts_at: window, request_id: requestId };
  return presentReview(await facilityRequest<ReviewWire>(`/api/v1/decisions/${encodeURIComponent(id)}/reviews`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) }));
}
export async function getReview(id: string, reviewId: string): Promise<import("./model").OutcomeReview> {
  const review = await facilityRequest<ReviewWire>(`/api/v1/decisions/${encodeURIComponent(id)}/reviews/${encodeURIComponent(reviewId)}`);
  if (review.decision_id !== id || review.review_id !== reviewId) throw new Error("The review does not match the selected decision.");
  return presentReview(review);
}


export async function listReviews(id: string): Promise<import("./model").OutcomeReview[]> {
  const response = await facilityRequest<components["schemas"]["OutcomeReviewListResponse"]>(`/api/v1/decisions/${encodeURIComponent(id)}/reviews`);
  if (response.items.some((review) => review.decision_id !== id)) throw new Error("Review history does not match the selected decision.");
  return response.items.map(presentReview);
}
