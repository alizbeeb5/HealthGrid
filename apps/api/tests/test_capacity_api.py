import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines import capacity as capacity_engine
from app.main import app
from app.modules.capacity import service as capacity_service
from app.modules.capacity.schemas import (
    FacilityCapacityResponse,
    ServiceCapacityResult,
    ServiceRequirement,
)
from app.modules.facilities.models import Facility, ResourceObservation
from app.modules.facilities.seed import FIXTURES as FEATURE_1

EXAMPLES = Path(__file__).resolve().parents[3] / "contracts" / "examples" / "feature-2"
PROFILE = EXAMPLES / "service-requirement.json"
URL = "/api/v1/capacity/facilities"
ENGINE_READY = hasattr(capacity_engine, "calculate_service_capacity")


def example(name: str):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def demo_profile(monkeypatch):
    """Use the agreed contract profile until the runtime copy is merged."""
    monkeypatch.setattr(capacity_service, "PROFILES_PATH", PROFILE)
    capacity_service._load_profiles.cache_clear()
    yield
    capacity_service._load_profiles.cache_clear()


class StubEngine:
    """Stands in for engines.capacity to test wiring independently of the formula."""

    def __init__(self):
        self.calls = []

    def __call__(self, snapshot, service, requirement):
        self.calls.append((snapshot, service, requirement))
        return ServiceCapacityResult(
            service_id=service.service_id,
            service_status=service.status,
            profile_version=requirement.profile_version if requirement else None,
            capacity_unit="simultaneous_service_place",
            status="unknown" if requirement else "not_configured",
            estimated_capacity=None,
            bottleneck_resource_ids=[],
            resource_limits=[],
            reason_codes=[] if requirement else ["requirements_not_configured"],
        )


@pytest.fixture
def stub_engine(monkeypatch) -> StubEngine:
    stub = StubEngine()
    monkeypatch.setattr(capacity_engine, "calculate_service_capacity", stub, raising=False)
    return stub


@pytest.fixture
def server_errors(client) -> TestClient:
    """Same app and overrides, but returns 500 responses instead of raising."""
    return TestClient(app, raise_server_exceptions=False)


def observation_count(engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(ResourceObservation))


# Contract: schemas and shared examples agree.


@pytest.mark.parametrize("facility_id", ["DEMO-A", "DEMO-B", "DEMO-C"])
def test_examples_match_schema(facility_id):
    payload = example(f"{facility_id}.capacity.response.json")
    model = FacilityCapacityResponse.model_validate(payload)
    assert model.model_dump(mode="json") == payload


def test_profile_example_matches_schema():
    ServiceRequirement.model_validate(example("service-requirement.json"))


@pytest.mark.parametrize(
    "change",
    [
        {"requirements": []},
        {"profile_version": ""},
        {"capacity_unit": "patients_per_day"},
        {"unexpected": True},
        {"requirements": [{"resource_id": "available-beds", "unit": "bed",
                           "required_per_capacity_unit": 0}]},
        {"requirements": [{"resource_id": "available-beds", "unit": "bed",
                           "required_per_capacity_unit": float("inf")}]},
        {"requirements": [{"resource_id": "available-beds", "unit": "bed",
                           "required_per_capacity_unit": "1"}]},
        {"requirements": [{"resource_id": "available-beds", "unit": "bed",
                           "required_per_capacity_unit": 1}] * 2},
    ],
)
def test_invalid_profiles_are_rejected(change):
    with pytest.raises(ValidationError):
        ServiceRequirement.model_validate({**example("service-requirement.json"), **change})


@pytest.mark.parametrize(
    "change",
    [
        {"status": "unavailable", "estimated_capacity": None},
        {"status": "unknown", "estimated_capacity": 5},
        {"status": "calculated", "bottleneck_resource_ids": []},
        {"status": "unknown", "estimated_capacity": None},  # keeps a bottleneck
        {"bottleneck_resource_ids": ["working-monitors", "available-beds"]},
        {"reason_codes": ["stale_required_observation", "service_unavailable"]},
        {"status": "not_configured", "estimated_capacity": None,
         "bottleneck_resource_ids": []},  # still has a profile_version
        {"estimated_capacity": -1},
    ],
)
def test_results_that_break_contract_are_rejected(change):
    service = example("DEMO-B.capacity.response.json")["services"][0]
    with pytest.raises(ValidationError):
        ServiceCapacityResult.model_validate({**service, **change})


# Wiring: endpoint -> facilities snapshot -> engine, with a stub engine.


def test_engine_receives_snapshot_service_and_matching_profile(client, stub_engine):
    response = client.get(f"{URL}/DEMO-B")

    assert response.status_code == 200
    body = response.json()
    assert body["facility_id"] == "DEMO-B"
    assert body["as_of"] == "2026-10-10T09:00:00Z"
    assert body["stale_after_hours"] == 24
    assert body["calculation_scope"] == "single_service"
    [(snapshot, service, requirement)] = stub_engine.calls
    snapshot_json = json.loads(snapshot.model_dump_json())
    assert snapshot_json == json.loads((FEATURE_1 / "DEMO-B.snapshot.response.json").read_text())
    assert service.service_id == "emergency-care"
    assert requirement == ServiceRequirement.model_validate(example("service-requirement.json"))


def test_service_without_profile_gets_none(client, stub_engine, tmp_path, monkeypatch):
    other = {**example("service-requirement.json"), "service_id": "maternity"}
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps([other]))
    monkeypatch.setattr(capacity_service, "PROFILES_PATH", path)

    body = client.get(f"{URL}/DEMO-B").json()

    assert stub_engine.calls[0][2] is None
    assert body["services"][0]["status"] == "not_configured"


def test_unknown_facility_returns_standard_404(client, stub_engine):
    response = client.get(f"{URL}/DEMO-X")
    assert response.status_code == 404
    assert response.json() == json.loads((FEATURE_1 / "not-found.response.json").read_text())
    assert stub_engine.calls == []


def test_facility_without_services_returns_empty_list(client, engine, stub_engine):
    with Session(engine) as db:
        db.add(Facility(facility_id="DEMO-EMPTY", name="Empty", latitude=0, longitude=0))
        db.commit()

    response = client.get(f"{URL}/DEMO-EMPTY")

    assert response.status_code == 200
    assert response.json()["services"] == []


def test_invalid_path_uses_invalid_request(client, stub_engine):
    response = client.get(f"{URL}/{'X' * 65}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize(
    "profiles",
    [
        "not json",
        json.dumps({"service_id": "emergency-care"}),
        json.dumps([{**json.loads(PROFILE.read_text()), "requirements": [
            {"resource_id": "ventilators", "unit": "item", "required_per_capacity_unit": 1}]}]),
        json.dumps([{**json.loads(PROFILE.read_text()), "requirements": [
            {"resource_id": "available-beds", "unit": "person",
             "required_per_capacity_unit": 1}]}]),
        json.dumps([json.loads(PROFILE.read_text())] * 2),
    ],
    ids=["unreadable", "incomplete", "unknown-resource", "unit-mismatch", "duplicate-service"],
)
def test_invalid_configuration_is_a_server_error(
    server_errors, stub_engine, tmp_path, monkeypatch, profiles
):
    path = tmp_path / "profiles.json"
    path.write_text(profiles)
    monkeypatch.setattr(capacity_service, "PROFILES_PATH", path)

    assert server_errors.get(f"{URL}/DEMO-B").status_code == 500
    assert stub_engine.calls == []


def test_missing_profile_file_is_a_server_error(server_errors, stub_engine, tmp_path, monkeypatch):
    monkeypatch.setattr(capacity_service, "PROFILES_PATH", tmp_path / "missing.json")
    assert server_errors.get(f"{URL}/DEMO-B").status_code == 500


def test_missing_engine_is_a_server_error(server_errors, monkeypatch):
    monkeypatch.delattr(capacity_engine, "calculate_service_capacity", raising=False)
    assert server_errors.get(f"{URL}/DEMO-B").status_code == 500


def test_engine_result_breaking_contract_is_a_server_error(server_errors, monkeypatch):
    def wrong_service(snapshot, service, requirement):
        return StubEngine()(snapshot, service.model_copy(update={"service_id": "other"}),
                            requirement)

    monkeypatch.setattr(capacity_engine, "calculate_service_capacity", wrong_service,
                        raising=False)
    assert server_errors.get(f"{URL}/DEMO-B").status_code == 500


# Integration with the real engine (data/calculation owner). Skipped until merged.

needs_engine = pytest.mark.skipif(
    not ENGINE_READY, reason="engines.capacity.calculate_service_capacity not merged yet"
)


@needs_engine
@pytest.mark.parametrize("facility_id", ["DEMO-A", "DEMO-B", "DEMO-C"])
def test_endpoint_matches_examples_at_fixture_clock(client, facility_id):
    response = client.get(f"{URL}/{facility_id}")
    assert response.status_code == 200
    assert response.json() == example(f"{facility_id}.capacity.response.json")


@needs_engine
def test_saved_observation_changes_capacity_without_altering_history(client, clock, engine):
    assert client.get(f"{URL}/DEMO-B").json()["services"][0]["estimated_capacity"] == 5
    update = {
        "resource_id": "working-monitors",
        "available_quantity": 8,
        "unit": "item",
        "observed_at": "2026-10-10T08:58:00Z",
    }
    assert client.post("/api/v1/facilities/DEMO-B/observations", json=update).status_code == 201
    before = observation_count(engine)

    service = client.get(f"{URL}/DEMO-B").json()["services"][0]

    assert service["estimated_capacity"] == 8
    assert service["bottleneck_resource_ids"] == ["working-monitors"]
    monitors = next(r for r in service["resource_limits"]
                    if r["resource_id"] == "working-monitors")
    assert monitors["available_quantity"] == 8 and monitors["capacity_limit"] == 8
    assert observation_count(engine) == before  # reading capacity writes nothing
    with Session(engine) as db:
        assert db.get(ResourceObservation, "OBS-DEMO-B-4").available_quantity == 5
