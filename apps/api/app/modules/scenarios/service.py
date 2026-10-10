"""Incident drafts, confirmation with an immutable baseline, and saved simulation runs."""

import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.engines import scenarios as scenario_engine
from app.engines.capacity import calculate_service_capacity
from app.modules.capacity import service as capacity
from app.modules.facilities import service as facilities
from app.modules.facilities.errors import FacilityNotFound
from app.modules.facilities.schemas import FacilitySnapshotResponse, FieldError
from app.modules.scenarios import models, repository
from app.modules.scenarios.errors import ScenarioError
from app.modules.scenarios.schemas import (
    SCHEMA_VERSION,
    EffectiveFacility,
    EffectiveScenario,
    IncidentBaseline,
    IncidentConfirmRequest,
    IncidentDraftInput,
    IncidentListResponse,
    IncidentRevision,
    RevisionStatus,
    SimulationRun,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


# Validation against the facility/service/resource catalog.


def validate_incident(
    db: Session, payload: IncidentDraftInput, now: datetime, *, confirm: bool, prefix: str = ""
) -> list[FieldError]:
    """Cross-field and catalog rules; applied to every supplied value, even in drafts."""
    errors: list[FieldError] = []

    def error(path: str, message: str) -> None:
        errors.append(FieldError(field=f"{prefix}{path}", message=message))

    if payload.starts_at and payload.expected_ends_at and (
        payload.expected_ends_at <= payload.starts_at
    ):
        error("expected_ends_at", "expected_ends_at must be after starts_at.")

    service_id = payload.service_id
    offering: set[str] = set()
    if service_id is not None:
        if facilities.get_service_name(db, service_id) is None:
            error("service_id", f"Unknown service {service_id}.")
        offering = set(facilities.list_facility_ids_offering(db, service_id))
    has_overrides = bool(payload.service_overrides or payload.resource_overrides)
    if has_overrides and service_id is None:
        error("service_id", "Select the service before adding overrides.")
    if confirm and not has_overrides:
        error("service_overrides", "Add at least one service or resource override.")

    snapshots: dict[str, FacilitySnapshotResponse | None] = {}

    def snapshot(facility_id: str) -> FacilitySnapshotResponse | None:
        if facility_id not in snapshots:
            try:
                snapshots[facility_id] = facilities.get_snapshot(db, facility_id, now)
            except FacilityNotFound:
                snapshots[facility_id] = None
        return snapshots[facility_id]

    affected = set(payload.affected_facility_ids)
    for i, facility_id in enumerate(payload.affected_facility_ids):
        if snapshot(facility_id) is None:
            error(f"affected_facility_ids.{i}", f"Unknown facility {facility_id}.")
        elif service_id is not None and facility_id not in offering:
            error(f"affected_facility_ids.{i}", f"{facility_id} does not offer {service_id}.")

    def check_facility(path: str, facility_id: str) -> bool:
        if facility_id not in affected:
            error(f"{path}.facility_id", f"{facility_id} is not in affected_facility_ids.")
            return False
        return snapshot(facility_id) is not None

    seen: set[tuple] = set()
    for i, override in enumerate(payload.service_overrides):
        path = f"service_overrides.{i}"
        if (override.facility_id, override.service_id) in seen:
            error(path, "Only one override per facility and service.")
        seen.add((override.facility_id, override.service_id))
        if service_id is not None and override.service_id != service_id:
            error(f"{path}.service_id", f"Overrides must use the selected service {service_id}.")
        check_facility(path, override.facility_id)

    for i, override in enumerate(payload.resource_overrides):
        path = f"resource_overrides.{i}"
        if (override.facility_id, override.resource_id) in seen:
            error(path, "Only one override per facility and resource.")
        seen.add((override.facility_id, override.resource_id))
        if not check_facility(path, override.facility_id):
            continue
        resource = next(
            (r for r in snapshot(override.facility_id).resources
             if r.resource_id == override.resource_id),
            None,
        )
        if resource is None:
            error(f"{path}.resource_id",
                  f"{override.resource_id} is not tracked for {override.facility_id}.")
            continue
        if override.unit != resource.unit:
            error(f"{path}.unit", f"Expected {resource.unit.value} for {resource.resource_id}.")
        if not resource.allows_fractional and not override.available_quantity.is_integer():
            error(f"{path}.available_quantity", f"Use a whole number for {resource.resource_id}.")
    return errors


# Revisions.


def _revision(row: models.IncidentRevision) -> IncidentRevision:
    return IncidentRevision(
        incident_id=row.incident_id,
        revision_id=row.revision_id,
        parent_revision_id=row.parent_revision_id,
        status=row.status,
        input=IncidentDraftInput.model_validate(row.input),
        created_at=row.created_at,
        confirmed_at=row.confirmed_at,
        confirmed_by=row.confirmed_by,
        baseline_id=row.baseline_id,
    )


def create_draft(db: Session, payload: IncidentDraftInput, now: datetime) -> IncidentRevision:
    errors = validate_incident(db, payload, now, confirm=False)
    if errors:
        raise ScenarioError("invalid_request", errors)
    incident = models.Incident(incident_id=_new_id("INC"), created_at=now)
    draft = models.IncidentRevision(
        revision_id=_new_id("REV"),
        incident_id=incident.incident_id,
        parent_revision_id=None,
        status=RevisionStatus.DRAFT,
        input=payload.model_dump(mode="json"),
        schema_version=SCHEMA_VERSION,
        created_at=now,
    )
    repository.add(db, incident, draft)
    db.commit()
    return _revision(draft)


def list_incidents(db: Session) -> IncidentListResponse:
    """Latest revision per incident, newest first, incident_id tie-break."""
    latest: dict[str, models.IncidentRevision] = {}
    for row in repository.list_revisions(db):  # ordered by created_at within an incident
        latest[row.incident_id] = row
    rows = sorted(latest.values(), key=lambda r: r.incident_id)
    rows.sort(key=lambda r: r.created_at, reverse=True)
    return IncidentListResponse(items=[_revision(row) for row in rows])


def _require_revision(db: Session, incident_id: str, revision_id: str) -> models.IncidentRevision:
    if repository.get_incident(db, incident_id) is None:
        raise ScenarioError("incident_not_found")
    row = repository.get_revision(db, revision_id)
    if row is None or row.incident_id != incident_id:
        raise ScenarioError("revision_not_found")
    return row


def get_revision(db: Session, incident_id: str, revision_id: str) -> IncidentRevision:
    return _revision(_require_revision(db, incident_id, revision_id))


def capture_baseline(db: Session, service_id: str, now: datetime) -> IncidentBaseline:
    """One shared timestamp; snapshots through facility services; full profile content."""
    profiles = capacity.get_profiles(db)
    return IncidentBaseline(
        baseline_id=_new_id("BASE"),
        captured_at=now,
        service_id=service_id,
        facility_snapshots=[
            facilities.get_snapshot(db, facility_id, now)
            for facility_id in facilities.list_facility_ids_offering(db, service_id)
        ],
        requirement_profiles=[profiles[key] for key in sorted(profiles)],
        schema_version=SCHEMA_VERSION,
    )


def confirm(
    db: Session, incident_id: str, request: IncidentConfirmRequest, now: datetime
) -> IncidentRevision:
    draft = _require_revision(db, incident_id, request.draft_revision_id)
    existing = repository.get_confirmed_revision(db, incident_id)
    if existing is not None:
        raise ScenarioError("revision_conflict", existing_revision_id=existing.revision_id)
    if draft.status != RevisionStatus.DRAFT:
        raise ScenarioError("revision_conflict", existing_revision_id=draft.revision_id)
    errors = validate_incident(db, request.input, now, confirm=True, prefix="input.")
    if errors:
        raise ScenarioError("invalid_request", errors)

    baseline = capture_baseline(db, request.input.service_id, now)
    confirmed = models.IncidentRevision(
        revision_id=_new_id("REV"),
        incident_id=incident_id,
        parent_revision_id=draft.revision_id,
        status=RevisionStatus.CONFIRMED,
        input=request.input.model_dump(mode="json"),
        schema_version=SCHEMA_VERSION,
        created_at=now,
        confirmed_at=now,
        confirmed_by=request.confirmed_by,
        baseline_id=baseline.baseline_id,
    )
    try:
        repository.add(
            db,
            models.IncidentBaseline(
                baseline_id=baseline.baseline_id,
                service_id=baseline.service_id,
                captured_at=baseline.captured_at,
                schema_version=SCHEMA_VERSION,
                payload=baseline.model_dump(mode="json"),
            ),
            confirmed,
        )
        db.commit()  # baseline and revision together, or neither
    except IntegrityError:
        db.rollback()  # a concurrent confirmation won the uniqueness constraint
        winner = repository.get_confirmed_revision(db, incident_id)
        raise ScenarioError(
            "revision_conflict", existing_revision_id=winner.revision_id if winner else None
        ) from None
    except Exception:
        db.rollback()
        raise
    return _revision(confirmed)


# Simulation runs.


def _run(row: models.SimulationRun) -> SimulationRun:
    return SimulationRun(
        run_id=row.run_id,
        created_at=row.created_at,
        engine_version=row.engine_version,
        schema_version=row.schema_version,
        impact=row.impact,
    )


def simulate(
    db: Session, incident_id: str, revision_id: str, now: datetime
) -> tuple[SimulationRun, bool]:
    """Return (run, created). Computed from the saved baseline, never live reports."""
    revision = _require_revision(db, incident_id, revision_id)
    if revision.status != RevisionStatus.CONFIRMED:
        raise ScenarioError("incident_not_confirmed")
    engine_version = scenario_engine.ENGINE_VERSION
    existing = repository.find_run(db, revision_id, engine_version)
    if existing is not None:
        return _run(existing), False

    baseline = IncidentBaseline.model_validate(
        repository.get_baseline(db, revision.baseline_id).payload
    )
    impact = scenario_engine.simulate_incident(baseline, _revision(revision))
    run = SimulationRun(
        run_id=_new_id("RUN"),
        created_at=now,
        engine_version=engine_version,
        schema_version=SCHEMA_VERSION,
        impact=impact,
    )
    try:
        repository.add(
            db,
            models.SimulationRun(
                run_id=run.run_id,
                revision_id=revision_id,
                engine_version=engine_version,
                schema_version=SCHEMA_VERSION,
                created_at=now,
                impact=impact.model_dump(mode="json"),
            ),
        )
        db.commit()
    except IntegrityError:
        db.rollback()  # a concurrent request saved the run first; return that one
        return _run(repository.find_run(db, revision_id, engine_version)), False
    return run, True


def get_effective_scenario(db: Session, run_id: str) -> EffectiveScenario:
    """Public contract for allocation: the saved run's frozen baseline with the confirmed
    overrides applied, rebuilt by the same overlay that produced the run."""
    row = repository.get_run(db, run_id)
    if row is None:
        raise ScenarioError("run_not_found")
    run = _run(row)
    revision = _revision(repository.get_revision(db, row.revision_id))
    baseline = IncidentBaseline.model_validate(
        repository.get_baseline(db, revision.baseline_id).payload
    )
    selected = revision.input.service_id
    profile = next((p for p in baseline.requirement_profiles if p.service_id == selected), None)
    required = {r.resource_id for r in profile.requirements} if profile else set()
    saved = {r.facility.facility_id: r for r in run.impact.rows}

    facilities_out = []
    for snapshot in baseline.facility_snapshots:
        facility_id = snapshot.facility.facility_id
        impact_row = saved[facility_id]
        effective = snapshot
        if impact_row.affected:
            effective, _ = scenario_engine.apply_incident_overrides(
                snapshot, revision, selected, required
            )
        service = next(s for s in effective.services if s.service_id == selected)
        if calculate_service_capacity(effective, service, profile) != impact_row.scenario_capacity:
            raise RuntimeError(f"Saved run {run_id} does not match its frozen inputs.")
        facilities_out.append(EffectiveFacility(
            snapshot=effective,
            affected=impact_row.affected,
            applied_overrides=impact_row.applied_overrides,
            scenario_capacity=impact_row.scenario_capacity,
        ))
    return EffectiveScenario(
        run_id=run.run_id,
        incident_id=revision.incident_id,
        revision_id=revision.revision_id,
        baseline_id=baseline.baseline_id,
        baseline_captured_at=baseline.captured_at,
        planning_starts_at=revision.input.starts_at,
        service_id=selected,
        requirement_profiles=baseline.requirement_profiles,
        facilities=facilities_out,
    )


def get_run(db: Session, run_id: str) -> SimulationRun:
    row = repository.get_run(db, run_id)
    if row is None:
        raise ScenarioError("run_not_found")
    return _run(row)
