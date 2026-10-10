"""Backend owner's checks for the Feature 3 network endpoints.

Shared-scenario integration tests owned by the data teammate live in
test_network_api.py.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.engines import capacity as capacity_engine
from app.main import app
from app.modules.capacity import service as capacity_service
from app.modules.facilities.models import FacilityService, ResourceObservation, Service
from app.modules.network.schemas import NetworkOverviewResponse, NetworkServiceListResponse

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "examples"
URL = "/api/v1/network"
OVERVIEW = f"{URL}/overview?service_id=emergency-care"


def example(name: str, feature: str = "feature-3"):
    return json.loads((CONTRACTS / feature / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def fresh_profiles():
    capacity_service._load_profiles.cache_clear()
    yield
    capacity_service._load_profiles.cache_clear()


@pytest.fixture
def server_errors(client) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def add_service(engine, service_id: str, name: str, facility_ids: list[str]) -> None:
    with Session(engine) as db:
        db.add(Service(service_id=service_id, name=name))
        db.flush()  # models have no relationships, so insert order is not inferred
        for facility_id in facility_ids:
            db.add(FacilityService(facility_id=facility_id, service_id=service_id,
                                   status="operating"))
        db.commit()


def observation_count(engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(ResourceObservation))


# Contract examples and schemas.


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("services.response.json", NetworkServiceListResponse),
        ("emergency-care.overview.response.json", NetworkOverviewResponse),
        ("unknown-service.overview.response.json", NetworkOverviewResponse),
    ],
)
def test_examples_match_schema(name, model):
    payload = example(name)
    assert model.model_validate(payload).model_dump(mode="json") == payload


def test_overview_rows_reuse_feature_1_and_2_payloads_unchanged():
    overview = example("emergency-care.overview.response.json")
    facilities = example("facilities.response.json", "feature-1")["items"]
    assert [row["facility"] for row in overview["facilities"]] == facilities
    for row in overview["facilities"]:
        capacity = example(f"{row['facility']['facility_id']}.capacity.response.json",
                           "feature-2")
        assert overview["as_of"] == capacity["as_of"]
        assert [row["capacity"]] == capacity["services"]


@pytest.mark.parametrize(
    "change",
    [
        {"facilities": "reversed"},
        {"service_id": "maternity"},  # rows would mix services
        {"service_name": None},  # unknown service cannot have rows
        {"capacity_unit": "patients_per_day"},
        {"unexpected": True},
    ],
)
def test_overview_contract_violations_are_rejected(change):
    payload = example("emergency-care.overview.response.json")
    if change == {"facilities": "reversed"}:
        change = {"facilities": payload["facilities"][::-1]}
    with pytest.raises(ValidationError):
        NetworkOverviewResponse.model_validate({**payload, **change})


# Endpoints at the frozen fixture clock.


def test_services_match_example(client):
    response = client.get(f"{URL}/services")
    assert response.status_code == 200
    assert response.json() == example("services.response.json")


def test_overview_matches_example(client):
    response = client.get(OVERVIEW)
    assert response.status_code == 200
    assert response.json() == example("emergency-care.overview.response.json")


def test_unknown_service_is_empty_200(client):
    response = client.get(f"{URL}/overview?service_id=maternity")
    assert response.status_code == 200
    assert response.json() == example("unknown-service.overview.response.json")


def test_missing_service_id_is_invalid_request(client):
    response = client.get(f"{URL}/overview")
    assert response.status_code == 422
    assert response.json() == example("missing-service-id.response.json")


@pytest.mark.parametrize("service_id", ["", "bad id", "x" * 65, "-leading"])
def test_malformed_service_id_is_invalid_request(client, service_id):
    response = client.get(f"{URL}/overview", params={"service_id": service_id})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert [field["field"] for field in error["fields"]] == ["service_id"]


# Service selection and exclusion.


def test_only_offering_facilities_are_included(client, engine):
    add_service(engine, "maternity", "Maternity care", ["DEMO-B"])

    services = client.get(f"{URL}/services").json()["items"]
    maternity = client.get(f"{URL}/overview?service_id=maternity").json()
    emergency = client.get(OVERVIEW).json()

    assert [s["service_id"] for s in services] == ["emergency-care", "maternity"]
    assert maternity["service_name"] == "Maternity care"
    assert [row["facility"]["facility_id"] for row in maternity["facilities"]] == ["DEMO-B"]
    assert maternity["facilities"][0]["capacity"]["status"] == "not_configured"
    assert emergency == example("emergency-care.overview.response.json")


def test_catalog_service_offered_nowhere_is_not_listed(client, engine):
    add_service(engine, "dialysis", "Dialysis", [])

    assert client.get(f"{URL}/services").json() == example("services.response.json")
    overview = client.get(f"{URL}/overview?service_id=dialysis").json()
    assert overview["service_name"] == "Dialysis"
    assert overview["facilities"] == []


def test_empty_network_lists_no_services(client, engine):
    with Session(engine) as db:
        db.execute(delete(FacilityService))
        db.commit()
    assert client.get(f"{URL}/services").json() == {"items": []}
    assert client.get(OVERVIEW).json()["facilities"] == []


# Calculation reliability.


def test_one_clock_one_profile_load_one_snapshot_per_facility(client, monkeypatch):
    profile_loads, snapshots = [], []
    original_profiles = capacity_service.get_profiles
    original_engine = capacity_engine.calculate_service_capacity

    def counting_profiles(db):
        profile_loads.append(1)
        return original_profiles(db)

    def recording_engine(snapshot, service, requirement):
        snapshots.append(snapshot)
        return original_engine(snapshot, service, requirement)

    monkeypatch.setattr(capacity_service, "get_profiles", counting_profiles)
    monkeypatch.setattr(capacity_engine, "calculate_service_capacity", recording_engine)

    body = client.get(OVERVIEW).json()

    assert len(profile_loads) == 1
    assert [s.facility.facility_id for s in snapshots] == ["DEMO-A", "DEMO-B", "DEMO-C"]
    assert {s.as_of.isoformat().replace("+00:00", "Z") for s in snapshots} == {body["as_of"]}


def test_configuration_failure_fails_whole_request(server_errors, tmp_path, monkeypatch):
    monkeypatch.setattr(capacity_service, "PROFILES_PATH", tmp_path / "missing.json")
    assert server_errors.get(OVERVIEW).status_code == 500


def test_calculation_failure_fails_whole_request(server_errors, monkeypatch):
    original = capacity_engine.calculate_service_capacity

    def fail_for_demo_b(snapshot, service, requirement):
        if snapshot.facility.facility_id == "DEMO-B":
            raise ValueError("unexpected calculation error")
        return original(snapshot, service, requirement)

    monkeypatch.setattr(capacity_engine, "calculate_service_capacity", fail_for_demo_b)
    assert server_errors.get(OVERVIEW).status_code == 500


def test_saved_update_changes_overview_without_altering_history(client, clock, engine):
    update = {
        "resource_id": "working-monitors",
        "available_quantity": 8,
        "unit": "item",
        "observed_at": "2026-10-10T08:58:00Z",
    }
    assert client.post("/api/v1/facilities/DEMO-B/observations", json=update).status_code == 201
    before = observation_count(engine)

    overview = client.get(OVERVIEW).json()
    rows = {row["facility"]["facility_id"]: row for row in overview["facilities"]}

    demo_b = rows["DEMO-B"]["capacity"]
    assert demo_b["estimated_capacity"] == 8
    assert demo_b["bottleneck_resource_ids"] == ["working-monitors"]
    assert rows["DEMO-B"]["facility"]["last_reported_at"] == "2026-10-10T09:00:00Z"
    assert rows["DEMO-A"]["capacity"]["status"] == "unknown"
    assert rows["DEMO-C"]["capacity"]["estimated_capacity"] == 0
    assert observation_count(engine) == before  # reading the overview writes nothing
    with Session(engine) as db:
        assert db.get(ResourceObservation, "OBS-DEMO-B-4").available_quantity == 5
