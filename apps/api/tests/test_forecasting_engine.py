"""Seasonal baseline tests; synthetic inputs only, no database or provider calls."""

import json
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.engines.forecasting import (
    DailyHistoryRecord,
    ForecastInputError,
    forecast_service_capacity,
)
from app.modules.capacity.schemas import ServiceRequirement
from app.modules.facilities.schemas import FacilitySnapshotResponse

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data/synthetic/feature-4"
NOW = datetime.fromisoformat("2026-10-10T23:59:59Z")


def load(letter="B"):
    return [
        DailyHistoryRecord(
            date=date.fromisoformat(row["date"]),
            snapshot=FacilitySnapshotResponse.model_validate(row["snapshot"]),
            demand=row["demand"],
            source=row["source"],
            data_quality=row["data_quality"],
            capacity_unit=row["capacity_unit"],
            profile_version=row["profile_version"],
        )
        for row in json.loads((DATA / f"DEMO-{letter}.history.json").read_text())
    ]


@pytest.fixture
def profile():
    return ServiceRequirement.model_validate(
        json.loads((ROOT / "data/synthetic/feature-2/service-requirement.json").read_text())
    )


def test_three_hospitals_have_eight_consecutive_weeks():
    for letter in "ABC":
        records = load(letter)
        assert len(records) == 56
        assert records[0].date == date(2026, 8, 16)
        assert records[-1].date == date(2026, 10, 10)
        assert all(r.data_quality == "synthetic" and r.source for r in records)
        assert all(b.date == a.date + timedelta(days=1) for a, b in zip(records, records[1:]))


def test_demo_gap_and_validation_errors(profile):
    result = forecast_service_capacity(load(), profile, NOW)
    assert len(result.history) == 56 and len(result.forecast) == 7
    assert result.forecast[0].expected_gap == result.forecast[1].expected_gap == 0
    third = result.forecast[2]
    assert third.date == date(2026, 10, 13)
    assert (third.predicted_capacity, third.predicted_demand, third.expected_gap) == (5, 8, 3)
    assert (third.capacity_lower, third.capacity_upper) == (3, 7)
    assert (third.demand_lower, third.demand_upper) == (6, 10)
    assert result.alerts[0].date == third.date and result.alerts[0].expected_gap == 3
    assert result.validation.capacity_mae == result.validation.demand_mae == 1.5
    assert result.validation.training_days == 42
    assert result.validation.evaluated_days == result.validation.withheld_days == 14


@pytest.mark.parametrize("letter", ["B", "C"])
def test_expected_outputs_reproducible(profile, letter):
    result = forecast_service_capacity(load(letter), profile, NOW)
    serialized = json.loads(json.dumps(asdict(result), default=lambda value: value.isoformat()))
    expected = json.loads((DATA / f"DEMO-{letter}.expected-engine-result.json").read_text())
    assert serialized == expected


def test_missing_history_not_zero(profile):
    with pytest.raises(ForecastInputError, match="known capacity and demand"):
        forecast_service_capacity(load("A"), profile, NOW)


def test_unavailable_zero_is_valid_and_keeps_reason(profile):
    result = forecast_service_capacity(load("C"), profile, NOW)
    assert all(day.predicted_capacity == 0 for day in result.forecast)
    assert result.history[-1].modeled_capacity == 0
    assert result.history[-1].reason_codes == ("service_unavailable",)


def test_insufficient_history(profile):
    with pytest.raises(ForecastInputError, match="56"):
        forecast_service_capacity(load()[1:], profile, NOW)


def test_missing_and_duplicate_dates_rejected(profile):
    records = load()
    for bad in (records[:10] + records[11:], records + [records[-1]]):
        with pytest.raises(ForecastInputError):
            forecast_service_capacity(bad, profile, NOW)


def test_weekly_baseline_missing_value_rejected(profile):
    records = load()
    records[-21] = replace(records[-21], demand=None)
    with pytest.raises(ForecastInputError, match="baseline"):
        forecast_service_capacity(records, profile, NOW)


def test_heldout_missing_value_rejected(profile):
    records = load()
    records[-10] = replace(records[-10], demand=None)
    with pytest.raises(ForecastInputError, match="withheld"):
        forecast_service_capacity(records, profile, NOW)


def test_earlier_missing_demand_remains_unknown(profile):
    records = load()
    records[0] = replace(records[0], demand=None)
    result = forecast_service_capacity(records, profile, NOW)
    assert result.history[0].demand is None
    assert result.forecast[2].expected_gap == 3


def test_stale_required_observation_rejected(profile):
    records = load()
    snapshot = records[-1].snapshot.model_copy(deep=True)
    monitor = next(r for r in snapshot.resources if r.resource_id == "working-monitors")
    monitor.data_status = "stale"
    monitor.observed_at -= timedelta(days=2)
    records[-1] = replace(records[-1], snapshot=snapshot)
    with pytest.raises(ForecastInputError, match="withheld"):
        forecast_service_capacity(records, profile, NOW)


@pytest.mark.parametrize(
    "field,value",
    [
        ("capacity_unit", "patients_per_day"),
        ("profile_version", "other-v2"),
        ("source", ""),
        ("data_quality", "unsupported"),
        ("demand", -1),
        ("demand", True),
        ("demand", 1.5),
        ("demand", float("nan")),
        ("demand", float("inf")),
    ],
)
def test_incompatible_or_invalid_daily_inputs(profile, field, value):
    records = load()
    records[0] = replace(records[0], **{field: value})
    with pytest.raises(ForecastInputError):
        forecast_service_capacity(records, profile, NOW)


def test_facility_and_service_mismatch_rejected(profile):
    records = load()
    snapshot = records[0].snapshot.model_copy(deep=True)
    snapshot.facility.facility_id = "DEMO-A"
    records[0] = replace(records[0], snapshot=snapshot)
    with pytest.raises((ForecastInputError, ValueError)):
        forecast_service_capacity(records, profile, NOW)
    with pytest.raises(ForecastInputError):
        forecast_service_capacity(load(), profile.model_copy(update={"service_id": "other"}), NOW)


def test_generation_clock_and_daily_timestamp_validation(profile):
    with pytest.raises(ForecastInputError):
        forecast_service_capacity(load(), profile, NOW.replace(tzinfo=None))
    with pytest.raises(ForecastInputError, match="stale history"):
        forecast_service_capacity(load(), profile, NOW + timedelta(days=1))
    records = load()
    snapshot = records[0].snapshot.model_copy(deep=True)
    snapshot.as_of += timedelta(days=1)
    records[0] = replace(records[0], snapshot=snapshot)
    with pytest.raises(ForecastInputError, match="timestamp"):
        forecast_service_capacity(records, profile, NOW)


def test_no_validation_leakage_from_withheld_targets(profile):
    records = load()
    original = forecast_service_capacity(records, profile, NOW)
    # Perturb a withheld target outside the final forecasting baseline. A model
    # trained using that target would hide its error; training must stay fixed.
    records[-10] = replace(records[-10], demand=records[-10].demand + 100)
    changed = forecast_service_capacity(records, profile, NOW)
    assert changed.validation.demand_mae > original.validation.demand_mae + 6
    assert [d.predicted_demand for d in changed.forecast] == [
        d.predicted_demand for d in original.forecast
    ]
    assert changed.validation.capacity_mae == original.validation.capacity_mae


def test_gap_nonnegative_and_ranges_enclose_predictions(profile):
    for letter in "BC":
        result = forecast_service_capacity(load(letter), profile, NOW)
        for day in result.forecast:
            assert day.expected_gap == max(0, day.predicted_demand - day.predicted_capacity)
            assert 0 <= day.capacity_lower <= day.predicted_capacity <= day.capacity_upper
            assert 0 <= day.demand_lower <= day.predicted_demand <= day.demand_upper
        assert all(alert.expected_gap > 0 for alert in result.alerts)
        assert not hasattr(result, "shortage_probability")


def test_capacity_uses_existing_engine_and_inputs_unchanged(profile, monkeypatch):
    from app.engines import forecasting

    original = forecasting.calculate_service_capacity
    calls = []

    def spy(snapshot, service, requirement):
        calls.append((snapshot, service, requirement))
        return original(snapshot, service, requirement)

    monkeypatch.setattr(forecasting, "calculate_service_capacity", spy)
    records = load()
    before = [r.snapshot.model_dump() for r in records]
    profile_before = profile.model_dump()
    forecast_service_capacity(records, profile, NOW)
    assert len(calls) == 56
    assert all(snapshot is record.snapshot for (snapshot, _, _), record in zip(calls, records))
    assert before == [r.snapshot.model_dump() for r in records]
    assert profile.model_dump() == profile_before
