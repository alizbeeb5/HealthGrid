"""Evidence rules independent of decisions, completion events, storage and AI."""

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from outcome_fixture_types import FIXTURES, load_case

from app.engines.outcomes import OutcomeValidationError, _evaluate_outcome


def evaluate(data=None, case="supported"):
    return _evaluate_outcome(data or load_case(case))


def row(result, fid="DEMO-B"):
    return next(r for r in result.rows if r.facility_id == fid)


def resource(data, fid="DEMO-B", rid="working-monitors", **changes):
    return replace(
        data,
        snapshots=tuple(
            snapshot.model_copy(
                update={
                    "resources": [
                        r.model_copy(update=changes) if r.resource_id == rid else r
                        for r in snapshot.resources
                    ]
                }
            )
            if snapshot.facility.facility_id == fid
            else snapshot
            for snapshot in data.snapshots
        ),
    )


def test_shared_source_profile_is_preserved():
    data = load_case()
    assert data.requirement.model_dump(mode="json") == json.loads(
        (FIXTURES / "requirement-profile.json").read_text()
    )
    assert data.requirement.model_dump(mode="json") == json.loads(
        (FIXTURES.parent / "feature-7/requirement-profile.json").read_text()
    )


@pytest.mark.parametrize(
    ("case", "status", "observed", "difference"),
    [
        ("supported", "at_or_above_expected", 8, 0),
        ("shortfall", "below_expected", 6, -2),
        ("zero", "below_expected", 0, -8),
        ("unavailable", "below_expected", 0, -8),
        ("insufficient", "insufficient_evidence", None, None),
        ("stale", "insufficient_evidence", None, None),
        ("early", "too_early", 8, None),
        ("late", "at_or_above_expected", 8, 0),
    ],
)
def test_demo_outcomes(case, status, observed, difference):
    result = evaluate(case=case)
    b = row(result)
    assert (b.expected_capacity, b.status, b.observed_capacity, b.capacity_difference) == (
        8,
        status,
        observed,
        difference,
    )
    assert b.required_service_places == 8
    assert b.expected_unmet_against_planned_demand == 0
    assert b.observed_unmet_against_planned_demand == (
        max(0, 8 - observed) if observed is not None else None
    )
    assert row(result, "DEMO-C").expected_capacity is None
    assert "DEMO-C" in result.coverage.excluded_facility_ids


def test_reported_completion_cannot_substitute_for_followup_reports():
    # Execution state is deliberately absent from the numerical interface.
    b = row(evaluate(case="insufficient"))
    assert b.observed_capacity is None
    assert b.status == "insufficient_evidence"
    assert "missing_required_observation" in b.reason_codes
    assert "missing_receipt_timestamp" in b.reason_codes


def test_partial_evidence_exposes_coverage_without_network_success_percentage():
    result = evaluate(case="partial")
    assert row(result, "DEMO-A").status == "insufficient_evidence"
    assert row(result).status == "at_or_above_expected"
    assert result.coverage.comparable_facility_ids == ("DEMO-B",)
    assert result.coverage.excluded_facility_ids == ("DEMO-A", "DEMO-C")
    assert not result.coverage.complete
    assert not hasattr(result, "success_percentage")
    assert not hasattr(result, "observed_network_total")


def test_fully_scoped_coverage_and_above_expected_signed_difference():
    data = load_case()
    data = replace(data, expectations=data.expectations[:2], snapshots=data.snapshots[:2])
    result = evaluate(resource(data, available_quantity=10.0))
    assert result.coverage.complete
    assert row(result).observed_capacity == 10
    assert row(result).capacity_difference == 2
    assert row(result).observed_unmet_against_planned_demand == 0


def test_missing_demand_is_not_zero_and_does_not_prevent_capacity_comparison():
    data = load_case()
    data = replace(
        data,
        expectations=tuple(replace(e, required_service_places=None) for e in data.expectations),
    )
    b = row(evaluate(data))
    assert b.status == "at_or_above_expected" and b.capacity_difference == 0
    assert b.required_service_places is None
    assert b.observed_unmet_against_planned_demand is None
    assert b.expected_unmet_against_planned_demand is None


def test_planned_zero_capacity_and_zero_demand_are_explicit():
    data = load_case()
    data = replace(
        data,
        expectations=tuple(
            replace(e, expected_capacity=0, required_service_places=0)
            if e.facility_id == "DEMO-B"
            else e
            for e in data.expectations
        ),
    )
    b = row(evaluate(resource(data, available_quantity=0.0)))
    assert (b.observed_capacity, b.capacity_difference, b.status) == (0, 0, "at_or_above_expected")
    assert b.observed_unmet_against_planned_demand == 0


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"observation_id": None}, "missing_required_observation"),
        ({"observed_at": None}, "missing_required_observation"),
        ({"available_quantity": None}, "missing_required_observation"),
        ({"recorded_at": None}, "missing_receipt_timestamp"),
    ],
)
def test_every_required_observation_needs_report_provenance(changes, reason):
    b = row(evaluate(resource(load_case(), **changes)))
    assert b.status == "insufficient_evidence" and b.observed_capacity is None
    assert reason in b.reason_codes


@pytest.mark.parametrize(
    ("hours", "seconds", "status"),
    [
        (24, 0, "at_or_above_expected"),
        (24, 1, "insufficient_evidence"),
    ],
)
def test_freshness_boundary_is_relative_to_capture_even_if_cached_label_is_current(
    hours, seconds, status
):
    data = load_case()
    observed = data.captured_at - timedelta(hours=hours, seconds=seconds)
    b = row(
        evaluate(resource(data, observed_at=observed, recorded_at=observed, data_status="current"))
    )
    assert b.status == status
    evidence = next(e for e in b.evidence if e.resource_id == "working-monitors")
    assert evidence.data_status == ("current" if seconds == 0 else "stale")


def test_freshness_can_recover_from_outdated_cached_stale_label():
    b = row(evaluate(resource(load_case(), data_status="stale")))
    assert b.status == "at_or_above_expected"
    assert b.capacity_result.resource_limits[-1].data_status == "current"


def test_window_boundaries_are_inclusive_but_old_baseline_is_not_followup():
    data = load_case()
    data = replace(data, observation_window_starts_at=data.captured_at - timedelta(hours=1))
    b = row(
        evaluate(
            resource(
                data,
                observed_at=data.observation_window_starts_at,
                recorded_at=data.observation_window_starts_at,
            )
        )
    )
    assert b.status == "at_or_above_expected"
    b = row(
        evaluate(
            resource(
                data,
                observed_at=data.observation_window_starts_at - timedelta(seconds=1),
                recorded_at=data.captured_at,
            )
        )
    )
    assert b.status == "insufficient_evidence"
    assert "observation_before_followup_window" in b.reason_codes


def test_observation_at_capture_is_allowed():
    data = load_case()
    b = row(evaluate(resource(data, observed_at=data.captured_at, recorded_at=data.captured_at)))
    assert b.status == "at_or_above_expected"


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("observed_at", "observation_after_capture"),
        ("recorded_at", "receipt_after_capture"),
    ],
)
def test_future_evidence_is_not_credited(field, reason):
    data = load_case()
    b = row(evaluate(resource(data, **{field: data.captured_at + timedelta(seconds=1)})))
    assert b.status == "insufficient_evidence" and reason in b.reason_codes


def test_receipt_before_observation_is_not_credible_followup():
    data = load_case()
    b = row(evaluate(resource(data, recorded_at=data.captured_at - timedelta(hours=1))))
    assert "receipt_before_observation" in b.reason_codes
    assert b.observed_capacity is None


def test_early_and_late_reviews_expose_exact_offset_and_never_claim_on_time_success():
    early = evaluate(case="early")
    assert early.seconds_from_expected_at == -3600
    assert (
        row(early).capacity_difference is None and "before_expected_date" in row(early).reason_codes
    )
    late = evaluate(case="late")
    assert late.seconds_from_expected_at == 172800
    assert "later_capture_does_not_establish_on_time_completion" in row(late).reason_codes


def test_exact_expected_time_is_comparable():
    data = load_case()
    data = replace(data, expected_at=data.captured_at)
    assert row(evaluate(data)).status == "at_or_above_expected"
    assert evaluate(data).seconds_from_expected_at == 0
    assert (
        "later_capture_does_not_establish_on_time_completion"
        not in row(evaluate(data)).reason_codes
    )


@pytest.mark.parametrize(
    ("rid", "quantity", "capacity"),
    [
        ("available-beds", 4.0, 4),
        ("nurses-on-duty", 2.0, 4),
    ],
)
def test_other_resource_bottlenecks_still_limit_outcome(rid, quantity, capacity):
    b = row(evaluate(resource(load_case(), rid=rid, available_quantity=quantity)))
    assert b.observed_capacity == capacity and b.capacity_difference == capacity - 8
    assert b.bottleneck_resource_ids == (rid,)


def test_tied_bottlenecks_are_preserved():
    data = resource(load_case(), rid="available-beds", available_quantity=8.0)
    b = row(evaluate(resource(data, rid="nurses-on-duty", available_quantity=4.0)))
    assert b.bottleneck_resource_ids == ("available-beds", "nurses-on-duty", "working-monitors")


def test_missing_nonrequired_resource_does_not_limit_outcome():
    b = row(
        evaluate(
            resource(
                load_case(),
                rid="oxygen-stock",
                available_quantity=None,
                observed_at=None,
                observation_id=None,
                recorded_at=None,
            )
        )
    )
    assert b.observed_capacity == 8
    assert all(e.resource_id != "oxygen-stock" for e in b.evidence)


def test_missing_required_resource_definition_remains_unknown():
    data = load_case()
    data = replace(
        data,
        snapshots=tuple(
            s.model_copy(
                update={
                    "resources": [r for r in s.resources if r.resource_id != "working-monitors"]
                }
            )
            if s.facility.facility_id == "DEMO-B"
            else s
            for s in data.snapshots
        ),
    )
    b = row(evaluate(data))
    assert b.status == "insufficient_evidence" and b.observed_capacity is None


def test_unavailable_is_explicit_zero_even_with_missing_resource_evidence():
    data = load_case("insufficient")
    data = replace(
        data,
        snapshots=tuple(
            s.model_copy(
                update={
                    "services": [
                        service.model_copy(update={"status": "unavailable"})
                        for service in s.services
                    ]
                }
            )
            if s.facility.facility_id == "DEMO-B"
            else s
            for s in data.snapshots
        ),
    )
    b = row(evaluate(data))
    assert b.status == "below_expected" and b.observed_capacity == 0
    assert b.capacity_difference == -8
    assert "missing_required_observation" in b.reason_codes


def test_limited_service_cannot_be_assumed_fully_operating():
    data = load_case()
    data = replace(
        data,
        snapshots=tuple(
            s.model_copy(
                update={
                    "services": [
                        service.model_copy(update={"status": "limited"}) for service in s.services
                    ]
                }
            )
            if s.facility.facility_id == "DEMO-B"
            else s
            for s in data.snapshots
        ),
    )
    b = row(evaluate(data))
    assert b.status == "insufficient_evidence" and b.observed_capacity is None
    assert "service_restriction_unquantified" in b.reason_codes


def test_missing_snapshot_does_not_drop_expected_hospital():
    data = load_case()
    result = evaluate(replace(data, snapshots=data.snapshots[:1]))
    assert len(result.rows) == 3
    assert row(result).status == "insufficient_evidence"
    assert row(result).observed_capacity is None
    assert "missing_facility_snapshot" in row(result).reason_codes


def test_missing_service_and_profile_are_not_comparable():
    data = load_case()
    snapshots = tuple(
        s.model_copy(update={"services": []}) if s.facility.facility_id == "DEMO-B" else s
        for s in data.snapshots
    )
    assert row(evaluate(replace(data, snapshots=snapshots))).status == "not_comparable"
    assert row(evaluate(replace(data, requirement=None))).status == "not_comparable"


@pytest.mark.parametrize(
    "field", ["baseline_captured_at", "expected_at", "captured_at", "observation_window_starts_at"]
)
def test_naive_timing_is_rejected(field):
    data = load_case()
    with pytest.raises(OutcomeValidationError, match=field):
        evaluate(replace(data, **{field: getattr(data, field).replace(tzinfo=None)}))


@pytest.mark.parametrize(
    "change",
    [
        lambda d: replace(
            d, observation_window_starts_at=d.baseline_captured_at - timedelta(seconds=1)
        ),
        lambda d: replace(d, observation_window_starts_at=d.captured_at + timedelta(seconds=1)),
        lambda d: replace(d, expected_at=d.baseline_captured_at - timedelta(seconds=1)),
        lambda d: replace(d, capacity_unit="patient_day"),
        lambda d: replace(d, expected_profile_version="different"),
        lambda d: replace(d, service_id="maternity"),
        lambda d: replace(d, expectations=d.expectations + d.expectations[:1]),
        lambda d: replace(d, snapshots=d.snapshots + d.snapshots[:1]),
        lambda d: replace(d, expectations=d.expectations[:1]),
    ],
)
def test_incompatible_inputs_are_rejected(change):
    with pytest.raises(OutcomeValidationError):
        evaluate(change(load_case()))


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_invalid_expected_quantities_and_planned_demand_are_rejected(value):
    data = load_case()
    for field in ("expected_capacity", "required_service_places"):
        with pytest.raises(OutcomeValidationError, match=field):
            evaluate(
                replace(
                    data,
                    expectations=(replace(data.expectations[0], **{field: value}),),
                    snapshots=data.snapshots[:1],
                )
            )


@pytest.mark.parametrize("quantity", [-1.0, float("nan"), float("inf"), True, 1.5])
def test_invalid_reported_integer_quantities_are_rejected(quantity):
    with pytest.raises(OutcomeValidationError, match="invalid quantity"):
        evaluate(resource(load_case(), available_quantity=quantity))


def test_mismatched_resource_units_are_rejected():
    with pytest.raises(OutcomeValidationError, match="unit"):
        evaluate(resource(load_case(), unit="person"))


def test_old_snapshot_clock_is_rejected_instead_of_reused_as_capture():
    data = load_case()
    snapshots = (
        data.snapshots[0].model_copy(update={"as_of": data.captured_at - timedelta(seconds=1)}),
    ) + data.snapshots[1:]
    with pytest.raises(OutcomeValidationError, match="as_of"):
        evaluate(replace(data, snapshots=snapshots))


def test_input_reports_and_expectations_are_not_mutated_and_order_is_stable():
    data = load_case("stale")
    before = [s.model_dump(mode="json") for s in data.snapshots]
    first = evaluate(data)
    second = evaluate(
        replace(
            data,
            snapshots=tuple(reversed(data.snapshots)),
            expectations=tuple(reversed(data.expectations)),
        )
    )
    assert first == second
    assert [s.model_dump(mode="json") for s in data.snapshots] == before
    assert data.snapshots[1].resources[-1].data_status == "current"


def test_empty_scope_has_no_fabricated_complete_coverage():
    result = evaluate(replace(load_case(), expectations=(), snapshots=()))
    assert result.rows == () and not result.coverage.complete


def test_unknown_expectation_preserves_observed_capacity_without_inventing_difference():
    data = load_case()
    data = replace(
        data, expectations=tuple(replace(e, expected_capacity=None) for e in data.expectations)
    )
    b = row(evaluate(data))
    assert b.observed_capacity == 8 and b.capacity_difference is None
    assert b.status == "not_comparable" and "expected_capacity_unknown" in b.reason_codes


def test_shared_manual_expectations_match_every_case():
    expected = json.loads((FIXTURES / "demo-expectations.json").read_text())["cases"]
    for case, facts in expected.items():
        actual = evaluate(case=case)
        assert [{key: getattr(r, key) for key in facts["rows"][0]} for r in actual.rows] == (
            facts["rows"]
        )
        assert list(actual.coverage.comparable_facility_ids) == facts["comparable_facility_ids"]
        assert actual.seconds_from_expected_at == facts["seconds_from_expected_at"]


def test_exact_fractional_requirement_is_reused_from_capacity_engine():
    data = load_case()
    requirement = data.requirement.model_copy(
        update={
            "requirements": [
                r.model_copy(update={"required_per_capacity_unit": 1.5})
                if r.resource_id == "working-monitors"
                else r
                for r in data.requirement.requirements
            ]
        }
    )
    b = row(evaluate(replace(data, requirement=requirement)))
    assert b.observed_capacity == 5 and b.capacity_difference == -3


def test_duplicate_resource_and_service_records_are_rejected():
    data = load_case()
    for field in ("resources", "services"):
        snapshot = data.snapshots[0]
        values = getattr(snapshot, field)
        snapshot = snapshot.model_copy(update={field: values + values[:1]})
        with pytest.raises(OutcomeValidationError, match="duplicate"):
            evaluate(replace(data, snapshots=(snapshot,) + data.snapshots[1:]))


def test_resource_timestamp_requires_timezone_even_if_quantity_is_known():
    data = load_case()
    with pytest.raises(OutcomeValidationError, match="observed_at"):
        evaluate(resource(data, observed_at=data.captured_at.replace(tzinfo=None)))


@pytest.mark.parametrize("source_type", ["allocation", "investment"])
@pytest.mark.parametrize("case", ["insufficient", "supported", "below", "early"])
def test_frontend_display_numerical_examples_match_engine(source_type, case):
    """Display is not a wire payload: receipts are explicit synthetic test assumptions.

    This verifies numerical values/classifications, not frontend behavior or live
    evidence provenance. Real capture must supply actual recorded_at timestamps.
    """
    from datetime import datetime

    from outcome_fixture_types import Expectation

    preview = json.loads(
        (FIXTURES.parents[2] / "apps/web/src/features/decisions/demo-display.json").read_text()
    )
    source = next(s for s in preview["sources"] if s["source_type"] == source_type)
    display = preview["reviews"][source_type][case]
    data = load_case()
    captured = datetime.fromisoformat(display["captured_at"])
    snapshots = []
    for shown in display["rows"]:
        base = next(s for s in data.snapshots if s.facility.facility_id == shown["facility_id"])
        observations = {o["resource_id"]: o for o in shown["observations"]}
        reports = []
        for resource in base.resources:
            observation = observations.get(resource.resource_id)
            observed = datetime.fromisoformat(observation["observed_at"]) if observation else None
            reports.append(
                resource.model_copy(
                    update={
                        "available_quantity": observation["quantity"] if observation else None,
                        "observation_id": observation["observation_id"] if observation else None,
                        "observed_at": observed,
                        "recorded_at": observed,  # fictional receipt for this numeric check
                        "unit": observation["unit"] if observation else resource.unit,
                        "data_status": observation["data_status"] if observation else "unknown",
                    }
                )
            )
        snapshots.append(base.model_copy(update={"as_of": captured, "resources": reports}))
    data = replace(
        data,
        snapshots=tuple(snapshots),
        captured_at=captured,
        baseline_captured_at=datetime.fromisoformat(source["baseline_at"]),
        expected_at=datetime.fromisoformat(display["expected_at"]),
        observation_window_starts_at=datetime.fromisoformat(display["window_starts_at"]),
        expected_profile_version=display["profile_version"],
        expectations=tuple(
            Expectation(e["facility_id"], e["capacity"], e["planned_demand"])
            for e in source["expectations"]
        ),
    )
    result = evaluate(data)
    for shown in display["rows"]:
        actual = row(result, shown["facility_id"])
        assert actual.expected_capacity == shown["expected"]
        assert actual.observed_capacity == shown["observed"]
        assert actual.capacity_difference == shown["capacity_difference"]
        assert actual.status == shown["classification"]
    assert list(result.coverage.comparable_facility_ids) == display["comparable_facility_ids"]
