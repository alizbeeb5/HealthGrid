"""Feature 6 backend: request validation, frozen scenario input, engine wiring,
independent plan checks and saved, immutable allocation runs."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines import allocation as allocation_engine
from app.main import app
from app.modules.allocation.models import AllocationRun as AllocationRow
from app.modules.allocation.schemas import (
    AllocationEngineInput,
    AllocationEngineResult,
    AllocationRun,
    AllocationRunRequest,
)
from app.modules.capacity import service as capacity_service

EXAMPLES = Path(__file__).resolve().parents[3] / "contracts" / "examples" / "feature-6"
URL = "/api/v1/allocation/runs"
CASES = ["improved", "no-improvement", "needs-inputs", "no-solution"]
RUN_FIELDS = {"allocation_run_id", "simulation_run_id", "incident_id", "revision_id",
              "baseline_id", "created_at", "schema_version", "input", "solver_settings"}
ENGINE_READY = hasattr(allocation_engine, "optimize_allocation")


def example(name: str):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def comparable(run: dict) -> dict:
    """Drop generated IDs/times and wall-clock duration before comparing."""
    ignored = {"allocation_run_id", "simulation_run_id", "incident_id", "revision_id",
               "baseline_id", "created_at", "solve_duration_ms"}
    body = {k: v for k, v in run.items() if k not in ignored}
    body["input"] = {k: v for k, v in run["input"].items() if k != "simulation_run_id"}
    return body


@pytest.fixture(autouse=True)
def fresh_profiles():
    capacity_service._load_profiles.cache_clear()
    yield
    capacity_service._load_profiles.cache_clear()


@pytest.fixture
def simulation(client, clock) -> dict:
    """The shared demo: a confirmed monitor-shortage scenario and its saved run."""
    incident = example("incident.request.json")
    draft = client.post("/api/v1/scenarios/incidents", json=incident).json()
    clock.now += timedelta(minutes=5)
    confirmed = client.post(f"/api/v1/scenarios/incidents/{draft['incident_id']}/confirm",
                            json={"draft_revision_id": draft["revision_id"], "input": incident,
                                  "confirmed_by": "Demo planner"}).json()
    clock.now += timedelta(minutes=1)
    run = client.post(f"/api/v1/scenarios/incidents/{draft['incident_id']}/revisions/"
                      f"{confirmed['revision_id']}/simulate")
    assert run.status_code == 201, run.text
    clock.now += timedelta(minutes=9)
    return run.json()


def request_for(simulation: dict, case: str = "improved", **changes) -> dict:
    return {**example(f"{case}.request.json"), "simulation_run_id": simulation["run_id"],
            **changes}


class StubEngine:
    """Returns the published example result so wiring is tested apart from the solver."""

    def __init__(self, case: str = "improved"):
        self.case = case
        self.calls: list[AllocationEngineInput] = []

    def __call__(self, inputs: AllocationEngineInput) -> AllocationEngineResult:
        self.calls.append(inputs)
        payload = {k: v for k, v in example(f"{self.case}.response.json").items()
                   if k not in RUN_FIELDS}
        return AllocationEngineResult.model_validate(payload)


@pytest.fixture
def stub_engine(monkeypatch) -> StubEngine:
    stub = StubEngine()
    monkeypatch.setattr(allocation_engine, "optimize_allocation", stub, raising=False)
    return stub


@pytest.fixture
def server_errors(client) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def saved_runs(engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(AllocationRow))


# Contract examples.


@pytest.mark.parametrize("case", CASES)
def test_examples_match_schema(case):
    AllocationRunRequest.model_validate(example(f"{case}.request.json"))
    payload = example(f"{case}.response.json")
    assert AllocationRun.model_validate(payload).model_dump(mode="json") == payload
    assert payload["input"] == example(f"{case}.request.json") | {
        "simulation_run_id": payload["simulation_run_id"]}


def test_improved_example_is_the_agreed_demo():
    run = example("improved.response.json")
    before = {r["facility_id"]: r for r in run["baseline_summary"]["rows"]}
    after = {r["facility_id"]: r for r in run["proposed_summary"]["rows"]}
    assert [(t["from_facility_id"], t["to_facility_id"], t["quantity"])
            for t in run["transfers"]] == [("DEMO-A", "DEMO-B", 1)]
    assert (before["DEMO-A"]["estimated_capacity"], after["DEMO-A"]["estimated_capacity"]) == (4, 3)
    assert (before["DEMO-B"]["estimated_capacity"], after["DEMO-B"]["estimated_capacity"]) == (2, 3)
    assert (run["baseline_summary"]["covered_service_places"],
            run["proposed_summary"]["covered_service_places"]) == (5, 6)
    assert run["proposed_summary"]["unmet_service_places"] == 5
    assert after["DEMO-A"]["unmet_service_places"] == 0  # donor demand stays covered
    assert run["coverage"]["excluded"][0]["facility_id"] == "DEMO-C"


def _drop(key):
    return lambda run: run.pop(key)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(plan_outcome="no_improvement"),  # covered went 5 -> 6
        lambda r: r.update(solver_status="unknown"),  # unknown cannot carry a proposal
        lambda r: r.update(validation_passed=False),  # never publish an unvalidated plan
        lambda r: r.update(total_cost_minor_units=0),
        lambda r: r.update(review_required=False),
        lambda r: r["proposed_summary"].update(covered_service_places=7),
        lambda r: r["proposed_summary"]["rows"][1].update(unmet_service_places=4),
        lambda r: r["coverage"].update(included_facility_ids=["DEMO-B", "DEMO-A"]),
        lambda r: r["transfers"][0].update(quantity=0),
        lambda r: r.update(dispatch_approved=True),
        _drop("objective_description"),
    ],
)
def test_results_that_break_contract_are_rejected(change):
    run = example("improved.response.json")
    change(run)
    with pytest.raises(ValidationError):
        AllocationRun.model_validate(run)


# Wiring with a stub engine.


def test_create_and_reopen_saved_run(client, simulation, stub_engine):
    response = client.post(URL, json=request_for(simulation))

    assert response.status_code == 201, response.text
    run = response.json()
    assert comparable(run) == comparable(example("improved.response.json"))
    assert run["simulation_run_id"] == simulation["run_id"]
    assert run["incident_id"] == simulation["impact"]["incident_id"]
    assert run["baseline_id"] == simulation["impact"]["baseline_id"]
    reopened = client.get(f"{URL}/{run['allocation_run_id']}")
    assert reopened.status_code == 200 and reopened.json() == run
    assert len(stub_engine.calls) == 1  # reopening never re-solves


def test_engine_receives_frozen_effective_scenario(client, simulation, stub_engine):
    client.post(URL, json=request_for(simulation))

    [inputs] = stub_engine.calls
    by_id = {f.snapshot.facility.facility_id: f for f in inputs.facilities}
    assert list(by_id) == ["DEMO-A", "DEMO-B", "DEMO-C"]
    monitors = next(r for r in by_id["DEMO-A"].snapshot.resources
                    if r.resource_id == "working-monitors")
    # The confirmed scenario assumption, without the old report as its evidence.
    assert (monitors.available_quantity, monitors.observation_id) == (4, None)
    assert next(s for s in by_id["DEMO-A"].snapshot.services).status == "operating"
    assert by_id["DEMO-A"].applied_overrides and by_id["DEMO-C"].applied_overrides == []
    assert by_id["DEMO-C"].constraint is None
    assert by_id["DEMO-B"].constraint.required_service_places == 8
    assert (inputs.resource_id, inputs.unit, inputs.service_id) == (
        "working-monitors", "item", "emergency-care")
    assert inputs.requirement.profile_version == "demo-v1"
    assert inputs.solver_settings.time_limit_seconds == 5.0


def test_later_hospital_updates_cannot_change_saved_or_new_runs(
    client, simulation, stub_engine
):
    run = client.post(URL, json=request_for(simulation)).json()
    update = {"resource_id": "working-monitors", "available_quantity": 9, "unit": "item",
              "observed_at": "2026-10-10T09:14:00Z"}
    assert client.post("/api/v1/facilities/DEMO-B/observations", json=update).status_code == 201

    assert client.get(f"{URL}/{run['allocation_run_id']}").json() == run
    client.post(URL, json=request_for(simulation))
    frozen = next(r for f in stub_engine.calls[-1].facilities
                  if f.snapshot.facility.facility_id == "DEMO-B"
                  for r in f.snapshot.resources if r.resource_id == "working-monitors")
    assert frozen.available_quantity == 2  # the saved scenario, not the new report


@pytest.mark.parametrize("case", CASES)
def test_every_outcome_is_saved(client, simulation, monkeypatch, case, engine):
    monkeypatch.setattr(allocation_engine, "optimize_allocation", StubEngine(case),
                        raising=False)
    response = client.post(URL, json=request_for(simulation, case))
    assert response.status_code == 201
    assert comparable(response.json()) == comparable(example(f"{case}.response.json"))
    assert saved_runs(engine) == 1


# Request validation.


def test_unknown_simulation_run_is_404(client, stub_engine):
    response = client.post(URL, json=example("improved.request.json") | {
        "simulation_run_id": "RUN-X"})
    assert response.status_code == 404
    assert response.json() == example("simulation-not-found.response.json")
    assert client.get(f"{URL}/ALLOC-X").json()["error"]["code"] == "allocation_run_not_found"


def test_route_to_unconstrained_facility_is_422(client, simulation, stub_engine):
    route = {**example("improved.request.json")["routes"][0], "to_facility_id": "DEMO-C"}
    response = client.post(URL, json=request_for(simulation, routes=[route]))
    assert response.status_code == 422
    assert response.json() == example("invalid-route.response.json")
    assert stub_engine.calls == []


def _constraint(**changes):
    return {**example("improved.request.json")["facility_constraints"][0], **changes}


def _route(**changes):
    return {**example("improved.request.json")["routes"][0], **changes}


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"resource_id": "available-beds"}, "resource_id"),
        ({"currency": "EUR"}, "currency"),
        ({"planning_horizon_minutes": 0}, "planning_horizon_minutes"),
        ({"budget_minor_units": -1}, "budget_minor_units"),
        ({"budget_minor_units": 100.5}, "budget_minor_units"),
        ({"facility_constraints": [_constraint(transferable_quantity=-1)]},
         "facility_constraints.0.transferable_quantity"),
        ({"facility_constraints": [_constraint(confirmed_at="2026-10-10T09:10:00")]},
         "facility_constraints.0.confirmed_at"),
        ({"facility_constraints": [_constraint(source_note="")]},
         "facility_constraints.0.source_note"),
        ({"facility_constraints": [_constraint(), _constraint()]}, "facility_constraints"),
        ({"facility_constraints": [_constraint(facility_id="DEMO-X")]},
         "facility_constraints.0.facility_id"),
        ({"routes": [_route(to_facility_id="DEMO-A")]}, "routes.0"),
        ({"routes": [_route(), _route(route_id="ROUTE-2")]}, "routes"),
        ({"routes": [_route(), _route()]}, "routes"),
        ({"routes": [_route(maximum_quantity=0)]}, "routes.0.maximum_quantity"),
        ({"routes": [_route(from_facility_id="DEMO-X")]}, "routes.0.from_facility_id"),
        ({"unexpected": True}, "unexpected"),
    ],
)
def test_invalid_requests_are_422_with_field_paths(
    client, simulation, stub_engine, engine, changes, field
):
    response = client.post(URL, json=request_for(simulation, **changes))
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert field in [f["field"] for f in error["fields"]], error["fields"]
    assert stub_engine.calls == [] and saved_runs(engine) == 0


# Independent validation of engine output.


def _bad(mutate):
    def engine(inputs):
        payload = {k: v for k, v in example("improved.response.json").items()
                   if k not in RUN_FIELDS}
        mutate(payload)
        return AllocationEngineResult.model_validate(payload)
    return engine


def _move(quantity, cost=10000):
    def mutate(p):
        p["transfers"][0].update(quantity=quantity, cost_minor_units=quantity * cost)
        p["total_cost_minor_units"] = quantity * cost
    return mutate


def _claim_capacity(p):
    p["proposed_summary"]["rows"][1].update(estimated_capacity=4, covered_service_places=4,
                                             unmet_service_places=4)
    p["proposed_summary"].update(covered_service_places=7, unmet_service_places=4)


@pytest.mark.parametrize(
    "mutate",
    [
        _move(2),  # beyond A's approved transferable quantity and B's inbound cap
        lambda p: p["transfers"][0].update(route_id="ROUTE-UNAPPROVED"),
        lambda p: p["transfers"][0].update(lead_time_minutes=90),
        _claim_capacity,  # capacity not confirmed by the capacity engine
        lambda p: p["proposed_summary"]["rows"][0].update(resource_quantity=4),
        lambda p: p["coverage"].update(included_facility_ids=["DEMO-A", "DEMO-B", "DEMO-C"]),
    ],
)
def test_invalid_proposals_are_never_published(server_errors, simulation, monkeypatch,
                                               engine, mutate):
    monkeypatch.setattr(allocation_engine, "optimize_allocation", _bad(mutate), raising=False)
    response = server_errors.post(URL, json=request_for(simulation))
    assert response.status_code == 500
    assert saved_runs(engine) == 0


@pytest.mark.parametrize(
    ("mutate", "budget", "problem"),
    [
        (lambda p: None, 10000, None),  # the agreed demo passes every check
        (_move(2), 20000, "sends more than its approved quantity"),
        (_move(2), 20000, "receives more than it can accept"),
        (lambda p: p["transfers"][0].update(route_id="ROUTE-UNAPPROVED"), 10000, "unapproved"),
        (lambda p: p["transfers"][0].update(lead_time_minutes=90), 10000, "deadline"),
        (lambda p: p["transfers"][0].update(cost_minor_units=1) or p.update(
            total_cost_minor_units=1), 10000, "wrong cost"),
        (lambda p: None, 5000, "exceeds the budget"),
        (_claim_capacity, 10000, "do not match the capacity engine"),
        (lambda p: p["proposed_summary"]["rows"][0].update(resource_quantity=4), 10000,
         "do not match the capacity engine"),
    ],
)
def test_check_plan_flags_each_violation(client, simulation, stub_engine, mutate, budget,
                                         problem):
    from app.modules.allocation.service import check_plan

    client.post(URL, json=request_for(simulation))
    inputs = stub_engine.calls[0].model_copy(update={"budget_minor_units": budget})
    result = _bad(mutate)(inputs)

    problems = check_plan(inputs, result)

    if problem is None:
        assert problems == []
    else:
        assert any(problem in p for p in problems), problems


def test_check_plan_flags_donor_below_protected_capacity(client, simulation, stub_engine):
    from app.modules.allocation.service import check_plan

    client.post(URL, json=request_for(simulation))
    inputs = stub_engine.calls[0]
    donor = inputs.facilities[0].constraint.model_copy(
        update={"required_service_places": 4, "minimum_retained_resource_quantity": 0})
    facilities = [inputs.facilities[0].model_copy(update={"constraint": donor}),
                  *inputs.facilities[1:]]
    inputs = inputs.model_copy(update={"facilities": facilities})

    def demand_four(p):
        for summary in ("baseline_summary", "proposed_summary"):
            row = p[summary]["rows"][0]
            row.update(required_service_places=4)
            row.update(covered_service_places=min(row["estimated_capacity"], 4),
                       unmet_service_places=4 - min(row["estimated_capacity"], 4))
            rows = p[summary]["rows"]
            p[summary].update(required_service_places=sum(r["required_service_places"]
                                                          for r in rows),
                              covered_service_places=sum(r["covered_service_places"]
                                                         for r in rows),
                              unmet_service_places=sum(r["unmet_service_places"]
                                                       for r in rows))
        p["plan_outcome"] = "no_improvement"  # 6 -> 6: the move only shifts the gap

    problems = check_plan(inputs, _bad(demand_four)(inputs))
    assert any("below its protected capacity" in p for p in problems), problems


def test_over_budget_proposal_is_rejected(server_errors, simulation, monkeypatch, engine):
    monkeypatch.setattr(allocation_engine, "optimize_allocation", StubEngine(), raising=False)
    response = server_errors.post(URL, json=request_for(simulation, budget_minor_units=5000))
    assert response.status_code == 500 and saved_runs(engine) == 0


def test_missing_engine_is_a_server_error(server_errors, simulation, monkeypatch, engine):
    monkeypatch.delattr(allocation_engine, "optimize_allocation", raising=False)
    assert server_errors.post(URL, json=request_for(simulation)).status_code == 500
    assert saved_runs(engine) == 0


# Integration with the real OR-Tools engine (optimization/data owner).

needs_engine = pytest.mark.skipif(
    not ENGINE_READY, reason="engines.allocation.optimize_allocation not merged yet")


@needs_engine
@pytest.mark.parametrize("case", CASES)
def test_real_engine_matches_examples(client, simulation, case):
    response = client.post(URL, json=request_for(simulation, case))
    assert response.status_code == 201, response.text
    assert comparable(response.json()) == comparable(example(f"{case}.response.json"))


@needs_engine
def test_equipment_cannot_reopen_a_closed_service(client, clock):
    closure = json.loads((EXAMPLES.parent / "feature-5" / "incident-draft.request.json")
                         .read_text(encoding="utf-8"))
    draft = client.post("/api/v1/scenarios/incidents", json=closure).json()
    confirmed = client.post(f"/api/v1/scenarios/incidents/{draft['incident_id']}/confirm",
                            json={"draft_revision_id": draft["revision_id"], "input": closure,
                                  "confirmed_by": "Demo planner"}).json()
    sim = client.post(f"/api/v1/scenarios/incidents/{draft['incident_id']}/revisions/"
                      f"{confirmed['revision_id']}/simulate").json()

    run = client.post(URL, json=request_for(sim)).json()

    excluded = {e["facility_id"]: e["reasons"] for e in run["coverage"]["excluded"]}
    assert "service_unavailable" in excluded["DEMO-B"]
    assert run["transfers"] == []


@needs_engine
def test_real_saved_plan_and_frozen_input_survive_later_updates(client, simulation):
    first = client.post(URL, json=request_for(simulation))
    assert first.status_code == 201, first.text
    run = first.json()
    assert run["proposed_summary"]["covered_service_places"] == 6
    before = client.get("/api/v1/facilities/DEMO-B/snapshot").json()
    monitors = next(r for r in before["resources"] if r["resource_id"] == "working-monitors")
    assert monitors["available_quantity"] == 5
    update = {"resource_id": "working-monitors", "available_quantity": 9, "unit": "item",
              "observed_at": "2026-10-10T09:14:00Z"}
    assert client.post("/api/v1/facilities/DEMO-B/observations", json=update).status_code == 201
    assert client.get(f"{URL}/{run['allocation_run_id']}").json() == run
    repeated = client.post(URL, json=request_for(simulation))
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["baseline_summary"] == run["baseline_summary"]
    assert repeated.json()["proposed_summary"] == run["proposed_summary"]
    assert repeated.json()["transfers"] == run["transfers"]
