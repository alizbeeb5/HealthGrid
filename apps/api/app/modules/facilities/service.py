"""Facility snapshot and observation use cases."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.modules.facilities import repository
from app.modules.facilities.errors import FacilityNotFound, ObservationRejected
from app.modules.facilities.models import ResourceObservation
from app.modules.facilities.schemas import (
    DataStatus,
    Facility,
    FacilityListResponse,
    FacilityService,
    FacilitySnapshotResponse,
    FieldError,
    ObservationCreate,
    ObservationResponse,
    ResourceDefinition,
    ResourceSnapshot,
)
from app.modules.ingestion.validation import validate_observation

# Demo reporting policy from the Feature 1 contract, not a clinical interval.
STALE_AFTER_HOURS = 24


def data_status(observed_at: datetime | None, as_of: datetime) -> DataStatus:
    if observed_at is None:
        return DataStatus.UNKNOWN
    if as_of - observed_at > timedelta(hours=STALE_AFTER_HOURS):
        return DataStatus.STALE
    return DataStatus.CURRENT


def _facility(row) -> Facility:
    facility, last_reported_at = row
    return Facility(
        facility_id=facility.facility_id,
        name=facility.name,
        latitude=facility.latitude,
        longitude=facility.longitude,
        last_reported_at=last_reported_at,
    )


def _definition(resource) -> ResourceDefinition:
    return ResourceDefinition(
        resource_id=resource.resource_id,
        name=resource.name,
        category=resource.category,
        unit=resource.unit,
        allows_fractional=resource.allows_fractional,
    )


def list_facilities(db: Session) -> FacilityListResponse:
    return FacilityListResponse(items=[_facility(row) for row in repository.list_facilities(db)])


def get_snapshot(db: Session, facility_id: str, now: datetime) -> FacilitySnapshotResponse:
    row = repository.get_facility(db, facility_id)
    if row is None:
        raise FacilityNotFound(facility_id)

    latest = repository.latest_observations(db, facility_id)
    resources = []
    for resource in repository.list_applicable_resources(db, facility_id):
        observation = latest.get(resource.resource_id)
        observed_at = observation.observed_at if observation else None
        resources.append(
            ResourceSnapshot(
                **_definition(resource).model_dump(),
                observation_id=observation.observation_id if observation else None,
                available_quantity=observation.available_quantity if observation else None,
                observed_at=observed_at,
                recorded_at=observation.recorded_at if observation else None,
                data_status=data_status(observed_at, now),
            )
        )

    services = [
        FacilityService(
            facility_id=facility_service.facility_id,
            service_id=facility_service.service_id,
            name=service.name,
            status=facility_service.status,
        )
        for facility_service, service in repository.list_services(db, facility_id)
    ]
    return FacilitySnapshotResponse(
        facility=_facility(row),
        services=services,
        resources=resources,
        as_of=now,
        stale_after_hours=STALE_AFTER_HOURS,
    )


def create_observation(
    db: Session, facility_id: str, payload: ObservationCreate, now: datetime
) -> ObservationResponse:
    if not repository.facility_exists(db, facility_id):
        raise FacilityNotFound(facility_id)

    resource = repository.get_applicable_resource(db, facility_id, payload.resource_id)
    if resource is None:
        message = f"Resource {payload.resource_id} is not tracked for facility {facility_id}."
        raise ObservationRejected([FieldError(field="resource_id", message=message)])

    errors = validate_observation(payload, _definition(resource), now)
    if errors:
        raise ObservationRejected(errors)

    observation = repository.add_observation(
        db,
        ResourceObservation(
            observation_id=f"OBS-{uuid.uuid4()}",
            facility_id=facility_id,
            resource_id=resource.resource_id,
            available_quantity=payload.available_quantity,
            unit=payload.unit,
            observed_at=payload.observed_at.astimezone(UTC),
            recorded_at=now,
        ),
    )
    db.commit()
    return ObservationResponse(
        resource_id=observation.resource_id,
        available_quantity=observation.available_quantity,
        unit=observation.unit,
        observed_at=observation.observed_at,
        observation_id=observation.observation_id,
        facility_id=observation.facility_id,
        recorded_at=observation.recorded_at,
    )
