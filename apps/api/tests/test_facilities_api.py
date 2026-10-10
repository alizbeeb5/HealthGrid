import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.facilities.models import ResourceDefinition, ResourceObservation
from app.modules.facilities.seed import FIXTURES

URL = "/api/v1/facilities"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def observation_count(engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(ResourceObservation))


def resource(snapshot: dict, resource_id: str) -> dict:
    return next(r for r in snapshot["resources"] if r["resource_id"] == resource_id)


def post(client, body: dict, facility_id: str = "DEMO-A"):
    return client.post(f"{URL}/{facility_id}/observations", json=body)


def test_list_matches_agreed_payload(client):
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json() == fixture("facilities.response.json")


@pytest.mark.parametrize("facility_id", ["DEMO-A", "DEMO-B", "DEMO-C"])
def test_snapshot_matches_agreed_payload(client, facility_id):
    response = client.get(f"{URL}/{facility_id}/snapshot")
    assert response.status_code == 200
    assert response.json() == fixture(f"{facility_id}.snapshot.response.json")


def test_unknown_facility_returns_contract_404(client):
    for response in (
        client.get(f"{URL}/DEMO-X/snapshot"),
        post(client, fixture("observation.request.json"), "DEMO-X"),
    ):
        assert response.status_code == 404
        assert response.json() == fixture("not-found.response.json")


def test_unreported_resource_is_unknown_not_zero(client):
    monitors = resource(client.get(f"{URL}/DEMO-A/snapshot").json(), "working-monitors")
    assert monitors["available_quantity"] is None
    assert monitors["observed_at"] is None and monitors["recorded_at"] is None
    assert monitors["data_status"] == "unknown"


def test_update_appends_and_becomes_latest(client, clock, engine):
    before = observation_count(engine)
    clock.now += timedelta(minutes=1)
    request = fixture("observation.request.json")

    response = post(client, request)

    assert response.status_code == 201
    body = response.json()
    expected = fixture("observation.response.json")
    assert {k: body[k] for k in request} == request
    assert body["facility_id"] == "DEMO-A"
    assert body["recorded_at"] == expected["recorded_at"]  # server receipt time
    assert body["observation_id"].startswith("OBS-")
    assert observation_count(engine) == before + 1

    snapshot = client.get(f"{URL}/DEMO-A/snapshot").json()
    beds = resource(snapshot, "available-beds")
    assert beds["observation_id"] == body["observation_id"]
    assert beds["available_quantity"] == 10
    assert beds["observed_at"] == request["observed_at"]
    assert beds["recorded_at"] == body["recorded_at"]
    assert snapshot["facility"]["last_reported_at"] == body["recorded_at"]

    with Session(engine) as db:
        previous = db.get(ResourceObservation, "OBS-DEMO-A-1")
        assert previous.available_quantity == 12  # history is preserved


def test_older_report_is_kept_but_does_not_replace_newer(client, engine):
    before = observation_count(engine)
    late = {**fixture("observation.request.json"), "observed_at": "2026-10-10T08:00:00Z"}

    assert post(client, late).status_code == 201

    assert observation_count(engine) == before + 1
    beds = resource(client.get(f"{URL}/DEMO-A/snapshot").json(), "available-beds")
    assert beds["observation_id"] == "OBS-DEMO-A-1"
    assert beds["available_quantity"] == 12


def test_same_observed_at_prefers_latest_receipt(client, clock):
    clock.now += timedelta(minutes=1)
    same_time = {**fixture("observation.request.json"), "observed_at": "2026-10-10T08:30:00Z"}

    created = post(client, same_time).json()

    beds = resource(client.get(f"{URL}/DEMO-A/snapshot").json(), "available-beds")
    assert beds["observation_id"] == created["observation_id"]


def test_first_report_turns_unknown_into_current_zero(client):
    zero = {
        "resource_id": "working-monitors",
        "available_quantity": 0,
        "unit": "item",
        "observed_at": "2026-10-10T08:50:00Z",
    }
    assert post(client, zero).status_code == 201

    monitors = resource(client.get(f"{URL}/DEMO-A/snapshot").json(), "working-monitors")
    assert monitors["available_quantity"] == 0
    assert monitors["data_status"] == "current"


def test_offset_timestamp_is_normalized_to_utc(client):
    body = {**fixture("observation.request.json"), "observed_at": "2026-10-10T11:55:00+03:00"}
    response = post(client, body)
    assert response.status_code == 201
    assert response.json()["observed_at"] == "2026-10-10T08:55:00Z"


def test_fractional_quantity_allowed_where_configured(client):
    body = {
        "resource_id": "oxygen-stock",
        "available_quantity": 750.25,
        "unit": "liter",
        "observed_at": "2026-10-10T08:55:00Z",
    }
    assert post(client, body).status_code == 201


def test_old_observation_is_accepted_as_history(client):
    body = {**fixture("observation.request.json"), "observed_at": "2025-01-01T00:00:00Z"}
    assert post(client, body).status_code == 201


@pytest.mark.parametrize(
    "case", fixture("invalid-observations.json"), ids=lambda case: case["case"]
)
def test_invalid_observation_is_rejected_without_saving(client, engine, case):
    before = observation_count(engine)

    response = post(client, case["request"])

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_observation"
    assert case["expected_field"] in {field["field"] for field in error["fields"]}
    assert observation_count(engine) == before


def test_unit_mismatch_matches_agreed_error(client):
    body = {**fixture("observation.request.json"), "unit": "liter"}
    response = post(client, body)
    assert response.status_code == 422
    assert response.json() == fixture("validation-error.response.json")


def test_resource_not_applicable_to_facility_is_rejected(client, engine):
    with Session(engine) as db:
        db.add(
            ResourceDefinition(
                resource_id="ventilators",
                name="Ventilators",
                category="equipment",
                unit="item",
                allows_fractional=False,
            )
        )
        db.commit()
    body = {**fixture("observation.request.json"), "resource_id": "ventilators", "unit": "item"}

    response = post(client, body)

    assert response.status_code == 422
    assert [f["field"] for f in response.json()["error"]["fields"]] == ["resource_id"]


def test_malformed_body_is_non_field_error(client):
    response = client.post(
        f"{URL}/DEMO-A/observations",
        content="{not json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_observation"
    assert response.json()["error"]["fields"] == []


def test_invalid_path_uses_invalid_request(client):
    response = client.get(f"{URL}/{'X' * 65}/snapshot")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
