"""Backend checks for Feature 4 history import and the forecast endpoint."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines import forecasting as forecasting_engine
from app.main import app
from app.modules.capacity import service as capacity_service
from app.modules.facilities.models import ResourceObservation
from app.modules.forecasting import service as forecasting_service
from app.modules.forecasting.models import DailyResourceRecord, DailyServiceDemand
from app.modules.forecasting.schemas import (
    DailyHistoryImport,
    FacilityForecastResponse,
    ForecastInput,
)

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "contracts" / "examples" / "feature-4"
DATASET = ROOT / "data" / "synthetic" / "feature-4" / "daily-history.json"
NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
URL = "/api/v1/forecasts/facilities"
DEMO_B = f"{URL}/DEMO-B?service_id=emergency-care"


def example(name: str):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def history_payload(**changes) -> DailyHistoryImport:
    payload = example("daily-history.import.json")
    for path, value in changes.items():
        kind, index, field = path.split("__")
        payload[kind][int(index)][field] = value
    return DailyHistoryImport.model_validate(payload)


def counts(engine) -> tuple[int, int, int]:
    with Session(engine) as db:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (DailyResourceRecord, DailyServiceDemand, ResourceObservation)
        )


@pytest.fixture(autouse=True)
def fresh_profiles():
    capacity_service._load_profiles.cache_clear()
    yield
    capacity_service._load_profiles.cache_clear()


class StubEngine:
    """Returns the published example so wiring is tested independently of the model."""

    def __init__(self):
        self.calls: list[ForecastInput] = []

    def __call__(self, inputs: ForecastInput) -> FacilityForecastResponse:
        self.calls.append(inputs)
        payload = example("DEMO-B.forecast.response.json")
        payload.update(facility_id=inputs.facility_id, service_id=inputs.service_id)
        if inputs.requirement is None:
            payload.update(status="not_configured", profile_version=None, forecast=[],
                           alerts=[], validation=None)
        return FacilityForecastResponse.model_validate(payload)


@pytest.fixture
def stub_engine(monkeypatch) -> StubEngine:
    stub = StubEngine()
    monkeypatch.setattr(forecasting_engine, "forecast_service_capacity", stub, raising=False)
    return stub


@pytest.fixture
def server_errors(client) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def imported(engine):
    with Session(engine) as db:
        forecasting_service.import_daily_history(db, history_payload(), NOW)


# Contract examples and schema invariants.


@pytest.mark.parametrize(
    "name", ["DEMO-B.forecast.response.json", "insufficient-history.forecast.response.json"]
)
def test_forecast_examples_match_schema(name):
    payload = example(name)
    assert FacilityForecastResponse.model_validate(payload).model_dump(mode="json") == payload


def test_demo_b_example_flags_first_gap_of_three():
    payload = example("DEMO-B.forecast.response.json")
    first_gap = next(day for day in payload["forecast"] if day["expected_gap"] > 0)
    assert (first_gap["predicted_capacity"], first_gap["predicted_demand"]) == (5, 8)
    assert first_gap["expected_gap"] == 3
    assert payload["alerts"][0]["date"] == first_gap["date"] == payload["forecast"][2]["date"]
    assert len({day["date"] for day in payload["history"]}) >= 56


def _day_change(**fields):
    def change(payload):
        payload["forecast"][2].update(fields)
    return change


@pytest.mark.parametrize(
    "change",
    [
        _day_change(expected_gap=2),  # gap must equal max(0, demand - capacity)
        _day_change(demand_upper=7),  # prediction outside its range
        _day_change(predicted_demand=None),  # unknown never silently allowed
        lambda p: p["forecast"].pop(),  # horizon must be 7 days
        lambda p: p["alerts"].pop(),  # every gap day needs an alert
        lambda p: p["forecast"].reverse(),
        lambda p: p.update(validation=None),
        lambda p: p.update(status="insufficient_history"),  # still has a forecast
        lambda p: p.update(profile_version=None),
        lambda p: p.update(shortage_probability=0.4),
        lambda p: p["history"][0].update(capacity=-1),
    ],
)
def test_contract_violations_are_rejected(change):
    payload = example("DEMO-B.forecast.response.json")
    change(payload)
    with pytest.raises(ValidationError):
        FacilityForecastResponse.model_validate(payload)


# History import.


def test_import_persists_history_separately_from_observations(engine):
    before = counts(engine)
    with Session(engine) as db:
        result = forecasting_service.import_daily_history(db, history_payload(), NOW)

    assert result.model_dump() == {"inserted_resource_records": 6,
                                   "inserted_demand_records": 2, "unchanged_records": 0}
    assert counts(engine) == (before[0] + 6, before[1] + 2, before[2])  # observations untouched


def test_reimport_is_idempotent(engine, imported):
    with Session(engine) as db:
        result = forecasting_service.import_daily_history(db, history_payload(), NOW)
    assert result.unchanged_records == 8 and result.inserted_resource_records == 0


def test_changed_day_is_rejected_and_history_preserved(engine, imported):
    before = counts(engine)
    changed = history_payload(resource_records__2__available_quantity=7)

    with Session(engine) as db, pytest.raises(forecasting_service.HistoryImportError):
        forecasting_service.import_daily_history(db, changed, NOW)

    assert counts(engine) == before
    with Session(engine) as db:
        stored = db.get(DailyResourceRecord, ("DEMO-B", "working-monitors", date(2026, 10, 8)))
        assert stored.available_quantity == 5


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"resource_records__0__unit": "liter"}, "resource_records.0.unit"),
        ({"resource_records__0__available_quantity": 1.5}, "resource_records.0.available_quantity"),
        ({"resource_records__0__facility_id": "DEMO-X"}, "resource_records.0.facility_id"),
        ({"resource_records__0__resource_id": "ventilators"}, "resource_records.0.resource_id"),
        ({"demand_records__0__service_id": "maternity"}, "demand_records.0.service_id"),
        ({"demand_records__0__date": "2026-10-11"}, "demand_records.0.date"),
        ({"resource_records__1__resource_id": "available-beds"}, "resource_records.1: duplicate"),
    ],
)
def test_invalid_import_writes_nothing(engine, changes, problem):
    before = counts(engine)
    with Session(engine) as db, pytest.raises(forecasting_service.HistoryImportError) as caught:
        forecasting_service.import_daily_history(db, history_payload(**changes), NOW)
    assert any(error.startswith(problem) for error in caught.value.errors), caught.value.errors
    assert counts(engine) == before


@pytest.mark.parametrize(
    "change",
    [{"available_quantity": -1}, {"available_quantity": "5"}, {"data_quality": "guessed"},
     {"source": ""}, {"date": "2026-02-30"}, {"extra": 1}],
)
def test_malformed_import_records_are_rejected_by_schema(change):
    payload = example("daily-history.import.json")
    payload["resource_records"][0].update(change)
    with pytest.raises(ValidationError):
        DailyHistoryImport.model_validate(payload)


# Endpoint wiring with a stub engine.


def test_engine_receives_validated_inputs(client, stub_engine, imported):
    response = client.get(DEMO_B)

    assert response.status_code == 200
    assert response.json() == example("DEMO-B.forecast.response.json")
    [inputs] = stub_engine.calls
    assert (inputs.facility_id, inputs.service_id, inputs.service_status) == (
        "DEMO-B", "emergency-care", "operating")
    assert inputs.generated_at == NOW and inputs.horizon_days == 7
    assert inputs.requirement.profile_version == "demo-v1"
    assert [(r.date.isoformat(), r.resource_id) for r in inputs.resource_records] == sorted(
        (r["date"], r["resource_id"])
        for r in example("daily-history.import.json")["resource_records"]
    )
    assert [r.peak_required_places for r in inputs.demand_records] == [5, 4]


def test_engine_gets_only_requested_facility_and_service(client, stub_engine, imported):
    client.get(f"{URL}/DEMO-A?service_id=emergency-care")
    [inputs] = stub_engine.calls
    assert inputs.resource_records == [] and inputs.demand_records == []


def test_missing_profile_is_passed_as_none(client, stub_engine, tmp_path, monkeypatch):
    other = {**example("../feature-2/service-requirement.json"), "service_id": "maternity"}
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps([other]))
    monkeypatch.setattr(capacity_service, "PROFILES_PATH", path)

    body = client.get(DEMO_B).json()

    assert stub_engine.calls[0].requirement is None
    assert body["status"] == "not_configured"


def test_unknown_facility_is_404(client, stub_engine):
    response = client.get(f"{URL}/DEMO-X?service_id=emergency-care")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "facility_not_found"
    assert stub_engine.calls == []


def test_service_not_offered_is_invalid_request(client, stub_engine):
    response = client.get(f"{URL}/DEMO-B?service_id=maternity")
    assert response.status_code == 422
    assert response.json() == example("service-not-offered.response.json")


@pytest.mark.parametrize("query", ["", "?service_id=", "?service_id=bad%20id"])
def test_missing_or_malformed_service_id_is_invalid_request(client, stub_engine, query):
    response = client.get(f"{URL}/DEMO-B{query}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert [f["field"] for f in response.json()["error"]["fields"]] == ["service_id"]


def test_missing_engine_is_a_server_error(server_errors, monkeypatch):
    monkeypatch.delattr(forecasting_engine, "forecast_service_capacity", raising=False)
    assert server_errors.get(DEMO_B).status_code == 500


def test_engine_result_for_wrong_facility_is_a_server_error(server_errors, monkeypatch):
    def wrong(inputs):
        return StubEngine()(inputs.model_copy(update={"facility_id": "DEMO-A"}))

    monkeypatch.setattr(forecasting_engine, "forecast_service_capacity", wrong, raising=False)
    assert server_errors.get(DEMO_B).status_code == 500


def test_forecast_request_writes_nothing(client, engine, stub_engine, imported):
    before = counts(engine)
    client.get(DEMO_B)
    assert counts(engine) == before


# Integration with the real engine and dataset (forecasting/data owner).

def test_real_engine_matches_demo_b_example(client, engine):
    with Session(engine) as db:
        dataset = DailyHistoryImport.model_validate_json(DATASET.read_text(encoding="utf-8"))
        forecasting_service.import_daily_history(db, dataset, NOW)
    before = counts(engine)

    response = client.get(DEMO_B)

    assert response.status_code == 200
    assert response.json() == example("DEMO-B.forecast.response.json")
    assert counts(engine) == before  # forecasts never become observations or history
