"""Feature 3 acceptance tests for teammate 2's network API.

Uses conftest.py's disposable SQLite database and frozen server_now dependency.
Does not seed, connect to or modify the developer's working database. These tests
intentionally require the real routes and engine; no replacement network API.
"""

import json
from collections import Counter
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.engines import capacity as capacity_engine
from app.main import app
from app.modules.capacity import service as capacity_service
from app.modules.facilities import service as facilities_service
from app.modules.facilities.models import FacilityService, ResourceObservation, Service

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "contracts/examples"
SCENARIOS = ROOT / "data/synthetic/feature-3"
URL = "/api/v1/network"
SERVICE_ID = "emergency-care"


def read(path):
    return json.loads(path.read_text())


def overview(client, service_id=SERVICE_ID):
    response = client.get(f"{URL}/overview", params={"service_id": service_id})
    assert response.status_code == 200, response.text
    return response.json()


def row(body, facility_id):
    return next(r for r in body["facilities"] if r["facility"]["facility_id"] == facility_id)


def observation_count(engine):
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(ResourceObservation))


@pytest.fixture(autouse=True)
def fresh_profiles():
    capacity_service._load_profiles.cache_clear()
    yield
    capacity_service._load_profiles.cache_clear()


def test_services_match_offered_catalog(client):
    response = client.get(f"{URL}/services")
    assert response.status_code == 200
    assert response.json() == {
        "items": [{"service_id": SERVICE_ID, "name": "Emergency care"}]
    }


def test_fixed_clock_network_preserves_shared_facility_and_capacity_examples(client):
    body = overview(client)
    expected_rows = []
    for letter in "ABC":
        snapshot = read(EXAMPLES / f"feature-1/DEMO-{letter}.snapshot.response.json")
        capacity = read(EXAMPLES / f"feature-2/DEMO-{letter}.capacity.response.json")
        expected_rows.append({
            "facility": snapshot["facility"], "capacity": capacity["services"][0]
        })
    assert body == {
        "service_id": SERVICE_ID,
        "service_name": "Emergency care",
        "as_of": "2026-10-10T09:00:00Z",
        "stale_after_hours": 24,
        "calculation_scope": "single_service",
        "capacity_unit": "simultaneous_service_place",
        "facilities": expected_rows,
    }
    # Summary arithmetic itself is tested against the real TypeScript helper.
    assert Counter(r["capacity"]["status"] for r in body["facilities"]) == {
        "unknown": 1, "calculated": 1, "unavailable": 1,
    }


@pytest.mark.parametrize("params", [{}, {"service_id": ""},
                                    {"service_id": "bad id"}, {"service_id": "x" * 65}])
def test_invalid_query_has_standard_field_error(client, params):
    response = client.get(f"{URL}/overview", params=params)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert any(field["field"] == "service_id" and field["message"] for field in error["fields"])


def test_unknown_service_is_empty_without_default_substitution(client):
    body = overview(client, "unknown-service")
    assert body["service_id"] == "unknown-service"
    assert body["service_name"] is None
    assert body["facilities"] == []
    assert body["as_of"] == "2026-10-10T09:00:00Z"


def test_service_selector_and_overview_include_only_offered_services(client, engine):
    with Session(engine) as db:
        db.add_all([Service(service_id="demo-outpatient", name="Demo outpatient"),
                    Service(service_id="not-offered", name="Not offered")])
        db.flush()
        db.add(FacilityService(facility_id="DEMO-B", service_id="demo-outpatient",
                               status="operating"))
        db.commit()
    response = client.get(f"{URL}/services")
    assert response.status_code == 200
    assert response.json()["items"] == [
        {"service_id": "demo-outpatient", "name": "Demo outpatient"},
        {"service_id": SERVICE_ID, "name": "Emergency care"},
    ]
    body = overview(client, "demo-outpatient")
    assert body["service_name"] == "Demo outpatient"
    assert [r["facility"]["facility_id"] for r in body["facilities"]] == ["DEMO-B"]
    result = body["facilities"][0]["capacity"]
    assert result["status"] == "not_configured"
    assert result["estimated_capacity"] is None
    assert result["reason_codes"] == ["requirements_not_configured"]
    assert len(overview(client)["facilities"]) == 3


def test_empty_participating_network(client, engine):
    with Session(engine) as db:
        db.execute(delete(FacilityService))
        db.commit()
    response = client.get(f"{URL}/services")
    assert response.status_code == 200
    assert response.json() == {"items": []}
    assert overview(client)["facilities"] == []


def test_snapshots_share_one_clock_and_profiles_load_once(client, monkeypatch):
    original_snapshot = facilities_service.get_snapshot
    original_profiles = capacity_service.get_profiles
    calls, profile_calls = [], []

    def snapshot(db, facility_id, now):
        calls.append((facility_id, now))
        return original_snapshot(db, facility_id, now)

    def profiles(db):
        profile_calls.append(True)
        return original_profiles(db)

    monkeypatch.setattr(facilities_service, "get_snapshot", snapshot)
    monkeypatch.setattr(capacity_service, "get_profiles", profiles)
    body = overview(client)
    assert Counter(facility_id for facility_id, _ in calls) == {
        "DEMO-A": 1, "DEMO-B": 1, "DEMO-C": 1,
    }
    assert len({now for _, now in calls}) == 1
    assert calls[0][1].isoformat().replace("+00:00", "Z") == body["as_of"]
    assert len(profile_calls) == 1


def test_network_passes_loaded_snapshots_directly_to_engine(client, monkeypatch):
    original_snapshot = facilities_service.get_snapshot
    original_calculate = capacity_engine.calculate_service_capacity
    loaded, calculated = {}, []

    def snapshot(db, facility_id, now):
        result = original_snapshot(db, facility_id, now)
        loaded[facility_id] = result
        return result

    def calculate(snapshot, service, requirement):
        assert snapshot is loaded[service.facility_id]
        assert service.service_id == SERVICE_ID
        calculated.append(service.facility_id)
        return original_calculate(snapshot, service, requirement)

    monkeypatch.setattr(facilities_service, "get_snapshot", snapshot)
    monkeypatch.setattr(capacity_engine, "calculate_service_capacity", calculate)
    overview(client)
    assert sorted(calculated) == ["DEMO-A", "DEMO-B", "DEMO-C"]


def test_monitor_update_changes_network_from_five_to_eight_and_keeps_history(
    client, clock, engine
):
    assert row(overview(client), "DEMO-B")["capacity"]["estimated_capacity"] == 5
    before = observation_count(engine)
    with Session(engine) as db:
        old = db.get(ResourceObservation, "OBS-DEMO-B-4")
        historical = (old.available_quantity, old.observed_at, old.recorded_at)
    clock.now += timedelta(minutes=1)
    payload = read(SCENARIOS / "monitor-update.request.json")
    response = client.post("/api/v1/facilities/DEMO-B/observations", json=payload)
    assert response.status_code == 201
    saved = response.json()
    for _ in range(2):  # A second fetch represents returning and refreshing.
        body = overview(client)
        updated = row(body, "DEMO-B")
        result = updated["capacity"]
        assert result["estimated_capacity"] == 8
        assert result["bottleneck_resource_ids"] == ["working-monitors"]
        monitor = next(r for r in result["resource_limits"]
                       if r["resource_id"] == "working-monitors")
        assert monitor["available_quantity"] == monitor["capacity_limit"] == 8
        assert monitor["observation_id"] == saved["observation_id"]
        assert monitor["observed_at"] == payload["observed_at"]
        assert updated["facility"]["last_reported_at"] == saved["recorded_at"]
        assert row(body, "DEMO-A")["capacity"]["estimated_capacity"] is None
        assert row(body, "DEMO-C")["capacity"]["estimated_capacity"] == 0
        assert body["as_of"] == "2026-10-10T09:01:00Z"
    assert observation_count(engine) == before + 1
    with Session(engine) as db:
        old = db.get(ResourceObservation, "OBS-DEMO-B-4")
        assert (old.available_quantity, old.observed_at, old.recorded_at) == historical


def test_current_zero_remains_calculated(client):
    payload = {**read(SCENARIOS / "monitor-update.request.json"), "available_quantity": 0}
    assert client.post("/api/v1/facilities/DEMO-B/observations", json=payload).status_code == 201
    result = row(overview(client), "DEMO-B")["capacity"]
    assert result["status"] == "calculated"
    assert result["estimated_capacity"] == 0
    assert result["bottleneck_resource_ids"] == ["working-monitors"]


def test_aged_reports_become_unknown_without_losing_unavailable_reason(client, clock):
    clock.now += timedelta(days=2)
    body = overview(client)
    result = row(body, "DEMO-B")["capacity"]
    assert result["status"] == "unknown" and result["estimated_capacity"] is None
    assert "stale_required_observation" in result["reason_codes"]
    unavailable = row(body, "DEMO-C")["capacity"]
    assert unavailable["status"] == "unavailable" and unavailable["estimated_capacity"] == 0
    assert unavailable["reason_codes"] == ["service_unavailable", "stale_required_observation"]


@pytest.mark.parametrize("target,attribute", [
    (facilities_service, "get_snapshot"),
    (capacity_service, "get_profiles"),
    (capacity_engine, "calculate_service_capacity"),
])
def test_technical_failure_is_not_a_partial_or_unknown_success(client, monkeypatch,
                                                             target, attribute):
    def fail(*args, **kwargs):
        raise RuntimeError("Injected network integration failure")

    monkeypatch.setattr(target, attribute, fail)
    with TestClient(app, raise_server_exceptions=False) as errors:
        response = errors.get(f"{URL}/overview", params={"service_id": SERVICE_ID})
    assert response.status_code == 500


@pytest.mark.parametrize("path,params,filename,status", [
    ("services", {}, "services.response.json", 200),
    ("overview", {"service_id": "emergency-care"},
     "emergency-care.overview.response.json", 200),
    ("overview", {"service_id": "maternity"}, "unknown-service.overview.response.json", 200),
    ("overview", {}, "missing-service-id.response.json", 422),
])
def test_network_responses_match_published_examples(client, path, params, filename, status):
    response = client.get(f"{URL}/{path}", params=params)
    assert response.status_code == status
    assert response.json() == read(EXAMPLES / "feature-3" / filename)
