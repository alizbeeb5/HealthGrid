"""Decisions: frozen source expectations, legal transitions with version checks and
idempotent retries, and captured outcome reviews through the outcome engine.

Approving or completing never writes observations: hospital resources change only
through Feature 1 reports.
"""

import hashlib
import importlib
import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.engines import capacity as capacity_engine
from app.modules.allocation import service as allocation
from app.modules.allocation.errors import AllocationError
from app.modules.decisions import models, repository, transitions
from app.modules.decisions.errors import DecisionError, invalid
from app.modules.decisions.schemas import (
    SCHEMA_VERSION,
    ActionItem,
    ActionStatus,
    DecisionCreateRequest,
    DecisionEvent,
    DecisionEventRequest,
    DecisionListResponse,
    DecisionRecord,
    DecisionStatus,
    EvidenceStatus,
    ExpectedFacility,
    OutcomeEvaluationInput,
    OutcomeEvaluationResult,
    OutcomeFacilityInput,
    OutcomeReview,
    OutcomeReviewRequest,
    SourceExpectation,
    SourceType,
)
from app.modules.facilities import service as facilities
from app.modules.investments import service as investments
from app.modules.investments.errors import InvestmentError
from app.modules.scenarios import service as scenarios

REVIEWABLE = {DecisionStatus.APPROVED, DecisionStatus.IN_PROGRESS, DecisionStatus.COMPLETED}


class OutcomeEngineError(RuntimeError):
    """Engine missing, or its evaluation failed the independent check. HTTP 500."""


def outcome_evaluator():
    """engines.outcomes.evaluate_outcome (owned by the data/evaluation teammate), resolved
    at request time so the API still starts before that engine is merged."""
    try:
        module = importlib.import_module("app.engines.outcomes")
    except ModuleNotFoundError:
        return None
    return getattr(module, "evaluate_outcome", None)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _hash(model) -> str:
    canonical = json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# Source expectations and actions (frozen at creation).


def _expectation_and_actions(db: Session, source_type: SourceType, run_id: str
                             ) -> tuple[SourceExpectation, list[ActionItem], bool]:
    """Return the frozen expectation, generated actions and whether the source assumes
    transfers (which then require a prerequisite allocation decision)."""
    try:
        run = (allocation.get_run(db, run_id) if source_type == SourceType.ALLOCATION
               else investments.get_run(db, run_id))
    except (AllocationError, InvestmentError):
        raise DecisionError("source_run_not_found", f"Source run {run_id} was not found.") \
            from None
    if run.proposed_summary is None or not run.validation_passed:
        raise invalid("source_run_id", f"{run_id} has no validated proposal "
                      f"({run.plan_outcome}); it cannot become an executable decision.")
    allocation_id = run_id if source_type == SourceType.ALLOCATION else run.allocation_run_id
    state = allocation.get_post_allocation_state(db, allocation_id)
    scenario = scenarios.get_effective_scenario(db, state.simulation_run_id)

    actions: list[ActionItem] = []
    pending = dict(status=ActionStatus.PENDING, reported_started_at=None,
                   reported_completed_at=None, actual_cost_minor_units=None, evidence_note=None,
                   blocker_note=None, corrections=[])
    if source_type == SourceType.ALLOCATION:
        expected_at = state.incident_starts_at + timedelta(minutes=state.allocation_horizon_minutes)
        for t in run.transfers:
            actions.append(ActionItem(
                action_id=f"ACT-{t.route_id}", action_type="transfer", reference_id=t.route_id,
                description=(f"Transfer {t.quantity} {t.unit.value} of {t.resource_id} from "
                             f"{t.from_facility_id} to {t.to_facility_id} ({t.route_id})."),
                facility_ids=sorted({t.from_facility_id, t.to_facility_id}),
                requires_action_ids=[], proposed_cost_minor_units=t.cost_minor_units,
                proposed_ready_at=state.incident_starts_at
                + timedelta(minutes=t.lead_time_minutes), **pending))
        costs = (run.total_cost_minor_units, None, None)
        assumes_transfers = False
    else:
        expected_at = run.input.evaluation_at
        for p in run.selected_projects:
            actions.append(ActionItem(
                action_id=f"ACT-{p.candidate_id}", action_type="project",
                reference_id=p.candidate_id,
                description=next(c.name for c in run.input.candidates
                                 if c.candidate_id == p.candidate_id),
                facility_ids=[p.facility_id],
                requires_action_ids=[f"ACT-{r}" for r in p.requires_candidate_ids],
                proposed_cost_minor_units=p.total_cost_minor_units,
                proposed_ready_at=p.ready_at, **pending))
        costs = (run.total_cost_minor_units, run.total_capital_cost_minor_units,
                 run.total_operating_cost_minor_units)
        assumes_transfers = bool(run.assumed_transfers)

    before = {r.facility_id: r for r in run.baseline_summary.rows}
    expectation = SourceExpectation(
        source_type=source_type, source_run_id=run_id, source_engine_version=run.engine_version,
        source_created_at=run.created_at, plan_outcome=run.plan_outcome,
        incident_id=run.incident_id, revision_id=run.revision_id, baseline_id=run.baseline_id,
        baseline_captured_at=scenario.baseline_captured_at, service_id=state.service_id,
        capacity_unit="simultaneous_service_place", requirement=state.requirement,
        expected_at=expected_at,
        facilities=[ExpectedFacility(
            facility_id=row.facility_id, required_service_places=row.required_service_places,
            capacity_before=before[row.facility_id].estimated_capacity,
            expected_capacity=row.estimated_capacity) for row in run.proposed_summary.rows],
        excluded_facilities=(run.coverage.excluded if source_type == SourceType.ALLOCATION
                             else run.coverage.excluded_facilities),
        expected_unmet_service_places=run.proposed_summary.unmet_service_places,
        proposed_cost_minor_units=costs[0], proposed_capital_cost_minor_units=costs[1],
        proposed_operating_cost_minor_units=costs[2], currency="USD")
    return expectation, actions, assumes_transfers


# Records.


def _record(row: models.Decision, db: Session) -> DecisionRecord:
    events = [DecisionEvent.model_validate(e.event) for e in repository.events(db, row.decision_id)]
    return DecisionRecord.model_validate({**row.state, "events": events})


def _state(record: DecisionRecord) -> dict:
    return record.model_dump(mode="json", exclude={"events"})


def _require(db: Session, decision_id: str) -> models.Decision:
    row = repository.get(db, decision_id)
    if row is None:
        raise DecisionError("decision_not_found", f"Decision {decision_id} was not found.")
    return row


def create(db: Session, request: DecisionCreateRequest, now: datetime) -> DecisionRecord:
    expectation, actions, assumes_transfers = _expectation_and_actions(
        db, request.source_type, request.source_run_id)

    if request.source_type == SourceType.ALLOCATION and request.prerequisite_decision_id:
        raise invalid("prerequisite_decision_id", "Allocation decisions have no prerequisite.")
    if request.source_type == SourceType.INVESTMENT:
        run = investments.get_run(db, request.source_run_id)
        if assumes_transfers and request.prerequisite_decision_id is None:
            raise invalid("prerequisite_decision_id", "This investment assumes transfers from "
                          f"{run.allocation_run_id}; link the decision tracking them.")
        if not assumes_transfers and request.prerequisite_decision_id is not None:
            raise invalid("prerequisite_decision_id",
                          "The source assumes no transfers; no prerequisite is needed.")
        if request.prerequisite_decision_id:
            prerequisite = repository.get(db, request.prerequisite_decision_id)
            if prerequisite is None:
                raise DecisionError("decision_not_found", "Prerequisite decision "
                                    f"{request.prerequisite_decision_id} was not found.")
            if (prerequisite.source_type, prerequisite.source_run_id) != (
                SourceType.ALLOCATION.value, run.allocation_run_id
            ) or prerequisite.status in ("rejected", "cancelled"):
                raise invalid("prerequisite_decision_id", "The prerequisite must be an active "
                              f"decision for allocation run {run.allocation_run_id}.")
    if request.supersedes_decision_id:
        superseded = _require(db, request.supersedes_decision_id)
        if superseded.status not in ("rejected", "cancelled"):
            raise DecisionError("invalid_transition", "Only a rejected or cancelled decision "
                                "can be superseded; its timeline is preserved.")

    existing = repository.active_for_source(db, request.source_type, request.source_run_id)
    if existing is not None:
        raise _duplicate(existing.decision_id)

    decision_id = _new_id("DEC")
    record = DecisionRecord(
        decision_id=decision_id, source_type=request.source_type,
        source_run_id=request.source_run_id, incident_id=expectation.incident_id,
        revision_id=expectation.revision_id, baseline_id=expectation.baseline_id,
        title=request.title, owner_name=request.owner_name, rationale=request.rationale,
        target_completion_at=request.target_completion_at, status=DecisionStatus.DRAFT,
        version=1, identity_mode="demo_self_reported", created_at=now, updated_at=now,
        prerequisite_decision_id=request.prerequisite_decision_id,
        supersedes_decision_id=request.supersedes_decision_id, expectation=expectation,
        actions=actions, events=[])
    event = DecisionEvent(
        event_id=_new_id("EVT"), sequence=1, event_type="create", request_id=None,
        actor_name=request.actor_name, identity_mode="demo_self_reported", note=None,
        occurred_at=None, recorded_at=now, payload=None, status_after=DecisionStatus.DRAFT,
        version_after=1)
    try:
        repository.add(db, models.Decision(
            decision_id=decision_id, source_type=request.source_type.value,
            source_run_id=request.source_run_id, status=record.status.value,
            created_at=now, updated_at=now, state=_state(record)))
        repository.add(db, models.DecisionEvent(
            event_id=event.event_id, decision_id=decision_id, sequence=1, request_id=None,
            request_hash=None, event_type="create", recorded_at=now,
            event=event.model_dump(mode="json"), response=None))
        db.commit()
    except IntegrityError:
        db.rollback()  # a concurrent request claimed the same source first
        winner = repository.active_for_source(db, request.source_type, request.source_run_id)
        raise _duplicate(winner.decision_id if winner else None) from None
    return record.model_copy(update={"events": [event]})


def _duplicate(existing_id: str | None) -> DecisionError:
    return DecisionError("duplicate_source_decision", "This source run already has an active "
                         "or completed decision.", existing_decision_id=existing_id)


def list_decisions(db: Session, status: DecisionStatus | None) -> DecisionListResponse:
    rows = repository.list_decisions(db, status.value if status else None)
    return DecisionListResponse(items=[_record(row, db) for row in rows])


def get(db: Session, decision_id: str) -> DecisionRecord:
    return _record(_require(db, decision_id), db)


def apply_event(db: Session, decision_id: str, command: DecisionEventRequest, now: datetime
                ) -> tuple[DecisionRecord, bool]:
    """Return (record, applied). A retried request returns its saved result unapplied."""
    row = _require(db, decision_id)
    digest = _hash(command)
    previous = repository.event_for_request(db, decision_id, command.request_id)
    if previous is not None:
        if previous.request_hash != digest:
            raise DecisionError("idempotency_conflict", "This request_id was already used "
                                "with a different request.")
        return DecisionRecord.model_validate(previous.response), False
    if command.expected_version != row.version:
        raise DecisionError("version_conflict", "The decision changed since you loaded it; "
                            "reload and retry.", current_version=row.version)

    record = _record(row, db)
    prerequisite_status = None
    if record.prerequisite_decision_id:
        prerequisite_status = DecisionStatus(
            repository.get(db, record.prerequisite_decision_id).status)
    updated = transitions.apply(record, command, now, prerequisite_status)
    version = row.version + 1
    occurred_at = getattr(command.payload, "occurred_at", None)
    event = DecisionEvent(
        event_id=_new_id("EVT"), sequence=len(record.events) + 1,
        event_type=command.event_type, request_id=command.request_id,
        actor_name=command.actor_name, identity_mode="demo_self_reported", note=command.note,
        occurred_at=occurred_at, recorded_at=now, payload=command.payload,
        status_after=updated.status, version_after=version)
    updated = updated.model_copy(update={"version": version,
                                         "events": [*record.events, event]})
    try:
        row.status = updated.status.value
        row.updated_at = now
        row.state = _state(updated)  # version_id_col increments and checks the version
        db.flush()
        repository.add(db, models.DecisionEvent(
            event_id=event.event_id, decision_id=decision_id, sequence=event.sequence,
            request_id=command.request_id, request_hash=digest, event_type=command.event_type,
            recorded_at=now, event=event.model_dump(mode="json"),
            response=updated.model_dump(mode="json")))
        db.commit()
    except (StaleDataError, IntegrityError):
        db.rollback()  # a concurrent change won; never apply on top of it
        retried = repository.event_for_request(db, decision_id, command.request_id)
        if retried is not None and retried.request_hash == digest:
            return DecisionRecord.model_validate(retried.response), False
        current = repository.get(db, decision_id)
        raise DecisionError("version_conflict", "The decision changed concurrently; reload "
                            "and retry.", current_version=current.version) from None
    return updated, True


# Outcome reviews.


def evidence_status(snapshot_resource, window_start: datetime, captured_at: datetime
                    ) -> EvidenceStatus:
    """Freshness of one reported resource for a follow-up review."""
    observed_at = snapshot_resource.observed_at
    if snapshot_resource.observation_id is None or observed_at is None:
        return EvidenceStatus.MISSING
    if observed_at < window_start or observed_at > captured_at:
        return EvidenceStatus.OUTSIDE_WINDOW
    if snapshot_resource.data_status != "current":
        return EvidenceStatus.STALE
    return EvidenceStatus.FRESH


def check_outcome(inputs: OutcomeEvaluationInput, result: OutcomeEvaluationResult
                  ) -> list[str]:
    """Independent check of the engine's evaluation. Empty means valid."""
    problems: list[str] = []
    expected = {f.facility_id: f for f in inputs.facilities}
    if [f.facility_id for f in result.facilities] != sorted(expected):
        return ["Outcome rows differ from the decision's expected facilities."]
    if result.coverage.excluded_facilities != inputs.excluded_facilities:
        problems.append("Excluded facilities differ from the source proposal.")
    too_early = inputs.captured_at < inputs.expected_at
    if (result.timing == "too_early") != too_early:
        problems.append("Timing classification is wrong.")
    offset = int((inputs.captured_at - inputs.expected_at).total_seconds() // 60)
    if result.captured_offset_minutes != offset:
        problems.append("captured_offset_minutes is wrong.")
    required = sorted(r.resource_id for r in inputs.requirement.requirements)
    for row in result.facilities:
        facility = expected[row.facility_id]
        if row.expected_capacity != facility.expected_capacity:
            problems.append(f"{row.facility_id} expected capacity differs from the frozen plan.")
        resources = {r.resource_id: r for r in facility.snapshot.resources}
        evidence = {e.resource_id: e for e in row.evidence}
        fresh = True
        for resource_id in required:
            resource, item = resources.get(resource_id), evidence.get(resource_id)
            if resource is None or item is None:
                problems.append(f"{row.facility_id} lacks evidence for {resource_id}.")
                fresh = False
                continue
            status = evidence_status(resource, inputs.observation_window_starts_at,
                                     inputs.captured_at)
            if (item.observation_id, item.available_quantity, item.observed_at,
                    item.data_status, item.evidence_status) != (
                    resource.observation_id, resource.available_quantity, resource.observed_at,
                    resource.data_status, status):
                problems.append(f"{row.facility_id} evidence for {resource_id} does not match "
                                "the captured report.")
            fresh = fresh and status == EvidenceStatus.FRESH
        if row.observed_capacity is not None:
            if too_early or not fresh:
                problems.append(f"{row.facility_id} is compared without fresh in-window "
                                "evidence.")
            service = next((s for s in facility.snapshot.services
                            if s.service_id == inputs.service_id), None)
            observed = (capacity_engine.calculate_service_capacity(
                facility.snapshot, service, inputs.requirement) if service else None)
            if observed is None or observed != row.observed or (
                    observed.estimated_capacity != row.observed_capacity):
                problems.append(f"{row.facility_id} observed capacity does not match the "
                                "capacity engine.")
            elif row.unmet_against_planned_demand != max(
                    0, facility.required_service_places - row.observed_capacity):
                problems.append(f"{row.facility_id} unmet demand is wrong.")
    return problems


def create_review(db: Session, decision_id: str, request: OutcomeReviewRequest, now: datetime
                  ) -> tuple[OutcomeReview, bool]:
    row = _require(db, decision_id)
    digest = _hash(request)
    previous = repository.review_for_request(db, decision_id, request.request_id)
    if previous is not None:
        if previous.request_hash != digest:
            raise DecisionError("idempotency_conflict", "This request_id was already used "
                                "with a different review request.")
        return OutcomeReview.model_validate(previous.payload), False
    record = _record(row, db)
    if record.status not in REVIEWABLE:
        raise DecisionError("invalid_transition", "Outcome reviews need an approved, "
                            f"in-progress or completed decision, not {record.status.value}.")
    expectation = record.expectation
    window = request.observation_window_starts_at
    if window < expectation.baseline_captured_at or window > now:
        raise invalid("observation_window_starts_at", "The window must start between the "
                      "source baseline capture and the review capture time.")

    snapshots = [facilities.get_snapshot(db, f.facility_id, now)
                 for f in expectation.facilities]
    inputs = OutcomeEvaluationInput(
        service_id=expectation.service_id, capacity_unit=expectation.capacity_unit,
        requirement=expectation.requirement, expected_at=expectation.expected_at,
        target_completion_at=record.target_completion_at, observation_window_starts_at=window,
        captured_at=now, stale_after_hours=facilities.STALE_AFTER_HOURS,
        decision_status=record.status,
        facilities=[OutcomeFacilityInput(
            facility_id=f.facility_id, required_service_places=f.required_service_places,
            capacity_before=f.capacity_before, expected_capacity=f.expected_capacity,
            snapshot=snapshot) for f, snapshot in zip(expectation.facilities, snapshots)],
        excluded_facilities=expectation.excluded_facilities)
    evaluate = outcome_evaluator()
    if evaluate is None:
        raise OutcomeEngineError("engines.outcomes.evaluate_outcome is missing.")
    result = OutcomeEvaluationResult.model_validate(evaluate(inputs).model_dump())
    problems = check_outcome(inputs, result)
    if problems:
        raise OutcomeEngineError("Outcome failed independent validation: " + "; ".join(problems))

    review = OutcomeReview(
        **result.model_dump(), review_id=_new_id("REVIEW"), decision_id=decision_id,
        source_type=record.source_type, source_run_id=record.source_run_id,
        request_id=request.request_id, actor_name=request.actor_name,
        identity_mode="demo_self_reported", note=request.note, captured_at=now,
        observation_window_starts_at=window, expected_at=expectation.expected_at,
        target_completion_at=record.target_completion_at, decision_status=record.status,
        decision_version=record.version, requirement=expectation.requirement,
        snapshots=snapshots, schema_version=SCHEMA_VERSION)
    try:
        repository.add(db, models.OutcomeReview(
            review_id=review.review_id, decision_id=decision_id, request_id=request.request_id,
            request_hash=digest, captured_at=now, engine_version=review.engine_version,
            payload=review.model_dump(mode="json")))
        db.commit()
    except IntegrityError:
        db.rollback()  # a concurrent retry with the same request_id saved first
        saved = repository.review_for_request(db, decision_id, request.request_id)
        if saved is not None and saved.request_hash == digest:
            return OutcomeReview.model_validate(saved.payload), False
        raise DecisionError("idempotency_conflict", "This request_id was already used "
                            "with a different review request.") from None
    return review, True


def get_review(db: Session, decision_id: str, review_id: str) -> OutcomeReview:
    _require(db, decision_id)
    row = repository.get_review(db, review_id)
    if row is None or row.decision_id != decision_id:
        raise DecisionError("review_not_found", f"Review {review_id} was not found.")
    return OutcomeReview.model_validate(row.payload)
