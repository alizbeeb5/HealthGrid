"""Canonical outcome DTOs and independent backend verification."""

from datetime import timedelta

import pytest
from outcome_fixture_types import load_case

from app.engines.outcomes import evaluate_outcome
from app.modules.decisions.schemas import OutcomeEvaluationInput, OutcomeFacilityInput
from app.modules.decisions.service import check_outcome


def inputs(case="supported"):
    fixture = load_case(case)
    return OutcomeEvaluationInput(
        service_id=fixture.service_id,
        capacity_unit=fixture.capacity_unit,
        requirement=fixture.requirement,
        expected_at=fixture.expected_at,
        target_completion_at=fixture.expected_at + timedelta(days=1),
        captured_at=fixture.captured_at,
        observation_window_starts_at=fixture.observation_window_starts_at,
        stale_after_hours=24,
        decision_status="completed",
        facilities=[
            OutcomeFacilityInput(
                facility_id=e.facility_id,
                expected_capacity=e.expected_capacity,
                capacity_before=3,
                required_service_places=e.required_service_places,
                snapshot=s,
            )
            for e, s in zip(fixture.expectations[:2], fixture.snapshots[:2], strict=True)
        ],
        excluded_facilities=[{"facility_id": "DEMO-C", "reasons": ["service_unavailable"]}],
    )


@pytest.mark.parametrize(
    ("case", "capacity", "difference", "classification"),
    [
        ("supported", 8, 0, "at_or_above_expected"),
        ("shortfall", 6, -2, "below_expected"),
        ("zero", 0, -8, "below_expected"),
        ("unavailable", 0, -8, "below_expected"),
        ("insufficient", None, None, "insufficient_evidence"),
        ("stale", None, None, "insufficient_evidence"),
        ("early", None, None, "too_early"),
        ("late", 8, 0, "at_or_above_expected"),
    ],
)
def test_canonical_results_are_independently_verified(case, capacity, difference, classification):
    data = inputs(case)
    before = data.model_dump(mode="json")
    result = evaluate_outcome(data)
    b = result.facilities[1]
    assert (b.observed_capacity, b.capacity_difference, b.classification) == (
        capacity,
        difference,
        classification,
    )
    assert check_outcome(data, result) == []
    assert data.model_dump(mode="json") == before
    assert result.coverage.excluded_facilities == data.excluded_facilities
    if case == "early":
        assert b.observed.estimated_capacity == 8  # visible observation, no target verdict


def change_monitor(data, **changes):
    b = data.facilities[1]
    snapshot = b.snapshot.model_copy(
        update={
            "resources": [
                r.model_copy(update=changes) if r.resource_id == "working-monitors" else r
                for r in b.snapshot.resources
            ]
        }
    )
    return data.model_copy(
        update={"facilities": [data.facilities[0], b.model_copy(update={"snapshot": snapshot})]}
    )


@pytest.mark.parametrize("cached_status", ["current", "stale", "unknown"])
def test_receipt_and_actual_times_take_precedence_over_cached_status(cached_status):
    data = change_monitor(inputs(), data_status=cached_status)
    result = evaluate_outcome(data)
    assert result.facilities[1].observed_capacity == 8
    assert check_outcome(data, result) == []
    assert result.facilities[1].evidence[-1].data_status == cached_status
    assert result.facilities[1].evidence[-1].evidence_status == "fresh"


@pytest.mark.parametrize(
    "change",
    [
        lambda d: {"recorded_at": None},
        lambda d: {"recorded_at": d.captured_at + timedelta(seconds=1)},
        lambda d: {"observed_at": d.captured_at + timedelta(seconds=1)},
        lambda d: {
            "observed_at": d.captured_at - timedelta(hours=24, seconds=1),
            "recorded_at": d.captured_at - timedelta(hours=24),
        },
    ],
)
def test_unusable_metadata_remains_unknown_and_passes_independent_check(change):
    data = inputs()
    data = change_monitor(data, **change(data))
    result = evaluate_outcome(data)
    assert result.facilities[1].observed_capacity is None
    assert result.facilities[1].classification == "insufficient_evidence"
    assert check_outcome(data, result) == []


def test_absent_resource_record_is_missing_evidence_not_internal_failure():
    data = inputs()
    b = data.facilities[1]
    snapshot = b.snapshot.model_copy(
        update={
            "resources": [r for r in b.snapshot.resources if r.resource_id != "working-monitors"]
        }
    )
    data = data.model_copy(
        update={"facilities": [data.facilities[0], b.model_copy(update={"snapshot": snapshot})]}
    )
    result = evaluate_outcome(data)
    assert result.facilities[1].evidence[-1].observation_id is None
    assert result.facilities[1].observed_capacity is None
    assert check_outcome(data, result) == []


def test_unavailable_with_missing_reports_preserves_explicit_zero():
    data = inputs("unavailable")
    data = change_monitor(
        data, observation_id=None, observed_at=None, recorded_at=None, available_quantity=None
    )
    result = evaluate_outcome(data)
    assert result.facilities[1].observed_capacity == 0
    assert result.facilities[1].evidence[-1].evidence_status == "missing"
    assert check_outcome(data, result) == []


def test_completion_and_owner_target_do_not_manufacture_capacity_or_replace_expected_date():
    data = inputs("insufficient")
    approved = data.model_copy(
        update={
            "decision_status": "approved",
            "target_completion_at": data.captured_at + timedelta(days=30),
        }
    )
    assert evaluate_outcome(approved) == evaluate_outcome(data)
    data = inputs("early")
    data = data.model_copy(update={"target_completion_at": data.captured_at - timedelta(days=1)})
    assert evaluate_outcome(data).timing == "too_early"


def test_equivalent_aware_input_timezones_are_normalized_without_changing_comparison():
    from datetime import timezone

    data = inputs()
    tz = timezone(timedelta(hours=3))
    shifted = data.model_copy(
        update={
            "expected_at": data.expected_at.astimezone(tz),
            "target_completion_at": data.target_completion_at.astimezone(tz),
            "observation_window_starts_at": data.observation_window_starts_at.astimezone(tz),
        }
    )
    assert evaluate_outcome(shifted) == evaluate_outcome(data)
    assert check_outcome(shifted, evaluate_outcome(shifted)) == []
