"""Real storage/engine regressions without a browser or HTTP worker thread."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.modules.capacity import service as capacity
from app.modules.forecasting.schemas import DailyHistoryImport
from app.modules.forecasting.service import get_facility_forecast, import_daily_history

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 10, 10, 9, tzinfo=UTC)


@pytest.fixture
def history_db(engine):
    payload = DailyHistoryImport.model_validate_json(
        (ROOT / "data/synthetic/feature-4/daily-history.json").read_text()
    )
    with Session(engine) as db:
        import_daily_history(db, payload, NOW)
        yield db


def test_real_database_engine_matches_wire_example(history_db):
    result = get_facility_forecast(history_db, "DEMO-B", "emergency-care", NOW)
    expected = json.loads(
        (ROOT / "contracts/examples/feature-4/DEMO-B.forecast.response.json").read_text()
    )
    assert result.model_dump(mode="json") == expected
    assert result.forecast[2].expected_gap == 3
    assert result.validation.capacity_mae == result.validation.demand_mae == 1.5


def test_missing_resource_history_is_unknown(history_db):
    result = get_facility_forecast(history_db, "DEMO-A", "emergency-care", NOW)
    assert result.status == "insufficient_history"
    assert result.history[-1].capacity is None
    assert result.forecast == result.alerts == []


def test_no_history_returns_successful_insufficient_state(engine):
    with Session(engine) as db:
        result = get_facility_forecast(db, "DEMO-B", "emergency-care", NOW)
        assert result.status == "insufficient_history" and result.history == []


def test_historical_outage_is_preserved(history_db):
    result = get_facility_forecast(history_db, "DEMO-C", "emergency-care", NOW)
    assert result.status == "forecasted"
    assert result.history[0].capacity == 4  # Current outage did not rewrite the past.
    assert result.history[-1].capacity == 0
    assert all(day.predicted_capacity == 0 for day in result.forecast)


def test_aged_history_returns_insufficient_not_server_error(history_db):
    result = get_facility_forecast(history_db, "DEMO-B", "emergency-care",
                                  NOW + timedelta(days=2))
    assert result.status == "insufficient_history" and result.forecast == []


def test_no_profile_returns_not_configured(history_db, monkeypatch):
    monkeypatch.setattr(capacity, "get_profiles", lambda db: {})
    result = get_facility_forecast(history_db, "DEMO-B", "emergency-care", NOW)
    assert result.status == "not_configured" and result.profile_version is None
    assert result.forecast == []
    assert result.history[0].demand is not None


def test_current_day_aggregate_excluded(history_db):
    payload = DailyHistoryImport.model_validate({"resource_records": [], "demand_records": [{
        "facility_id": "DEMO-B", "service_id": "emergency-care", "date": NOW.date(),
        "peak_required_places": 1000, "source": "synthetic-partial-day",
        "data_quality": "estimated",
    }]})
    import_daily_history(history_db, payload, NOW)
    result = get_facility_forecast(history_db, "DEMO-B", "emergency-care", NOW)
    assert result.history[-1].date < NOW.date()
    assert result.forecast[2].predicted_demand == 8
