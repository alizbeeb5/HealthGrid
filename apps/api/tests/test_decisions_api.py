"""Feature 8 backend: decisions, legal transitions, prerequisites, idempotency, version
checks, duplicate-source prevention and immutable outcome reviews.

Source proposals come from the real Feature 6 allocation and Feature 7 investment
engines, so these tests also cover the proposal -> decision handoff.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.modules.capacity import service as capacity_service
from app.modules.decisions import repository as decision_repository
from app.modules.decisions import service as decisions_service
from app.modules.decisions import transitions
from app.modules.decisions.models import Decision as DecisionRow
from app.modules.decisions.models import OutcomeReview as ReviewRow
from app.modules.decisions.schemas import (
    DecisionEventRequest,
    DecisionRecord,
    OutcomeEvaluationResult,
    OutcomeReview,
)
from app.modules.facilities.models import ResourceObservation

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "examples"
EXAMPLES = CONTRACTS / "feature-8"
URL = "/api/v1/decisions"
REVIEW_FIELDS = {"review_id", "decision_id", "source_type", "source_run_id", "request_id",
                 "actor_name", "identity_mode", "note", "captured_at",
                 "observation_window_starts_at", "expected_at", "target_completion_at",
                 "decision_status", "decision_version", "requirement", "snapshots",
                 "schema_version"}
ENGINE_READY = decisions_service.outcome_evaluator() is not None
GENERATED = re.compile(r"\b(DEC|EVT|ALLOC|INVRUN|INC|REVIEW|REV|BASE|RUN)-[A-Za-z0-9-]+")


def example(name: str, feature: str = "feature-8"):
    return json.loads((CONTRACTS / feature / name).read_text(encoding="utf-8"))


def normalized(body) -> dict:
    """Replace generated IDs (and readable example IDs) with their prefixes."""
    return json.loads(GENERATED.sub(lambda m: f"{m.group(1)}-X", json.dumps(body)))


def at(clock, text: str) -> None:
    clock.now = datetime.fromisoformat(text.replace("Z", "+00:00"))


def ok(response, code: int = 201) -> dict:
    assert response.status_code == code, response.text
    return response.json()


@pytest.fixture(autouse=True)
def fresh_profiles():
    capacity_service._load_profiles.cache_clear()
    yield
    capacity_service._load_profiles.cache_clear()


@pytest.fixture
def sources(client, clock) -> dict:
    """Features 5-7 demo proposals, from the real allocation and investment engines."""
    incident = example("incident.request.json", "feature-6")
    draft = ok(client.post("/api/v1/scenarios/incidents", json=incident))
    at(clock, "2026-10-10T09:05:00Z")
    confirmed = ok(client.post(f"/api/v1/scenarios/incidents/{draft['incident_id']}/confirm",
                               json={"draft_revision_id": draft["revision_id"],
                                     "input": incident, "confirmed_by": "Demo planner"}))
    at(clock, "2026-10-10T09:06:00Z")
    sim = ok(client.post(f"/api/v1/scenarios/incidents/{draft['incident_id']}/revisions/"
                         f"{confirmed['revision_id']}/simulate"))
    at(clock, "2026-10-10T09:15:00Z")
    alloc = ok(client.post("/api/v1/allocation/runs", json={
        **example("improved.request.json", "feature-6"), "simulation_run_id": sim["run_id"]}))
    at(clock, "2026-10-10T09:30:00Z")
    inv = ok(client.post("/api/v1/investments/runs", json={
        **example("improved.request.json", "feature-7"),
        "allocation_run_id": alloc["allocation_run_id"]}))
    return {"simulation": sim, "allocation": alloc, "investment": inv}


def create_allocation_decision(client, sources) -> dict:
    return ok(client.post(URL, json={
        "source_type": "allocation", "source_run_id": sources["allocation"]["allocation_run_id"],
        "title": "Move one monitor from Demo Hospital A to B",
        "owner_name": "Logistics lead (demo)",
        "rationale": "Closes one modeled place at B while A keeps its planned demand.",
        "target_completion_at": "2026-10-10T11:00:00Z", "actor_name": "Demo planner",
        "prerequisite_decision_id": None, "supersedes_decision_id": None}))


def create_investment_decision(client, sources, prerequisite_id, **changes) -> dict:
    body = {**example("decision-create.request.json"),
            "source_run_id": sources["investment"]["investment_run_id"],
            "prerequisite_decision_id": prerequisite_id, **changes}
    return client.post(URL, json=body)


def send(client, decision, event_type, request_id, payload=None, note=None,
         actor="Demo planner", version=None):
    return client.post(f"{URL}/{decision['decision_id']}/events", json={
        "event_type": event_type, "expected_version": version or decision["version"],
        "request_id": request_id, "actor_name": actor, "note": note,
        "payload": {"event_type": event_type, **(payload or {})}})


def action(action_id, status, occurred_at, **extra):
    return {"action_id": action_id, "status": status, "occurred_at": occurred_at,
            "evidence_note": None, "actual_cost_minor_units": None, "blocker_note": None,
            **extra}


def run_allocation_decision(client, clock, sources) -> dict:
    """Record, approve and report-complete the transfer decision."""
    at(clock, "2026-10-10T09:40:00Z")
    d = create_allocation_decision(client, sources)
    d = ok(send(client, d, "submit", "REQ-T-SUBMIT"))
    d = ok(send(client, d, "approve", "REQ-T-APPROVE", note="Approved.",
                actor="Regional director (demo)"))
    at(clock, "2026-10-10T09:50:00Z")
    d = ok(send(client, d, "start", "REQ-T-START", {"occurred_at": "2026-10-10T09:45:00Z"}))
    transfer = d["actions"][0]["action_id"]
    d = ok(send(client, d, "update_action", "REQ-T-ACT-START",
                action(transfer, "in_progress", "2026-10-10T09:46:00Z")))
    at(clock, "2026-10-10T10:20:00Z")
    d = ok(send(client, d, "update_action", "REQ-T-ACT-DONE", action(
        transfer, "completed", "2026-10-10T10:15:00Z",
        evidence_note="Monitor received and installed at B (demo report).",
        actual_cost_minor_units=9500)))
    return ok(send(client, d, "complete", "REQ-T-COMPLETE",
                   {"occurred_at": "2026-10-10T10:20:00Z"}, note="Transfer reported completed."))


REPAIR, COMMISSION = "ACT-INV-B-REPAIR-5-IDLE", "ACT-INV-B-COMMISSION-5-REPAIRED"


def run_investment_decision(client, clock, sources, transfer) -> dict:
    """The shared demo journey, keyed to the published examples."""
    at(clock, "2026-10-10T10:30:00Z")
    d = ok(create_investment_decision(client, sources, transfer["decision_id"]))
    stages = {"draft": d}
    d = ok(send(client, d, "submit", "REQ-R-SUBMIT"))
    d = ok(send(client, d, "approve", "REQ-R-APPROVE", note="Within budget; approved.",
                actor="Regional director (demo)"))
    stages["approved"] = d
    at(clock, "2026-10-10T11:00:00Z")
    d = ok(send(client, d, "start", "REQ-R-START", {"occurred_at": "2026-10-10T11:00:00Z"}))
    engineer = "Biomedical engineer (demo)"
    d = ok(send(client, d, "update_action", "REQ-R-REPAIR-START",
                action(REPAIR, "in_progress", "2026-10-10T11:00:00Z"), actor=engineer))
    at(clock, "2026-10-12T09:00:00Z")
    d = ok(send(client, d, "update_action", "REQ-R-REPAIR-BLOCKED", action(
        REPAIR, "blocked", "2026-10-12T09:00:00Z",
        blocker_note="Replacement power boards delayed by the supplier (demo)."),
        actor=engineer))
    stages["blocked"] = d
    at(clock, "2026-10-13T09:00:00Z")
    d = ok(send(client, d, "update_action", "REQ-R-REPAIR-RESUME",
                action(REPAIR, "in_progress", "2026-10-13T09:00:00Z"), actor=engineer))
    at(clock, "2026-10-17T12:00:00Z")
    d = ok(send(client, d, "update_action", "REQ-R-REPAIR-DONE", action(
        REPAIR, "completed", "2026-10-17T11:00:00Z",
        evidence_note="Five monitors repaired; awaiting commissioning (demo report).",
        actual_cost_minor_units=95000), actor=engineer))
    d = ok(send(client, d, "update_action", "REQ-R-COMMISSION-START",
                action(COMMISSION, "in_progress", "2026-10-17T12:00:00Z"), actor=engineer))
    at(clock, "2026-10-20T12:00:00Z")
    d = ok(send(client, d, "update_action", "REQ-R-COMMISSION-DONE", action(
        COMMISSION, "completed", "2026-10-20T11:00:00Z",
        evidence_note="Five repaired monitors commissioned (demo report)."), actor=engineer))
    stages["completed"] = ok(send(client, d, "complete", "REQ-R-COMPLETE",
                                  {"occurred_at": "2026-10-20T12:00:00Z"},
                                  note="All package actions reported completed."))
    return stages


@pytest.fixture
def journey(client, clock, sources) -> dict:
    transfer = run_allocation_decision(client, clock, sources)
    return {"transfer": transfer, **run_investment_decision(client, clock, sources, transfer)}


def observation_count(engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(ResourceObservation))


# Contract examples.


@pytest.mark.parametrize("name", ["decision-draft", "decision-approved", "decision-blocked",
                                  "decision-completed"])
def test_decision_examples_match_schema(name):
    payload = example(f"{name}.response.json")
    assert DecisionRecord.model_validate(payload).model_dump(mode="json") == payload


@pytest.mark.parametrize("name", ["review-insufficient-evidence", "review-supported",
                                  "review-below-expected"])
def test_review_examples_match_schema(name):
    payload = example(f"{name}.response.json")
    assert OutcomeReview.model_validate(payload).model_dump(mode="json") == payload


def test_review_examples_tell_the_demo_story():
    rows = {name: {f["facility_id"]: f for f in example(f"review-{name}.response.json")
                   ["facilities"]}
            for name in ("insufficient-evidence", "supported", "below-expected")}
    assert rows["insufficient-evidence"]["DEMO-B"]["classification"] == "insufficient_evidence"
    assert example("review-insufficient-evidence.response.json")["decision_status"] == (
        "completed")  # reported completion is not evidence
    b = rows["supported"]["DEMO-B"]
    assert (b["classification"], b["observed_capacity"], b["capacity_difference"]) == (
        "at_or_above_expected", 8, 0)
    b = rows["below-expected"]["DEMO-B"]
    assert (b["classification"], b["observed_capacity"], b["capacity_difference"]) == (
        "below_expected", 6, -2)


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(event_type="submit"),  # payload type must match
        lambda p: p.update(note=None),  # approval needs an explanation
        lambda p: p.update(expected_version=0),
        lambda p: p["payload"].update(extra=True),
    ],
)
def test_malformed_event_requests_are_rejected(change):
    body = example("decision-event.request.json")
    change(body)
    with pytest.raises(ValidationError):
        DecisionEventRequest.model_validate(body)


# The shared journey.


def test_journey_reproduces_examples(journey):
    for stage in ("draft", "approved", "blocked", "completed"):
        assert normalized(journey[stage]) == normalized(
            example(f"decision-{stage}.response.json")), stage


def test_saved_decisions_reopen_unchanged(client, journey):
    for key in ("transfer", "completed"):
        decision = journey[key]
        assert ok(client.get(f"{URL}/{decision['decision_id']}"), 200) == decision
    listed = ok(client.get(URL, params={"status": "completed"}), 200)["items"]
    assert {d["decision_id"] for d in listed} == {journey["transfer"]["decision_id"],
                                                  journey["completed"]["decision_id"]}


def test_approval_and_completion_never_change_inventory(client, clock, sources, engine):
    def inventory():
        resources = ok(client.get("/api/v1/facilities/DEMO-B/snapshot"), 200)["resources"]
        return [(r["observation_id"], r["available_quantity"]) for r in resources]

    before_count, before = observation_count(engine), inventory()
    transfer = run_allocation_decision(client, clock, sources)
    run_investment_decision(client, clock, sources, transfer)
    assert observation_count(engine) == before_count
    assert inventory() == before  # freshness ages with time; reports are unchanged


def test_expectation_is_frozen_from_the_source(journey, sources):
    expectation = journey["completed"]["expectation"]
    assert expectation["expected_at"] == sources["investment"]["input"]["evaluation_at"]
    expected = {f["facility_id"]: f["expected_capacity"] for f in expectation["facilities"]}
    assert expected == {"DEMO-A": 3, "DEMO-B": 8}
    assert (expectation["proposed_cost_minor_units"],
            expectation["proposed_capital_cost_minor_units"],
            expectation["proposed_operating_cost_minor_units"]) == (240000, 150000, 90000)
    transfer = journey["transfer"]["expectation"]
    assert transfer["expected_at"] == "2026-10-10T11:00:00Z"  # incident start + 60 minutes


# Transitions.


def test_invalid_transitions_conflict(client, clock, sources):
    d = create_allocation_decision(client, sources)
    assert ok(send(client, d, "approve", "R1", note="x"), 409)["error"]["code"] == (
        "invalid_transition")
    assert ok(send(client, d, "start", "R2", {"occurred_at": "2026-10-10T09:30:00Z"}),
              409)["error"]["code"] == "invalid_transition"
    d = ok(send(client, d, "submit", "R3"))
    edit = {"title": "New title", "owner_name": None, "rationale": None,
            "target_completion_at": None}
    assert ok(send(client, d, "edit_draft", "R4", edit), 409)["error"]["code"] == (
        "invalid_transition")
    d = ok(send(client, d, "reject", "R5", note="Not now."))
    assert d["status"] == "rejected"
    assert ok(send(client, d, "submit", "R6"), 409)["error"]["code"] == "invalid_transition"


def test_draft_edits_apply_only_to_drafts(client, sources):
    d = create_allocation_decision(client, sources)
    d = ok(send(client, d, "edit_draft", "R1", {
        "title": "Edited", "owner_name": None, "rationale": None,
        "target_completion_at": None}))
    assert d["title"] == "Edited" and d["owner_name"] == "Logistics lead (demo)"
    assert d["events"][-1]["event_type"] == "edit_draft" and d["version"] == 2


def test_explanations_are_required(client, sources):
    d = create_allocation_decision(client, sources)
    response = send(client, d, "cancel", "R1")
    assert response.status_code == 422
    assert response.json()["error"]["fields"][0]["field"] == ""


def test_action_rules(client, clock, sources):
    d = run_allocation_decision(client, clock, sources)  # completed decision
    transfer = d["actions"][0]["action_id"]
    reopen = send(client, d, "update_action", "R1",
                  action(transfer, "in_progress", "2026-10-10T10:20:00Z"))
    assert ok(reopen, 409)["error"]["code"] == "invalid_transition"


def test_complete_requires_every_action(client, clock, sources):
    at(clock, "2026-10-10T09:40:00Z")
    d = create_allocation_decision(client, sources)
    d = ok(send(client, d, "submit", "R1"))
    d = ok(send(client, d, "approve", "R2", note="ok"))
    d = ok(send(client, d, "start", "R3", {"occurred_at": "2026-10-10T09:40:00Z"}))
    response = send(client, d, "complete", "R4", {"occurred_at": "2026-10-10T09:40:00Z"},
                    note="done")
    assert ok(response, 409)["error"]["code"] == "prerequisite_not_met"


def test_execution_times_cannot_be_future_or_out_of_order(client, clock, sources):
    at(clock, "2026-10-10T09:40:00Z")
    d = create_allocation_decision(client, sources)
    d = ok(send(client, d, "submit", "R1"))
    d = ok(send(client, d, "approve", "R2", note="ok"))
    future = send(client, d, "start", "R3", {"occurred_at": "2026-10-10T10:00:00Z"})
    assert future.status_code == 422
    assert future.json()["error"]["fields"][0]["field"] == "payload.occurred_at"
    d = ok(send(client, d, "start", "R4", {"occurred_at": "2026-10-10T09:40:00Z"}))
    transfer = d["actions"][0]["action_id"]
    d = ok(send(client, d, "update_action", "R5",
                action(transfer, "in_progress", "2026-10-10T09:40:00Z")))
    backwards = send(client, d, "update_action", "R6", action(
        transfer, "completed", "2026-10-10T09:30:00Z", evidence_note="done"))
    assert backwards.status_code == 422


def test_cancel_preserves_completed_actions(client, clock, sources):
    transfer = run_allocation_decision(client, clock, sources)
    at(clock, "2026-10-10T10:30:00Z")
    d = ok(create_investment_decision(client, sources, transfer["decision_id"]))
    d = ok(send(client, d, "submit", "R1"))
    d = ok(send(client, d, "approve", "R2", note="ok"))
    at(clock, "2026-10-10T11:00:00Z")
    d = ok(send(client, d, "start", "R3", {"occurred_at": "2026-10-10T11:00:00Z"}))
    d = ok(send(client, d, "update_action", "R4", action(REPAIR, "in_progress",
                                                         "2026-10-10T11:00:00Z")))
    d = ok(send(client, d, "update_action", "R5", action(
        REPAIR, "completed", "2026-10-10T11:00:00Z", evidence_note="Repaired.")))
    d = ok(send(client, d, "cancel", "R6", note="Funding withdrawn."))
    statuses = {a["action_id"]: a["status"] for a in d["actions"]}
    assert statuses == {REPAIR: "completed", COMMISSION: "cancelled"}
    assert d["status"] == "cancelled"


def test_corrections_append_and_preserve_previous_values(client, clock, sources):
    d = run_allocation_decision(client, clock, sources)
    transfer = d["actions"][0]["action_id"]
    corrected = ok(send(client, d, "correct_action_report", "R1", {
        "action_id": transfer, "reason": "Invoice showed the actual cost.",
        "completed_at": None, "evidence_note": None, "actual_cost_minor_units": 9800}))
    item = corrected["actions"][0]
    assert item["actual_cost_minor_units"] == 9800
    assert item["corrections"][0]["previous_actual_cost_minor_units"] == 9500
    assert corrected["status"] == "completed"  # corrections never change the state


# Prerequisites and sources.


def test_investment_needs_its_allocation_prerequisite(client, clock, sources):
    missing = create_investment_decision(client, sources, None)
    assert ok(missing, 422)["error"]["fields"][0]["field"] == "prerequisite_decision_id"
    at(clock, "2026-10-10T09:40:00Z")
    transfer = create_allocation_decision(client, sources)
    d = ok(create_investment_decision(client, sources, transfer["decision_id"]))
    d = ok(send(client, d, "submit", "R1"))
    d = ok(send(client, d, "approve", "R2", note="ok"))
    early = send(client, d, "start", "R3", {"occurred_at": "2026-10-10T09:40:00Z"})
    assert ok(early, 409)["error"]["code"] == "prerequisite_not_met"


def test_action_dependencies_are_enforced(client, clock, sources):
    transfer = run_allocation_decision(client, clock, sources)
    at(clock, "2026-10-10T10:30:00Z")
    d = ok(create_investment_decision(client, sources, transfer["decision_id"]))
    d = ok(send(client, d, "submit", "R1"))
    d = ok(send(client, d, "approve", "R2", note="ok"))
    at(clock, "2026-10-10T11:00:00Z")
    d = ok(send(client, d, "start", "R3", {"occurred_at": "2026-10-10T11:00:00Z"}))
    response = send(client, d, "update_action", "REQ-R-COMMISSION-EARLY",
                    action(COMMISSION, "in_progress", "2026-10-10T11:00:00Z"),
                    actor="Biomedical engineer (demo)")
    assert normalized(ok(response, 409)) == normalized(
        example("prerequisite-not-met.response.json"))


def test_allocation_decisions_take_no_prerequisite(client, sources):
    response = client.post(URL, json={
        **example("decision-create.request.json"), "source_type": "allocation",
        "source_run_id": sources["allocation"]["allocation_run_id"],
        "prerequisite_decision_id": "DEC-X"})
    assert ok(response, 422)["error"]["fields"][0]["field"] == "prerequisite_decision_id"


def test_missing_and_ineligible_sources(client, sources):
    body = {**example("decision-create.request.json"), "prerequisite_decision_id": None}
    missing = client.post(URL, json={**body, "source_run_id": "INVRUN-X"})
    assert ok(missing, 404)["error"]["code"] == "source_run_not_found"
    needs = ok(client.post("/api/v1/allocation/runs", json={
        **example("needs-inputs.request.json", "feature-6"),
        "simulation_run_id": sources["simulation"]["run_id"]}))
    ineligible = client.post(URL, json={**body, "source_type": "allocation",
                                        "source_run_id": needs["allocation_run_id"]})
    assert ok(ineligible, 422)["error"]["fields"][0]["field"] == "source_run_id"
    assert ok(client.get(f"{URL}/DEC-X"), 404)["error"]["code"] == "decision_not_found"


def test_no_improvement_source_completes_without_actions(client, clock, sources):
    none = ok(client.post("/api/v1/allocation/runs", json={
        **example("no-improvement.request.json", "feature-6"),
        "simulation_run_id": sources["simulation"]["run_id"]}))
    at(clock, "2026-10-10T09:40:00Z")
    d = ok(client.post(URL, json={
        "source_type": "allocation", "source_run_id": none["allocation_run_id"],
        "title": "Make no transfer", "owner_name": "Planner (demo)",
        "rationale": "No affordable transfer improves coverage.",
        "target_completion_at": "2026-10-10T11:00:00Z", "actor_name": "Planner (demo)",
        "prerequisite_decision_id": None, "supersedes_decision_id": None}))
    assert d["actions"] == []
    d = ok(send(client, d, "submit", "R1"))
    d = ok(send(client, d, "approve", "R2", note="Accept no action."))
    d = ok(send(client, d, "complete", "R3", {"occurred_at": "2026-10-10T09:40:00Z"},
                note="Recorded decision to take no action."))
    assert d["status"] == "completed"


# Duplicates, versions and retries.


def test_duplicate_source_and_superseding(client, sources):
    first = create_allocation_decision(client, sources)
    again = {
        "source_type": "allocation", "source_run_id": sources["allocation"]["allocation_run_id"],
        "title": "Again", "owner_name": "x", "rationale": "x",
        "target_completion_at": "2026-10-10T11:00:00Z", "actor_name": "x",
        "prerequisite_decision_id": None, "supersedes_decision_id": None}
    error = ok(client.post(URL, json=again), 409)["error"]
    assert (error["code"], error["existing_decision_id"]) == (
        "duplicate_source_decision", first["decision_id"])
    superseding = {**again, "supersedes_decision_id": first["decision_id"]}
    early = client.post(URL, json=superseding)
    assert ok(early, 409)["error"]["code"] == "invalid_transition"  # first is still active
    ok(send(client, first, "cancel", "R1", note="Reconsider."))
    second = ok(client.post(URL, json=superseding))
    assert second["supersedes_decision_id"] == first["decision_id"]
    assert ok(client.get(f"{URL}/{first['decision_id']}"), 200)["status"] == "cancelled"


def test_concurrent_creation_hits_the_unique_index(client, sources, engine, monkeypatch):
    first = create_allocation_decision(client, sources)
    calls = []
    original = decision_repository.active_for_source

    def stale_check(db, source_type, source_run_id):
        calls.append(1)
        return None if len(calls) == 1 else original(db, source_type, source_run_id)

    monkeypatch.setattr(decision_repository, "active_for_source", stale_check)
    response = client.post(URL, json={
        "source_type": "allocation", "source_run_id": sources["allocation"]["allocation_run_id"],
        "title": "Racing", "owner_name": "x", "rationale": "x",
        "target_completion_at": "2026-10-10T11:00:00Z", "actor_name": "x",
        "prerequisite_decision_id": None, "supersedes_decision_id": None})
    error = ok(response, 409)["error"]
    assert error["existing_decision_id"] == first["decision_id"]
    assert len(calls) == 2  # the second lookup runs only after the IntegrityError
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(DecisionRow)) == 1


def test_retries_versions_and_idempotency(client, sources):
    d = create_allocation_decision(client, sources)
    first = send(client, d, "submit", "REQ-1")
    assert first.status_code == 201
    replay = send(client, d, "submit", "REQ-1")  # same request, stale version: still a replay
    assert replay.status_code == 200 and replay.json() == first.json()
    assert ok(client.get(f"{URL}/{d['decision_id']}"), 200)["version"] == 2
    changed = send(client, d, "submit", "REQ-1", note="different")
    assert ok(changed, 409)["error"]["code"] == "idempotency_conflict"
    stale = send(client, d, "approve", "REQ-2", note="ok", version=1)
    error = ok(stale, 409)["error"]
    assert (error["code"], error["current_version"]) == ("version_conflict", 2)


def test_concurrent_update_conflicts_instead_of_overwriting(client, sources, engine,
                                                            monkeypatch):
    d = create_allocation_decision(client, sources)
    original = transitions.apply

    def racing_apply(record, command, now, prerequisite_status):
        with Session(engine) as other:  # another request commits first
            row = other.get(DecisionRow, record.decision_id)
            row.updated_at = now + timedelta(seconds=1)  # a real change bumps the version
            other.commit()
        return original(record, command, now, prerequisite_status)

    monkeypatch.setattr(transitions, "apply", racing_apply)
    response = send(client, d, "submit", "REQ-RACE")
    assert ok(response, 409)["error"]["code"] == "version_conflict"


# Outcome reviews.


class StubEvaluator:
    """Returns the published insufficient-evidence result for its matching state."""

    def __init__(self):
        self.calls = []

    def __call__(self, inputs):
        self.calls.append(inputs)
        payload = {k: v for k, v in example("review-insufficient-evidence.response.json")
                   .items() if k not in REVIEW_FIELDS}
        return OutcomeEvaluationResult.model_validate(payload)


@pytest.fixture
def stub_evaluator(monkeypatch) -> StubEvaluator:
    stub = StubEvaluator()
    monkeypatch.setattr(decisions_service, "outcome_evaluator", lambda: stub)
    return stub


@pytest.fixture
def server_errors(client) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def review(client, decision, request_id="REQ-REVIEW-1", **changes):
    return client.post(f"{URL}/{decision['decision_id']}/reviews",
                       json={**example("review.request.json"), "request_id": request_id,
                             **changes})


def test_review_captures_and_reopens_unchanged(client, clock, journey, stub_evaluator):
    at(clock, "2026-11-10T09:00:00Z")
    saved = ok(review(client, journey["completed"]))
    assert normalized(saved) == normalized(example("review-insufficient-evidence.response.json"))
    [inputs] = stub_evaluator.calls
    assert inputs.expected_at.isoformat() == "2026-11-09T11:00:00+00:00"
    assert inputs.target_completion_at.isoformat() == "2026-10-21T00:00:00+00:00"
    assert [f.expected_capacity for f in inputs.facilities] == [3, 8]
    assert inputs.requirement.profile_version == "demo-v1"
    url = f"{URL}/{journey['completed']['decision_id']}/reviews/{saved['review_id']}"
    assert ok(client.get(url), 200) == saved
    replay = review(client, journey["completed"])
    assert replay.status_code == 200 and replay.json() == saved
    conflict = review(client, journey["completed"], note="different")
    assert ok(conflict, 409)["error"]["code"] == "idempotency_conflict"


def test_review_rules(client, clock, sources, journey, stub_evaluator, engine):
    at(clock, "2026-11-10T09:00:00Z")
    before = review(client, journey["completed"], "R1",
                    observation_window_starts_at="2026-10-01T00:00:00Z")
    assert ok(before, 422)["error"]["fields"][0]["field"] == "observation_window_starts_at"
    after = review(client, journey["completed"], "R2",
                   observation_window_starts_at="2026-11-11T00:00:00Z")
    assert after.status_code == 422
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ReviewRow)) == 0
    url = f"{URL}/{journey['completed']['decision_id']}/reviews/REVIEW-X"
    assert ok(client.get(url), 404)["error"]["code"] == "review_not_found"


def test_draft_decisions_cannot_be_reviewed(client, clock, sources, stub_evaluator):
    at(clock, "2026-10-10T09:40:00Z")
    d = create_allocation_decision(client, sources)
    assert ok(review(client, d, observation_window_starts_at="2026-10-10T09:10:00Z"),
              409)["error"]["code"] == "invalid_transition"


def test_missing_outcome_engine_is_a_server_error(server_errors, clock, journey, engine,
                                                  monkeypatch):
    monkeypatch.setattr(decisions_service, "outcome_evaluator", lambda: None)
    at(clock, "2026-11-10T09:00:00Z")
    assert review(server_errors, journey["completed"]).status_code == 500
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ReviewRow)) == 0


def _evaluation(mutate):
    payload = {k: v for k, v in example("review-insufficient-evidence.response.json").items()
               if k not in REVIEW_FIELDS}
    mutate(payload)
    return OutcomeEvaluationResult.model_validate(payload)


def _claim_comparable(p):
    b = p["facilities"][1]
    b.update(classification="at_or_above_expected", observed_capacity=8, capacity_difference=0,
             unmet_against_planned_demand=0, reasons=[])
    p["coverage"].update(comparable_facility_ids=["DEMO-B"],
                         not_comparable_facility_ids=["DEMO-A"])
    p["reasons"] = []


@pytest.mark.parametrize(
    ("mutate", "problem"),
    [
        (lambda p: None, None),
        (lambda p: p["facilities"][1]["evidence"][0].update(evidence_status="fresh"),
         "does not match the captured report"),
        (lambda p: p["facilities"][1].update(expected_capacity=7), "frozen plan"),
        (lambda p: p.update(captured_offset_minutes=0), "captured_offset_minutes"),
        (_claim_comparable, "without fresh in-window evidence"),
        (lambda p: p["coverage"].update(excluded_facilities=[]), "Excluded facilities"),
    ],
)
def test_check_outcome_flags_each_violation(client, clock, journey, stub_evaluator, mutate,
                                            problem):
    at(clock, "2026-11-10T09:00:00Z")
    review(client, journey["completed"])
    inputs = stub_evaluator.calls[0]

    problems = decisions_service.check_outcome(inputs, _evaluation(mutate))

    if problem is None:
        assert problems == []
    else:
        assert any(problem in p for p in problems), problems


# Integration with the real outcome engine (data/evaluation owner).

needs_engine = pytest.mark.skipif(
    not ENGINE_READY, reason="engines.outcomes.evaluate_outcome not merged yet")


def report(client, facility, resource, quantity, unit, observed_at):
    ok(client.post(f"/api/v1/facilities/{facility}/observations", json={
        "resource_id": resource, "available_quantity": quantity, "unit": unit,
        "observed_at": observed_at}))


@needs_engine
def test_real_engine_reproduces_the_three_reviews(client, clock, journey):
    decision = journey["completed"]
    at(clock, "2026-11-10T09:00:00Z")
    first = ok(review(client, decision, "REQ-REVIEW-1"))
    assert normalized(first) == normalized(
        example("review-insufficient-evidence.response.json"))
    at(clock, "2026-11-10T09:05:00Z")
    for facility, beds, nurses, monitors in (("DEMO-A", 12, 6, 3), ("DEMO-B", 18, 9, 8)):
        report(client, facility, "available-beds", beds, "bed", "2026-11-10T08:00:00Z")
        report(client, facility, "nurses-on-duty", nurses, "person", "2026-11-10T08:00:00Z")
        report(client, facility, "working-monitors", monitors, "item", "2026-11-10T08:00:00Z")
    at(clock, "2026-11-10T09:10:00Z")
    second = ok(review(client, decision, "REQ-REVIEW-2"))
    at(clock, "2026-11-10T09:15:00Z")
    report(client, "DEMO-B", "working-monitors", 6, "item", "2026-11-10T09:12:00Z")
    at(clock, "2026-11-10T09:20:00Z")
    third = ok(review(client, decision, "REQ-REVIEW-3"))

    for saved, name in ((second, "supported"), (third, "below-expected")):
        expected = example(f"review-{name}.response.json")
        assert normalized(saved)["facilities"][1]["classification"] == (
            expected["facilities"][1]["classification"])
        assert saved["facilities"][1]["observed_capacity"] == (
            expected["facilities"][1]["observed_capacity"])
    for saved in (first, second, third):
        url = f"{URL}/{decision['decision_id']}/reviews/{saved['review_id']}"
        assert ok(client.get(url), 200) == saved  # later reports never rewrite any review
    assert ok(review(client, decision, "REQ-REVIEW-2"), 200) == second
    listed = ok(client.get(f"{URL}/{decision['decision_id']}/reviews"), 200)
    assert listed["items"] == [third, second, first]
    assert ok(client.get(f"{URL}/{decision['decision_id']}"), 200) == decision


@needs_engine
def test_real_engine_marks_early_reviews(client, clock, journey):
    at(clock, "2026-10-21T09:00:00Z")
    saved = ok(review(client, journey["completed"], "REQ-EARLY",
                      observation_window_starts_at="2026-10-20T00:00:00Z"))
    assert saved["timing"] == "too_early"
    assert {f["classification"] for f in saved["facilities"]} == {"too_early"}



@pytest.mark.parametrize("event_type", ["start", "complete", "update_action"])
def test_execution_timestamp_even_one_second_in_future_is_rejected(
    client, clock, sources, event_type
):
    at(clock, "2026-10-10T10:50:00Z")
    decision = create_allocation_decision(client, sources)
    decision = ok(send(client, decision, "submit", "REQ-FUTURE-SUBMIT"))
    decision = ok(send(client, decision, "approve", "REQ-FUTURE-APPROVE", note="Approved."))
    timestamp = (clock.now + timedelta(seconds=1)).isoformat()
    payload = {"occurred_at": timestamp}
    if event_type == "update_action":
        payload = action(decision["actions"][0]["action_id"], "in_progress", timestamp)
    response = send(client, decision, event_type, "REQ-FUTURE-SECOND", payload, note="Demo report")
    assert response.status_code == 422, response.text
    assert "payload.occurred_at" in [f["field"] for f in response.json()["error"]["fields"]]



def test_review_history_requires_existing_decision_and_starts_empty(client, clock, sources):
    decision = create_allocation_decision(client, sources)
    assert ok(client.get(f"{URL}/{decision['decision_id']}/reviews"), 200) == {"items": []}
    response = client.get(f"{URL}/DEC-MISSING/reviews")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "decision_not_found"
