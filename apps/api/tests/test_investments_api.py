"""Feature 7 backend: catalog, frozen post-allocation input, validation, engine wiring,
independent package checks and saved, immutable investment runs.

The source proposal is produced by the real Feature 6 allocation engine, so these
tests also cover the allocation -> investment handoff.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines import investments as investments_engine
from app.main import app
from app.modules.allocation import service as allocation_service
from app.modules.capacity import service as capacity_service
from app.modules.investments import service as investments_service
from app.modules.investments.models import InvestmentRun as InvestmentRow
from app.modules.investments.schemas import (
    InvestmentCatalog,
    InvestmentEngineInput,
    InvestmentEngineResult,
    InvestmentRun,
    InvestmentRunRequest,
)

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "examples"
EXAMPLES = CONTRACTS / "feature-7"
URL = "/api/v1/investments"
CASES = ["improved", "no-improvement", "needs-inputs", "timeout"]
RUN_FIELDS = {"investment_run_id", "allocation_run_id", "simulation_run_id", "incident_id",
              "revision_id", "baseline_id", "created_at", "schema_version", "input",
              "solver_settings", "assumed_transfers"}
ENGINE_READY = hasattr(investments_engine, "optimize_investments")


def example(name: str, feature: str = "feature-7"):
    return json.loads((CONTRACTS / feature / name).read_text(encoding="utf-8"))


def comparable(run: dict) -> dict:
    ignored = {"investment_run_id", "allocation_run_id", "simulation_run_id", "incident_id",
               "revision_id", "baseline_id", "created_at", "solve_duration_ms"}
    body = {k: v for k, v in run.items() if k not in ignored}
    body["input"] = {k: v for k, v in run["input"].items() if k != "allocation_run_id"}
    return body


@pytest.fixture(autouse=True)
def fresh_profiles():
    capacity_service._load_profiles.cache_clear()
    yield
    capacity_service._load_profiles.cache_clear()


@pytest.fixture
def allocation(client, clock) -> dict:
    """The Feature 6 demo proposal (A->B one monitor), from the real allocation engine."""
    incident = example("incident.request.json", "feature-6")
    draft = client.post("/api/v1/scenarios/incidents", json=incident).json()
    clock.now += timedelta(minutes=5)
    confirmed = client.post(f"/api/v1/scenarios/incidents/{draft['incident_id']}/confirm",
                            json={"draft_revision_id": draft["revision_id"], "input": incident,
                                  "confirmed_by": "Demo planner"}).json()
    clock.now += timedelta(minutes=1)
    sim = client.post(f"/api/v1/scenarios/incidents/{draft['incident_id']}/revisions/"
                      f"{confirmed['revision_id']}/simulate").json()
    clock.now += timedelta(minutes=9)
    response = client.post("/api/v1/allocation/runs", json={
        **example("improved.request.json", "feature-6"), "simulation_run_id": sim["run_id"]})
    assert response.status_code == 201, response.text
    clock.now += timedelta(minutes=15)
    return response.json()


def request_for(allocation: dict, case: str = "improved", **changes) -> dict:
    return {**example(f"{case}.request.json"), "allocation_run_id":
            allocation["allocation_run_id"], **changes}


class StubEngine:
    """Returns the published example result so wiring is tested apart from the solver."""

    def __init__(self, case: str = "improved"):
        self.case = case
        self.calls: list[InvestmentEngineInput] = []

    def __call__(self, inputs: InvestmentEngineInput) -> InvestmentEngineResult:
        self.calls.append(inputs)
        payload = {k: v for k, v in example(f"{self.case}.response.json").items()
                   if k not in RUN_FIELDS}
        return InvestmentEngineResult.model_validate(payload)


@pytest.fixture
def stub_engine(monkeypatch) -> StubEngine:
    stub = StubEngine()
    monkeypatch.setattr(investments_engine, "optimize_investments", stub, raising=False)
    return stub


@pytest.fixture
def server_errors(client) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def saved_runs(engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(InvestmentRow))


# Catalog and contract examples.


def test_catalog_matches_example(client):
    response = client.get(f"{URL}/catalog")
    assert response.status_code == 200
    assert response.json() == example("catalog.response.json")
    InvestmentCatalog.model_validate(response.json())


@pytest.mark.parametrize("case", CASES)
def test_examples_match_schema(case):
    InvestmentRunRequest.model_validate(example(f"{case}.request.json"))
    payload = example(f"{case}.response.json")
    assert InvestmentRun.model_validate(payload).model_dump(mode="json") == payload
    assert payload["input"] == example(f"{case}.request.json")


def test_improved_example_is_the_agreed_demo():
    run = example("improved.response.json")
    rows = {r["facility_id"]: r for r in run["proposed_summary"]["rows"]}
    assert [p["candidate_id"] for p in run["selected_projects"]] == [
        "INV-B-COMMISSION-5-REPAIRED", "INV-B-REPAIR-5-IDLE"]
    assert (run["total_capital_cost_minor_units"], run["total_operating_cost_minor_units"],
            run["total_cost_minor_units"]) == (150000, 90000, 240000)
    assert (run["baseline_summary"]["covered_service_places"],
            run["proposed_summary"]["covered_service_places"]) == (6, 11)
    assert rows["DEMO-B"]["estimated_capacity"] == 8
    assert run["proposed_summary"]["unmet_service_places"] == 0
    commission = run["selected_projects"][0]
    assert commission["ready_at"] == "2026-10-20T11:00:00Z"  # repair 7 days + 3 days


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(plan_outcome="no_improvement"),
        lambda r: r.update(total_cost_minor_units=1),
        lambda r: r["selected_projects"][0].update(total_cost_minor_units=1),
        lambda r: r.update(solver_status="unknown"),
        lambda r: r.update(validation_passed=False),
        lambda r: r["selected_projects"].reverse(),
        lambda r: r["proposed_summary"]["rows"][1].update(unmet_service_places=1),
        lambda r: r.update(purchase_approved=True),
    ],
)
def test_results_that_break_contract_are_rejected(change):
    run = example("improved.response.json")
    change(run)
    with pytest.raises(ValidationError):
        InvestmentRun.model_validate(run)


@pytest.mark.parametrize(
    "change",
    [
        {"resource_effects": [{"resource_id": "working-monitors", "quantity_delta": 1,
                               "unit": "item"}] * 2},
        {"resource_effects": [{"resource_id": "working-monitors", "quantity_delta": -1,
                               "unit": "item"}]},
        {"resource_effects": [{"resource_id": "working-monitors", "quantity_delta": 1.5,
                               "unit": "item"}]},
        {"requires_candidate_ids": ["INV-B-BUY-1-MONITOR"]},  # itself
        {"requires_candidate_ids": ["Z", "A"]},
        {"capital_cost_minor_units": -1},
        {"implementation_days": 1.5},
    ],
)
def test_malformed_candidates_are_rejected(change):
    candidate = {**example("catalog.response.json")["candidates"][0], **change}
    with pytest.raises(ValidationError):
        InvestmentCatalog.model_validate({**example("catalog.response.json"),
                                          "candidates": [candidate]})


# Frozen post-allocation input (real allocation engine).


def test_post_allocation_state_reapplies_transfers_once(client, allocation, engine):
    with Session(engine) as db:
        state = allocation_service.get_post_allocation_state(db, allocation["allocation_run_id"])
    monitors = {f.snapshot.facility.facility_id: next(
        r.available_quantity for r in f.snapshot.resources if r.resource_id ==
        "working-monitors") for f in state.facilities}
    assert monitors == {"DEMO-A": 3, "DEMO-B": 3, "DEMO-C": 1}  # A->B applied once
    demand = {f.snapshot.facility.facility_id: f.required_service_places
              for f in state.facilities}
    assert demand == {"DEMO-A": 3, "DEMO-B": 8, "DEMO-C": None}
    assert state.included_facility_ids == ["DEMO-A", "DEMO-B"]
    assert [t.quantity for t in state.transfers] == [1]


def test_tampered_allocation_fails_reconstruction(client, allocation, engine):
    from app.modules.allocation.models import AllocationRun as AllocationRow

    with Session(engine) as db:
        row = db.get(AllocationRow, allocation["allocation_run_id"])
        payload = json.loads(json.dumps(row.payload))
        payload["proposed_summary"]["rows"][1]["resource_quantity"] = 9
        row.payload = payload
        db.commit()
        with pytest.raises(RuntimeError, match="does not match its frozen inputs"):
            allocation_service.get_post_allocation_state(db, allocation["allocation_run_id"])


# Wiring with a stub engine.


def test_create_and_reopen_saved_run(client, allocation, stub_engine):
    response = client.post(f"{URL}/runs", json=request_for(allocation))

    assert response.status_code == 201, response.text
    run = response.json()
    assert comparable(run) == comparable(example("improved.response.json"))
    assert run["allocation_run_id"] == allocation["allocation_run_id"]
    assert run["simulation_run_id"] == allocation["simulation_run_id"]
    assert run["assumed_transfers"] == allocation["transfers"]
    reopened = client.get(f"{URL}/runs/{run['investment_run_id']}")
    assert reopened.status_code == 200 and reopened.json() == run
    assert len(stub_engine.calls) == 1  # reopening never re-solves


def test_engine_receives_frozen_post_transfer_state(client, allocation, stub_engine):
    client.post(f"{URL}/runs", json=request_for(allocation))

    [inputs] = stub_engine.calls
    b = next(f for f in inputs.facilities if f.snapshot.facility.facility_id == "DEMO-B")
    assert next(r.available_quantity for r in b.snapshot.resources
                if r.resource_id == "working-monitors") == 3
    assert b.required_service_places == 8
    assert inputs.included_facility_ids == ["DEMO-A", "DEMO-B"]
    assert [e.facility_id for e in inputs.excluded_facilities] == ["DEMO-C"]
    assert inputs.requirement.profile_version == "demo-v1"
    assert len(inputs.candidates) == 4 and inputs.operating_cost_months == 3
    assert inputs.solver_settings.time_limit_seconds == 5.0


@pytest.mark.parametrize("case", CASES)
def test_every_outcome_is_saved(client, allocation, monkeypatch, engine, case):
    monkeypatch.setattr(investments_engine, "optimize_investments", StubEngine(case),
                        raising=False)
    response = client.post(f"{URL}/runs", json=request_for(allocation, case))
    assert response.status_code == 201, response.text
    assert comparable(response.json()) == comparable(example(f"{case}.response.json"))
    assert saved_runs(engine) == 1


def test_later_changes_cannot_alter_saved_run(client, allocation, stub_engine, monkeypatch):
    run = client.post(f"{URL}/runs", json=request_for(allocation)).json()
    update = {"resource_id": "working-monitors", "available_quantity": 9, "unit": "item",
              "observed_at": "2026-10-10T09:29:00Z"}
    assert client.post("/api/v1/facilities/DEMO-B/observations", json=update).status_code == 201
    changed = example("catalog.response.json") | {"catalog_version": "edited-v2",
                                                  "candidates": []}
    monkeypatch.setattr(investments_service, "get_catalog",
                        lambda: InvestmentCatalog.model_validate(changed))

    assert client.get(f"{URL}/runs/{run['investment_run_id']}").json() == run
    client.post(f"{URL}/runs", json=request_for(allocation))
    b = next(f for f in stub_engine.calls[-1].facilities
             if f.snapshot.facility.facility_id == "DEMO-B")
    assert next(r.available_quantity for r in b.snapshot.resources
                if r.resource_id == "working-monitors") == 3  # frozen, not the new report


# Request validation.


def test_missing_and_ineligible_sources(client, allocation, clock, stub_engine):
    missing = client.post(f"{URL}/runs", json=request_for(allocation,
                                                          allocation_run_id="ALLOC-X"))
    assert missing.status_code == 404
    assert missing.json() == example("allocation-not-found.response.json")
    needs = client.post("/api/v1/allocation/runs", json={
        **example("needs-inputs.request.json", "feature-6"),
        "simulation_run_id": allocation["simulation_run_id"]}).json()
    ineligible = client.post(f"{URL}/runs", json=request_for(
        allocation, allocation_run_id=needs["allocation_run_id"]))
    assert ineligible.status_code == 422
    fields = ineligible.json()["error"]["fields"]
    assert fields[0]["field"] == "allocation_run_id"
    assert client.get(f"{URL}/runs/INVRUN-X").json()["error"]["code"] == (
        "investment_run_not_found")
    assert stub_engine.calls == []


def _candidates(index: int = 0, **changes) -> list[dict]:
    candidates = [dict(c) for c in example("catalog.response.json")["candidates"]]
    candidates[index] = {**candidates[index], **changes}
    return candidates


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"planning_starts_at": "2026-10-10T10:30:00Z"}, "planning_starts_at"),
        ({"evaluation_at": "2026-10-10T11:00:00Z"}, "evaluation_at"),
        ({"operating_cost_months": 0}, "operating_cost_months"),
        ({"budget_minor_units": -1}, "budget_minor_units"),
        ({"currency": "EUR"}, "currency"),
        ({"candidates": _candidates(service_id="maternity")}, "candidates.0.service_id"),
        ({"candidates": _candidates(facility_id="DEMO-X")}, "candidates.0.facility_id"),
        ({"candidates": _candidates(resource_effects=[
            {"resource_id": "oxygen-stock", "quantity_delta": 1, "unit": "liter"}])},
         "candidates.0.resource_effects.0.resource_id"),
        ({"candidates": _candidates(resource_effects=[
            {"resource_id": "working-monitors", "quantity_delta": 1, "unit": "bed"}])},
         "candidates.0.resource_effects.0.unit"),
        ({"candidates": _candidates(requires_candidate_ids=["INV-MISSING"])},
         "candidates.0.requires_candidate_ids"),
        ({"candidates": _candidates(3, requires_candidate_ids=["INV-B-COMMISSION-5-REPAIRED"])},
         "candidates"),  # repair <-> commission cycle
        ({"candidates": _candidates() + _candidates()[:1]}, "candidates"),
        ({"unexpected": True}, "unexpected"),
    ],
)
def test_invalid_requests_are_422_with_field_paths(
    client, allocation, stub_engine, engine, changes, field
):
    response = client.post(f"{URL}/runs", json=request_for(allocation, **changes))
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert field in [f["field"] for f in error["fields"]], error["fields"]
    assert stub_engine.calls == [] and saved_runs(engine) == 0


# Independent package checks.


def _mutated(mutate):
    def engine(inputs):
        payload = {k: v for k, v in example("improved.response.json").items()
                   if k not in RUN_FIELDS}
        mutate(payload)
        return InvestmentEngineResult.model_validate(payload)
    return engine


def _drop_prerequisite(p):
    repair = p["selected_projects"].pop(1)
    for key, value in (("total_capital_cost_minor_units", repair["capital_cost_minor_units"]),
                       ("total_operating_cost_minor_units",
                        repair["operating_cost_minor_units"]),
                       ("total_cost_minor_units", repair["total_cost_minor_units"])):
        p[key] -= value
    p["remaining_budget_minor_units"] += repair["total_cost_minor_units"]


def _cheaper_operation(p):
    project = p["selected_projects"][0]
    project.update(operating_cost_minor_units=30000, total_cost_minor_units=80000)
    p.update(total_operating_cost_minor_units=30000, total_cost_minor_units=180000,
             remaining_budget_minor_units=120000)


def _claim_more_capacity(p):
    row = p["proposed_summary"]["rows"][0]
    row.update(estimated_capacity=4, covered_service_places=3)


@pytest.mark.parametrize(
    ("mutate", "changes", "problem"),
    [
        (lambda p: None, {}, None),  # the agreed demo passes every check
        (_drop_prerequisite, {}, "without its prerequisites"),
        (_cheaper_operation, {}, "does not match its supplied candidate"),
        (lambda p: p["selected_projects"][0].update(ready_at="2026-10-19T11:00:00Z"), {},
         "not ready by evaluation_at"),
        (lambda p: None, {"evaluation_at": datetime(2026, 10, 19, 11, tzinfo=UTC)},
         "not ready by evaluation_at"),
        (lambda p: None, {"budget_minor_units": 200000}, "exceeds the budget"),
        (_claim_more_capacity, {}, "do not match the capacity engine"),
        (lambda p: p["coverage"].update(excluded_facilities=[]), {}, "coverage differs"),
    ],
)
def test_check_package_flags_each_violation(client, allocation, stub_engine, mutate, changes,
                                            problem):
    client.post(f"{URL}/runs", json=request_for(allocation))
    inputs = stub_engine.calls[0].model_copy(update=changes)
    result = _mutated(mutate)(inputs)

    problems = investments_service.check_package(inputs, result)

    if problem is None:
        assert problems == []
    else:
        assert any(problem in p for p in problems), problems


def test_check_package_flags_unconfirmed_and_exclusive_selections(client, allocation,
                                                                  stub_engine):
    client.post(f"{URL}/runs", json=request_for(allocation))
    inputs = stub_engine.calls[0]
    candidates = [c.model_copy(update={"source_note": None, "exclusive_group_id": "G"})
                  if c.candidate_id.startswith("INV-B-COMMISSION") else
                  c.model_copy(update={"exclusive_group_id": "G"})
                  if c.candidate_id.startswith("INV-B-REPAIR") else c
                  for c in inputs.candidates]
    inputs = inputs.model_copy(update={"candidates": candidates})

    problems = investments_service.check_package(inputs, _mutated(lambda p: None)(inputs))

    assert any("without confirmation" in p for p in problems), problems
    assert any("More than one project selected in group G" in p for p in problems), problems


@pytest.mark.parametrize("mutate", [_drop_prerequisite, _claim_more_capacity])
def test_invalid_packages_are_never_published(server_errors, allocation, monkeypatch, engine,
                                              mutate):
    monkeypatch.setattr(investments_engine, "optimize_investments", _mutated(mutate),
                        raising=False)
    assert server_errors.post(f"{URL}/runs", json=request_for(allocation)).status_code == 500
    assert saved_runs(engine) == 0


def test_missing_engine_is_a_server_error(server_errors, allocation, monkeypatch, engine):
    monkeypatch.delattr(investments_engine, "optimize_investments", raising=False)
    assert server_errors.post(f"{URL}/runs", json=request_for(allocation)).status_code == 500
    assert saved_runs(engine) == 0


# Integration with the real OR-Tools investment engine (optimization/data owner).

needs_engine = pytest.mark.skipif(
    not ENGINE_READY, reason="engines.investments.optimize_investments not merged yet")


@needs_engine
@pytest.mark.parametrize("case", ["improved", "no-improvement", "needs-inputs"])
def test_real_engine_matches_examples(client, allocation, case):
    response = client.post(f"{URL}/runs", json=request_for(allocation, case))
    assert response.status_code == 201, response.text
    assert comparable(response.json()) == comparable(example(f"{case}.response.json"))


@needs_engine
@pytest.mark.parametrize(("budget", "selected"), [
    (200000, ["INV-B-BUY-1-MONITOR"]),  # $2,000: repair path unaffordable, buy one fits
    (100000, []),  # $1,000: nothing affordable closes a place
])
def test_budget_changes_the_recommendation(client, allocation, budget, selected):
    run = client.post(f"{URL}/runs", json=request_for(allocation,
                                                      budget_minor_units=budget)).json()
    assert [p["candidate_id"] for p in run["selected_projects"]] == selected
