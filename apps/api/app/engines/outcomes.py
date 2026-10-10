"""Pure follow-up evidence comparison; canonical DTO binding belongs to backend/data.

No database, HTTP, system clock, AI or optimizer calls. Follow-up observations are
validated against the supplied capture time, then the existing capacity engine
calculates modeled capacity using the frozen source requirement profile.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from types import SimpleNamespace
from typing import Protocol, Sequence

from app.engines.capacity import CAPACITY_UNIT, calculate_service_capacity
from app.modules.capacity.schemas import ServiceCapacityResult, ServiceRequirement
from app.modules.decisions.schemas import (
    FacilityOutcome,
    OutcomeCoverage,
    OutcomeEvaluationInput,
    OutcomeEvaluationResult,
    ResourceEvidence,
)
from app.modules.facilities.schemas import FacilitySnapshotResponse, ResourceSnapshot

ENGINE_VERSION = "outcome-review-v1"


class OutcomeValidationError(ValueError):
    """Incompatible frozen inputs; do not publish an apparently valid comparison."""


class _ExpectationInput(Protocol):
    facility_id: str
    expected_capacity: int | None
    required_service_places: int | None


class _Problem(Protocol):
    """Internal interface only; not a second public Pydantic/wire contract."""

    service_id: str
    capacity_unit: str
    expected_profile_version: str
    requirement: ServiceRequirement | None
    baseline_captured_at: datetime | None
    expected_at: datetime
    captured_at: datetime
    observation_window_starts_at: datetime
    expectations: Sequence[_ExpectationInput]
    snapshots: Sequence[FacilitySnapshotResponse]


@dataclass(frozen=True)
class _Evidence:
    resource_id: str
    unit: str
    observation_id: str | None
    available_quantity: float | None
    observed_at: datetime | None
    recorded_at: datetime | None
    data_status: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class _Row:
    facility_id: str
    expected_capacity: int | None
    observed_capacity: int | None
    capacity_difference: int | None
    status: str
    reason_codes: tuple[str, ...]
    required_service_places: int | None
    expected_unmet_against_planned_demand: int | None
    observed_unmet_against_planned_demand: int | None
    bottleneck_resource_ids: tuple[str, ...]
    evidence: tuple[_Evidence, ...]
    capacity_result: ServiceCapacityResult | None


@dataclass(frozen=True)
class _Coverage:
    expected_facility_ids: tuple[str, ...]
    comparable_facility_ids: tuple[str, ...]
    excluded_facility_ids: tuple[str, ...]
    complete: bool


@dataclass(frozen=True)
class _KernelResult:
    engine_version: str
    service_id: str
    capacity_unit: str
    profile_version: str | None
    captured_at: datetime
    expected_at: datetime
    observation_window_starts_at: datetime
    seconds_from_expected_at: float
    rows: tuple[_Row, ...]
    coverage: _Coverage


def _utc(value, field):
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise OutcomeValidationError(f"{field}: supply an aware UTC timestamp.")


def _count(value, field):
    if value is not None and (type(value) is not int or value < 0):
        raise OutcomeValidationError(f"{field}: use a nonnegative whole number or null.")


def _validate(data: _Problem):
    for field in (
        "baseline_captured_at",
        "expected_at",
        "captured_at",
        "observation_window_starts_at",
    ):
        if field != "baseline_captured_at" or data.baseline_captured_at is not None:
            _utc(getattr(data, field), field)
    if data.observation_window_starts_at > data.captured_at or (
        data.baseline_captured_at is not None
        and data.observation_window_starts_at < data.baseline_captured_at
    ):
        raise OutcomeValidationError(
            "observation_window_starts_at: must be between baseline and capture."
        )
    if data.baseline_captured_at is not None and data.expected_at < data.baseline_captured_at:
        raise OutcomeValidationError("expected_at: cannot precede the source baseline.")
    if not data.service_id or data.capacity_unit != CAPACITY_UNIT:
        raise OutcomeValidationError("Use one known service and simultaneous_service_place units.")
    if not data.expected_profile_version.strip():
        raise OutcomeValidationError("expected_profile_version: supply the frozen profile version.")
    profile = data.requirement
    if profile is not None and (
        profile.service_id != data.service_id
        or profile.capacity_unit != data.capacity_unit
        or profile.profile_version != data.expected_profile_version
    ):
        raise OutcomeValidationError(
            "requirement: must match the source service, unit and profile version."
        )
    expected = {}
    for i, row in enumerate(data.expectations):
        if not row.facility_id or row.facility_id in expected:
            raise OutcomeValidationError(
                f"expectations.{i}.facility_id: must be unique and nonblank."
            )
        _count(row.expected_capacity, f"expectations.{i}.expected_capacity")
        _count(row.required_service_places, f"expectations.{i}.required_service_places")
        expected[row.facility_id] = row
    snapshots = {}
    for i, snapshot in enumerate(data.snapshots):
        fid = snapshot.facility.facility_id
        if fid not in expected or fid in snapshots:
            raise OutcomeValidationError(
                f"snapshots.{i}.facility_id: unexpected or duplicate facility."
            )
        _utc(snapshot.as_of, f"snapshots.{i}.as_of")
        if snapshot.as_of != data.captured_at:
            raise OutcomeValidationError(
                f"snapshots.{i}.as_of: must equal the review capture time."
            )
        if type(snapshot.stale_after_hours) is not int or snapshot.stale_after_hours <= 0:
            raise OutcomeValidationError(f"snapshots.{i}.stale_after_hours: must be positive.")
        resource_ids = [r.resource_id for r in snapshot.resources]
        if len(set(resource_ids)) != len(resource_ids):
            raise OutcomeValidationError(f"snapshots.{i}.resources: duplicate resource IDs.")
        service_ids = [s.service_id for s in snapshot.services]
        if len(set(service_ids)) != len(service_ids) or any(
            s.facility_id != fid for s in snapshot.services
        ):
            raise OutcomeValidationError(
                f"snapshots.{i}.services: duplicate or mismatched services."
            )
        for resource in snapshot.resources:
            for field in ("observed_at", "recorded_at"):
                value = getattr(resource, field)
                if value is not None:
                    _utc(value, f"snapshots.{i}.{resource.resource_id}.{field}")
            quantity = resource.available_quantity
            if quantity is not None and (
                isinstance(quantity, bool)
                or not isfinite(quantity)
                or quantity < 0
                or (not resource.allows_fractional and quantity != int(quantity))
            ):
                raise OutcomeValidationError(
                    f"snapshots.{i}.{resource.resource_id}: invalid quantity."
                )
        snapshots[fid] = snapshot
    return expected, snapshots


def _evidence(resource: ResourceSnapshot | None, rule, snapshot, data):
    reasons = set()
    if resource is None:
        return _Evidence(
            rule.resource_id,
            str(rule.unit),
            None,
            None,
            None,
            None,
            "unknown",
            ("missing_required_observation",),
        )
    if resource.unit != rule.unit:
        raise OutcomeValidationError(
            f"{snapshot.facility.facility_id}.{rule.resource_id}.unit: "
            "does not match the frozen profile."
        )
    if (
        not resource.observation_id
        or resource.available_quantity is None
        or (resource.observed_at is None)
    ):
        reasons.add("missing_required_observation")
    if resource.recorded_at is None:
        reasons.add("missing_receipt_timestamp")
    elif resource.recorded_at > data.captured_at:
        reasons.add("receipt_after_capture")
    observed = resource.observed_at
    if observed is not None:
        if observed > data.captured_at:
            reasons.add("observation_after_capture")
        if observed < data.observation_window_starts_at:
            reasons.add("observation_before_followup_window")
        if (data.captured_at - observed).total_seconds() > snapshot.stale_after_hours * 3600:
            reasons.add("stale_required_observation")
        if resource.recorded_at is not None and resource.recorded_at < observed:
            reasons.add("receipt_before_observation")
    status = (
        "stale"
        if reasons == {"stale_required_observation"}
        else ("unknown" if reasons else "current")
    )
    return _Evidence(
        resource.resource_id,
        str(resource.unit),
        resource.observation_id,
        resource.available_quantity,
        observed,
        resource.recorded_at,
        status,
        tuple(sorted(reasons)),
    )


def _evaluate_outcome(data: _Problem) -> _KernelResult:
    """Internal numerical routine; the public binding maps canonical engine types.

    Explicit unavailable status is captured current service evidence and yields
    zero even with missing resource reports. It does not establish historical
    service status. Missing resource evidence remains visible alongside that zero.
    """
    expectations, snapshots = _validate(data)
    rows = []
    for fid, expectation in sorted(expectations.items()):
        snapshot = snapshots.get(fid)
        profile = data.requirement
        reasons = set()
        evidence = ()
        capacity = None
        if snapshot is None:
            reasons.add("missing_facility_snapshot")
        else:
            service = next((s for s in snapshot.services if s.service_id == data.service_id), None)
            if profile is not None:
                resources = {r.resource_id: r for r in snapshot.resources}
                evidence = tuple(
                    _evidence(resources.get(rule.resource_id), rule, snapshot, data)
                    for rule in sorted(profile.requirements, key=lambda r: r.resource_id)
                )
                # Replace freshness labels only on copies; supplied reports stay intact.
                statuses = {e.resource_id: e.data_status for e in evidence}
                normalized = snapshot.model_copy(
                    update={
                        "resources": [
                            r.model_copy(update={"data_status": statuses[r.resource_id]})
                            if r.resource_id in statuses
                            else r.model_copy()
                            for r in snapshot.resources
                        ]
                    }
                )
            else:
                normalized = snapshot.model_copy(deep=True)
            if service is None:
                reasons.add("service_not_offered")
            else:
                try:
                    capacity = calculate_service_capacity(normalized, service, profile)
                except ValueError as exc:
                    raise OutcomeValidationError(f"{fid}: {exc}") from exc
                reasons.update(str(r) for r in capacity.reason_codes)
            reasons.update(reason for entry in evidence for reason in entry.reason_codes)
        if profile is None:
            reasons.add("requirements_not_configured")
        if expectation.expected_capacity is None:
            reasons.add("expected_capacity_unknown")
        observed = capacity.estimated_capacity if capacity is not None else None
        comparable = (
            profile is not None
            and expectation.expected_capacity is not None
            and (capacity is not None and capacity.status in ("calculated", "unavailable"))
        )
        if (
            profile is None
            or expectation.expected_capacity is None
            or (snapshot is not None and "service_not_offered" in reasons)
        ):
            status = "not_comparable"
        elif data.captured_at < data.expected_at:
            status = "too_early"
            reasons.add("before_expected_date")
        elif not comparable:
            status = "insufficient_evidence"
        else:
            status = (
                "at_or_above_expected"
                if observed >= expectation.expected_capacity
                else ("below_expected")
            )
        if data.captured_at > data.expected_at:
            reasons.add("later_capture_does_not_establish_on_time_completion")
        difference = (
            observed - expectation.expected_capacity
            if status in ("at_or_above_expected", "below_expected")
            else None
        )
        demand = expectation.required_service_places
        rows.append(
            _Row(
                fid,
                expectation.expected_capacity,
                observed,
                difference,
                status,
                tuple(sorted(reasons)),
                demand,
                max(0, demand - expectation.expected_capacity)
                if demand is not None and expectation.expected_capacity is not None
                else None,
                max(0, demand - observed) if demand is not None and observed is not None else None,
                tuple(capacity.bottleneck_resource_ids) if capacity is not None else (),
                evidence,
                capacity,
            )
        )
    comparable_ids = tuple(r.facility_id for r in rows if r.capacity_difference is not None)
    all_ids = tuple(r.facility_id for r in rows)
    return _KernelResult(
        ENGINE_VERSION,
        data.service_id,
        data.capacity_unit,
        data.requirement.profile_version if data.requirement is not None else None,
        data.captured_at,
        data.expected_at,
        data.observation_window_starts_at,
        (data.captured_at - data.expected_at).total_seconds(),
        tuple(rows),
        _Coverage(
            all_ids,
            comparable_ids,
            tuple(fid for fid in all_ids if fid not in comparable_ids),
            bool(all_ids) and len(comparable_ids) == len(all_ids),
        ),
    )


def evaluate_outcome(data: OutcomeEvaluationInput) -> OutcomeEvaluationResult:
    """Canonical pure entry; source-baseline window checks are enforced by the backend.

    The public schema reserves observed_capacity for target-comparable rows. A
    fresh early estimate is retained in observed (the capacity result), with no
    difference/unmet target claim. Completion and owner deadlines do not determine
    the classification.
    """

    def canonical_time(value, field):
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise OutcomeValidationError(f"{field}: supply an aware timestamp.")
        return value.astimezone(UTC)

    canonical_time(data.target_completion_at, "target_completion_at")
    if type(data.stale_after_hours) is not int or data.stale_after_hours <= 0:
        raise OutcomeValidationError("stale_after_hours: must be positive.")
    for facility in data.facilities:
        if facility.facility_id != facility.snapshot.facility.facility_id:
            raise OutcomeValidationError("facilities: snapshot must match facility_id.")
        if facility.snapshot.stale_after_hours != data.stale_after_hours:
            raise OutcomeValidationError("facilities: freshness policy must match the capture.")
    problem = SimpleNamespace(
        service_id=data.service_id,
        capacity_unit=data.capacity_unit,
        expected_profile_version=data.requirement.profile_version,
        requirement=data.requirement,
        baseline_captured_at=None,
        expected_at=canonical_time(data.expected_at, "expected_at"),
        captured_at=data.captured_at,
        observation_window_starts_at=canonical_time(
            data.observation_window_starts_at, "observation_window_starts_at"
        ),
        expectations=[
            SimpleNamespace(
                facility_id=f.facility_id,
                expected_capacity=f.expected_capacity,
                required_service_places=f.required_service_places,
            )
            for f in data.facilities
        ],
        snapshots=[f.snapshot for f in data.facilities],
    )
    kernel = _evaluate_outcome(problem)
    too_early = data.captured_at < data.expected_at
    facilities = []
    by_id = {f.facility_id: f for f in data.facilities}
    for row in kernel.rows:
        source = by_id[row.facility_id]
        raw = {r.resource_id: r for r in source.snapshot.resources}
        evidence = []
        for entry in row.evidence:
            status = (
                "missing"
                if "missing_required_observation" in entry.reason_codes
                or "missing_receipt_timestamp" in entry.reason_codes
                else "outside_window"
                if any(
                    reason in entry.reason_codes
                    for reason in (
                        "observation_before_followup_window",
                        "observation_after_capture",
                        "receipt_after_capture",
                        "receipt_before_observation",
                    )
                )
                else "stale"
                if entry.data_status == "stale"
                else "fresh"
            )
            evidence.append(
                ResourceEvidence(
                    resource_id=entry.resource_id,
                    observation_id=entry.observation_id,
                    available_quantity=entry.available_quantity,
                    observed_at=entry.observed_at,
                    data_status=raw[entry.resource_id].data_status
                    if entry.resource_id in raw
                    else "unknown",
                    evidence_status=status,
                )
            )
        is_unavailable = (
            row.capacity_result is not None and row.capacity_result.status == "unavailable"
        )
        fresh = all(e.evidence_status == "fresh" for e in evidence)
        observed = row.capacity_result if fresh or is_unavailable else None
        reasons = []
        if too_early:
            classification = "too_early"
            reasons.append("Review predates the expected date; no target achievement assessment.")
        elif not fresh and not is_unavailable:
            classification = "insufficient_evidence"
            reasons.extend(
                f"{e.resource_id}: {e.evidence_status} evidence"
                for e in evidence
                if e.evidence_status != "fresh"
            )
        elif row.status in ("at_or_above_expected", "below_expected"):
            classification = row.status
        else:
            classification = "not_comparable"
            reasons.append(
                "Reported service status is limited; modeled capacity is not quantified."
                if observed is not None and observed.service_status == "limited"
                else "The reported service cannot be compared with the frozen expectation."
            )
        comparable = classification in ("at_or_above_expected", "below_expected")
        facilities.append(
            FacilityOutcome(
                facility_id=row.facility_id,
                classification=classification,
                expected_capacity=row.expected_capacity,
                observed_capacity=row.observed_capacity if comparable else None,
                capacity_difference=row.capacity_difference if comparable else None,
                observed=observed,
                evidence=evidence,
                reasons=reasons,
                unmet_against_planned_demand=row.observed_unmet_against_planned_demand
                if comparable
                else None,
            )
        )
    comparable_ids = [f.facility_id for f in facilities if f.observed_capacity is not None]
    return OutcomeEvaluationResult(
        engine_version=ENGINE_VERSION,
        timing="too_early" if too_early else "on_or_after_expected",
        captured_offset_minutes=int(kernel.seconds_from_expected_at // 60),
        facilities=facilities,
        coverage=OutcomeCoverage(
            comparable_facility_ids=comparable_ids,
            not_comparable_facility_ids=[
                f.facility_id for f in facilities if f.facility_id not in comparable_ids
            ],
            excluded_facilities=data.excluded_facilities,
        ),
        reasons=["Reported completion is not evidence of capacity; compare fresh reports."]
        if any(f.classification == "insufficient_evidence" for f in facilities)
        else [],
    )
