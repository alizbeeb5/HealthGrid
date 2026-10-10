"""Feature 5 backend: incident drafts, confirmation/baseline, overlay engine and runs."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines import scenarios as scenario_engine
from app.main import app
from app.modules.capacity import service as capacity_service
from app.modules.facilities.models import FacilityService, ResourceObservation, Service
from app.modules.scenarios import repository as scenario_repository
from app.modules.scenarios.models import IncidentBaseline as BaselineRow
from app.modules.scenarios.models import IncidentRevision as RevisionRow
from app.modules.scenarios.models import SimulationRun as RunRow
from app.modules.scenarios.schemas import (
    IncidentBaseline,
    IncidentDraftInput,
    IncidentListResponse,
    IncidentRevision,
    ScenarioErrorResponse,
    SimulationRun,
)

EXAMPLES = Path(__file__).resolve().parents[3] / "contracts" / "examples" / "feature-5"
URL = "/api/v1/scenarios"


def example(name: str):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def fresh_profiles():
    capacity_service._load_profiles.cache_clear()
    yield
    capacity_service._load_profiles.cache_clear()


@pytest.fixture
def server_errors(client) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def draft_input(**changes) -> dict:
    return {**example("incident-draft.request.json"), **changes}


def create(client, **changes) -> dict:
    response = client.post(f"{URL}/incidents", json=draft_input(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def confirm(client, draft: dict, **changes):
    body = {"draft_revision_id": draft["revision_id"], "input": draft_input(**changes),
            "confirmed_by": "Demo planner"}
    return client.post(f"{URL}/incidents/{draft['incident_id']}/confirm", json=body)


def simulate(client, revision: dict):
    return client.post(f"{URL}/incidents/{revision['incident_id']}/revisions/"
                       f"{revision['revision_id']}/simulate")


def confirmed_run(client, clock, **changes) -> tuple[dict, dict, dict]:
    draft = create(client, **changes)
    clock.now += timedelta(minutes=5)
    revision = confirm(client, draft, **changes)
    assert revision.status_code == 201, revision.text
    clock.now += timedelta(minutes=1)
    run = simulate(client, revision.json())
    assert run.status_code == 201, run.text
    return draft, revision.json(), run.json()


def rows(run: dict) -> dict[str, dict]:
    return {row["facility"]["facility_id"]: row for row in run["impact"]["rows"]}


def count(engine, model) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(model))


def readable(body, *pairs):
    """Swap generated IDs for the example's readable IDs."""
    text = json.dumps(body)
    for real, fixed in pairs:
        text = text.replace(real, fixed)
    return json.loads(text)


# Contract examples.


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("incident-draft.request.json", IncidentDraftInput),
        ("incident-draft.response.json", IncidentRevision),
        ("incident-confirmed.response.json", IncidentRevision),
        ("incidents.response.json", IncidentListResponse),
        ("simulation-run.response.json", SimulationRun),
        ("revision-conflict.response.json", ScenarioErrorResponse),
        ("incident-not-confirmed.response.json", ScenarioErrorResponse),
        ("invalid-override.response.json", ScenarioErrorResponse),
    ],
)
def test_examples_match_schema(name, model):
    payload = example(name)
    assert model.model_validate(payload).model_dump(mode="json") == payload


def test_full_flow_reproduces_examples(client, clock):
    draft, revision, run = confirmed_run(client, clock)
    ids = [(draft["incident_id"], "INC-DEMO-B-OUTAGE"),
           (draft["revision_id"], "REV-DEMO-B-DRAFT"),
           (revision["revision_id"], "REV-DEMO-B-CONFIRMED"),
           (revision["baseline_id"], "BASE-DEMO-B-OUTAGE"),
           (run["run_id"], "RUN-DEMO-B-OUTAGE")]

    assert readable(draft, *ids) == example("incident-draft.response.json")
    assert readable(revision, *ids) == example("incident-confirmed.response.json")
    assert readable(run, *ids) == example("simulation-run.response.json")
    listed = client.get(f"{URL}/incidents").json()
    assert readable(listed, *ids) == example("incidents.response.json")


def test_demo_b_outage_is_5_to_0(client, clock):
    _, _, run = confirmed_run(client, clock)
    by_id = rows(run)
    b = by_id["DEMO-B"]
    assert (b["baseline_capacity"]["estimated_capacity"],
            b["scenario_capacity"]["estimated_capacity"], b["capacity_change"]) == (5, 0, -5)
    assert b["affected"] and b["applied_overrides"][0]["scenario_status"] == "unavailable"
    a = by_id["DEMO-A"]  # unknown stays unknown, never zero
    assert a["scenario_capacity"]["estimated_capacity"] is None and a["capacity_change"] is None
    c = by_id["DEMO-C"]  # stale evidence is preserved
    assert "stale_required_observation" in c["baseline_capacity"]["reason_codes"]
    assert c["capacity_change"] == 0 and not c["affected"]


# Drafts.


def test_draft_persists_and_reopens(client):
    draft = create(client)
    reopened = client.get(f"{URL}/incidents/{draft['incident_id']}/revisions/"
                          f"{draft['revision_id']}")
    assert reopened.status_code == 200 and reopened.json() == draft
    assert draft["status"] == "draft" and draft["baseline_id"] is None


def test_bare_report_saves_as_draft(client):
    draft = create(client, service_id=None, starts_at=None, expected_ends_at=None,
                   affected_facility_ids=[], service_overrides=[], assumptions=[])
    assert draft["input"]["report_text"].startswith("Demo Hospital B")


def test_list_returns_latest_revision_newest_first(client, clock):
    first = create(client, title="First")
    clock.now += timedelta(minutes=1)
    second = create(client, title="Second")
    clock.now += timedelta(minutes=1)
    confirmed = confirm(client, first).json()

    items = client.get(f"{URL}/incidents").json()["items"]

    assert [i["revision_id"] for i in items] == [confirmed["revision_id"], second["revision_id"]]


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"expected_ends_at": "2026-10-10T09:00:00Z"}, "expected_ends_at"),
        ({"service_id": "dialysis"}, "service_id"),
        ({"affected_facility_ids": ["DEMO-X"]}, "affected_facility_ids.0"),
        ({"affected_facility_ids": ["DEMO-A"]}, "service_overrides.0.facility_id"),
        ({"service_overrides": [{"facility_id": "DEMO-B", "service_id": "maternity",
                                 "status": "unavailable", "restriction_note": None}]},
         "service_overrides.0.service_id"),
        ({"service_overrides": [{"facility_id": "DEMO-B", "service_id": "emergency-care",
                                 "status": "unavailable", "restriction_note": None}] * 2},
         "service_overrides.1"),
        ({"resource_overrides": [{"facility_id": "DEMO-B", "resource_id": "working-monitors",
                                  "available_quantity": 2, "unit": "liter"}]},
         "resource_overrides.0.unit"),
        ({"resource_overrides": [{"facility_id": "DEMO-B", "resource_id": "working-monitors",
                                  "available_quantity": 2.5, "unit": "item"}]},
         "resource_overrides.0.available_quantity"),
        ({"resource_overrides": [{"facility_id": "DEMO-B", "resource_id": "ventilators",
                                  "available_quantity": 2, "unit": "item"}]},
         "resource_overrides.0.resource_id"),
        ({"service_id": None}, "service_id"),  # overrides need a selected service
        ({"affected_facility_ids": ["DEMO-B", "DEMO-A"]}, "affected_facility_ids"),
        ({"service_overrides": [{"facility_id": "DEMO-B", "service_id": "emergency-care",
                                 "status": "limited", "restriction_note": None}]},
         "service_overrides.0"),
        ({"resource_overrides": [{"facility_id": "DEMO-B", "resource_id": "working-monitors",
                                  "available_quantity": -1, "unit": "item"}]},
         "resource_overrides.0.available_quantity"),
        ({"title": ""}, "title"),
        ({"unexpected": True}, "unexpected"),
    ],
)
def test_invalid_draft_is_rejected_with_field_paths(client, engine, changes, field):
    response = client.post(f"{URL}/incidents", json=draft_input(**changes))
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert field in [f["field"] for f in error["fields"]], error["fields"]
    assert count(engine, RevisionRow) == 0


def test_override_facility_must_offer_selected_service(client, engine):
    with Session(engine) as db:
        db.add(Service(service_id="maternity", name="Maternity care"))
        db.flush()
        db.add(FacilityService(facility_id="DEMO-B", service_id="maternity", status="operating"))
        db.commit()
    response = client.post(f"{URL}/incidents", json=draft_input(
        service_id="maternity", affected_facility_ids=["DEMO-A"], service_overrides=[]))
    assert response.status_code == 422
    assert response.json()["error"]["fields"][0]["field"] == "affected_facility_ids.0"


# Confirmation and baseline.


def test_confirm_requires_complete_input(client):
    draft = create(client, service_id=None, starts_at=None, affected_facility_ids=[],
                   service_overrides=[])
    response = confirm(client, draft, starts_at=None, affected_facility_ids=[],
                       service_overrides=[])
    assert response.status_code == 422
    fields = {f["field"] for f in response.json()["error"]["fields"]}
    assert {"input.starts_at", "input.affected_facility_ids"} <= fields


def test_confirm_requires_an_override(client):
    draft = create(client)
    response = confirm(client, draft, service_overrides=[])
    assert response.status_code == 422
    assert response.json()["error"]["fields"][0]["field"] == "input.service_overrides"


def test_baseline_captures_snapshots_and_full_profiles_once(client, clock, engine):
    _, revision, _ = confirmed_run(client, clock)
    with Session(engine) as db:
        baseline = IncidentBaseline.model_validate(
            db.get(BaselineRow, revision["baseline_id"]).payload)
    assert baseline.captured_at.isoformat().replace("+00:00", "Z") == revision["confirmed_at"]
    assert [s.facility.facility_id for s in baseline.facility_snapshots] == [
        "DEMO-A", "DEMO-B", "DEMO-C"]
    assert {s.as_of for s in baseline.facility_snapshots} == {baseline.captured_at}
    assert baseline.requirement_profiles[0].requirements  # content, not just a version
    assert baseline.schema_version == 1


def test_duplicate_confirmation_conflicts(client):
    draft = create(client)
    first = confirm(client, draft)
    second = confirm(client, draft)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "revision_conflict"
    assert second.json()["error"]["existing_revision_id"] == first.json()["revision_id"]


def test_concurrent_confirmation_hits_uniqueness_constraint(client, engine, monkeypatch):
    draft = create(client)
    winner = confirm(client, draft).json()
    original = scenario_repository.get_confirmed_revision
    calls = []

    def stale_precheck(db, incident_id):
        # The losing request's pre-check ran before the winner committed.
        calls.append(incident_id)
        return None if len(calls) == 1 else original(db, incident_id)

    monkeypatch.setattr(scenario_repository, "get_confirmed_revision", stale_precheck)

    response = confirm(client, draft)

    assert response.status_code == 409
    assert response.json()["error"]["existing_revision_id"] == winner["revision_id"]
    assert len(calls) == 2  # the second lookup only happens after the IntegrityError
    assert count(engine, BaselineRow) == 1  # the loser's baseline was rolled back


def test_failed_confirmation_saves_neither_revision_nor_baseline(
    server_errors, engine, monkeypatch
):
    draft = create(server_errors)
    original_add = scenario_repository.add

    def add_then_fail(db, *rows):
        original_add(db, *rows)
        raise RuntimeError("injected failure after flush")

    monkeypatch.setattr(scenario_repository, "add", add_then_fail)
    assert confirm(server_errors, draft).status_code == 500
    assert count(engine, BaselineRow) == 0
    assert count(engine, RevisionRow) == 1  # only the draft


def test_unknown_incident_and_revision(client):
    draft = create(client)
    missing_incident = client.get(f"{URL}/incidents/INC-X/revisions/{draft['revision_id']}")
    missing_revision = client.get(f"{URL}/incidents/{draft['incident_id']}/revisions/REV-X")
    assert missing_incident.status_code == missing_revision.status_code == 404
    assert missing_incident.json()["error"]["code"] == "incident_not_found"
    assert missing_revision.json()["error"]["code"] == "revision_not_found"


# Simulation runs.


def test_simulating_a_draft_is_not_allowed(client):
    draft = create(client)
    response = simulate(client, draft)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "incident_not_confirmed"


def test_repeat_simulation_returns_saved_run(client, clock, engine):
    _, revision, run = confirmed_run(client, clock)
    again = simulate(client, revision)
    assert again.status_code == 200 and again.json() == run
    assert count(engine, RunRow) == 1
    assert client.get(f"{URL}/runs/{run['run_id']}").json() == run
    assert client.get(f"{URL}/runs/RUN-X").json()["error"]["code"] == "run_not_found"


def test_later_reports_do_not_change_saved_baseline_or_run(client, clock, engine):
    observations_before = count(engine, ResourceObservation)
    _, revision, run = confirmed_run(client, clock)
    assert count(engine, ResourceObservation) == observations_before  # scenario wrote none

    update = {"resource_id": "working-monitors", "available_quantity": 8, "unit": "item",
              "observed_at": "2026-10-10T09:05:00Z"}
    assert client.post("/api/v1/facilities/DEMO-B/observations", json=update).status_code == 201

    assert simulate(client, revision).json() == run
    assert client.get(f"{URL}/runs/{run['run_id']}").json() == run
    with Session(engine) as db:
        stored = db.get(ResourceObservation, "OBS-DEMO-B-4")
        assert stored.available_quantity == 5  # the reported history is intact


def test_resource_override_is_a_labeled_assumption(client, clock):
    override = {"facility_id": "DEMO-B", "resource_id": "working-monitors",
                "available_quantity": 2, "unit": "item"}
    _, _, run = confirmed_run(client, clock, service_overrides=[], resource_overrides=[override])

    b = rows(run)["DEMO-B"]
    assert (b["scenario_capacity"]["estimated_capacity"], b["capacity_change"]) == (2, -3)
    [applied] = b["applied_overrides"]
    assert applied == {"override_type": "resource_quantity", "resource_id": "working-monitors",
                       "unit": "item", "baseline_quantity": 5, "baseline_data_status": "current",
                       "scenario_quantity": 2, "affects_modeled_estimate": True}
    monitors = next(r for r in b["scenario_capacity"]["resource_limits"]
                    if r["resource_id"] == "working-monitors")
    assert monitors["observation_id"] is None and monitors["observed_at"] is None


def test_resource_outside_profile_is_recorded_but_does_not_change_estimate(client, clock):
    oxygen = {"facility_id": "DEMO-B", "resource_id": "oxygen-stock",
              "available_quantity": 0, "unit": "liter"}
    _, _, run = confirmed_run(client, clock, service_overrides=[], resource_overrides=[oxygen])
    b = rows(run)["DEMO-B"]
    assert b["capacity_change"] == 0
    assert b["applied_overrides"][0]["affects_modeled_estimate"] is False


def test_unknown_baseline_stays_unknown_unless_explicitly_set(client, clock):
    beds = {"facility_id": "DEMO-A", "resource_id": "available-beds",
            "available_quantity": 4, "unit": "bed"}
    _, _, run = confirmed_run(client, clock, affected_facility_ids=["DEMO-A"],
                              service_overrides=[], resource_overrides=[beds])
    a = rows(run)["DEMO-A"]
    assert a["affected"] and a["scenario_capacity"]["estimated_capacity"] is None
    assert a["capacity_change"] is None
    assert "missing_required_observation" in a["scenario_capacity"]["reason_codes"]


def test_limited_override_yields_unknown_not_a_fraction(client, clock):
    limited = [{"facility_id": "DEMO-B", "service_id": "emergency-care", "status": "limited",
                "restriction_note": "Generator supports half the ward."}]
    _, _, run = confirmed_run(client, clock, service_overrides=limited)
    b = rows(run)["DEMO-B"]
    assert b["scenario_capacity"]["status"] == "unknown"
    assert b["scenario_capacity"]["estimated_capacity"] is None and b["capacity_change"] is None


def test_failed_simulation_saves_no_run(server_errors, clock, engine, monkeypatch):
    draft = create(server_errors)
    revision = confirm(server_errors, draft).json()

    def fail(baseline, incident):
        raise ValueError("unexpected calculation error")

    monkeypatch.setattr(scenario_engine, "simulate_incident", fail)
    assert simulate(server_errors, revision).status_code == 500
    assert count(engine, RunRow) == 0


# Pure engine.


def test_engine_rejects_draft_or_mismatched_baseline():
    draft = IncidentRevision.model_validate(example("incident-draft.response.json"))
    confirmed = IncidentRevision.model_validate(example("incident-confirmed.response.json"))
    baseline = IncidentBaseline(
        baseline_id="BASE-DEMO-B-OUTAGE", captured_at=datetime(2026, 10, 10, 9, 5, tzinfo=UTC),
        service_id="emergency-care", facility_snapshots=[], requirement_profiles=[],
        schema_version=1)
    other = baseline.model_copy(update={"baseline_id": "BASE-OTHER"})
    with pytest.raises(ValueError):
        scenario_engine.simulate_incident(baseline, draft)
    with pytest.raises(ValueError):
        scenario_engine.simulate_incident(other, confirmed)
    with pytest.raises(ValueError):  # affected DEMO-B is not in this empty baseline
        scenario_engine.simulate_incident(baseline, confirmed)


@pytest.mark.parametrize(
    "change",
    [
        lambda row: row.update(capacity_change=-4),
        lambda row: row.update(capacity_change=None),
        lambda row: row.update(affected=False),
    ],
)
def test_impact_rows_that_break_contract_are_rejected(change):
    run = example("simulation-run.response.json")
    change(run["impact"]["rows"][1])
    with pytest.raises(ValidationError):
        SimulationRun.model_validate(run)
