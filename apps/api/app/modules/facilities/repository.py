"""Database access for facilities. Other modules should call the service instead."""

from datetime import datetime

from sqlalchemy import Row, func, select
from sqlalchemy.orm import Session, aliased

from app.modules.facilities.models import (
    Facility,
    FacilityResource,
    FacilityService,
    ResourceDefinition,
    ResourceObservation,
    Service,
)


def _with_last_reported_at():
    last_reported = (
        select(func.max(ResourceObservation.recorded_at))
        .where(ResourceObservation.facility_id == Facility.facility_id)
        .correlate(Facility)
        .scalar_subquery()
    )
    return select(Facility, last_reported.label("last_reported_at"))


def list_facilities(db: Session) -> list[Row[tuple[Facility, datetime | None]]]:
    return list(db.execute(_with_last_reported_at().order_by(Facility.facility_id)))


def get_facility(db: Session, facility_id: str) -> Row[tuple[Facility, datetime | None]] | None:
    stmt = _with_last_reported_at().where(Facility.facility_id == facility_id)
    return db.execute(stmt).one_or_none()


def facility_exists(db: Session, facility_id: str) -> bool:
    return db.get(Facility, facility_id) is not None


def list_services(db: Session, facility_id: str) -> list[Row[tuple[FacilityService, Service]]]:
    stmt = (
        select(FacilityService, Service)
        .join(Service, Service.service_id == FacilityService.service_id)
        .where(FacilityService.facility_id == facility_id)
        .order_by(FacilityService.service_id)
    )
    return list(db.execute(stmt))


def list_offered_services(db: Session) -> list[Service]:
    """Catalog services offered by at least one facility."""
    offered = select(FacilityService.service_id).distinct()
    stmt = select(Service).where(Service.service_id.in_(offered)).order_by(Service.service_id)
    return list(db.scalars(stmt))


def get_service(db: Session, service_id: str) -> Service | None:
    return db.get(Service, service_id)


def list_facility_ids_offering(db: Session, service_id: str) -> list[str]:
    stmt = (
        select(FacilityService.facility_id)
        .where(FacilityService.service_id == service_id)
        .order_by(FacilityService.facility_id)
    )
    return list(db.scalars(stmt))


def list_resource_definitions(db: Session) -> list[ResourceDefinition]:
    return list(db.scalars(select(ResourceDefinition).order_by(ResourceDefinition.resource_id)))


def list_applicable_resources(db: Session, facility_id: str) -> list[ResourceDefinition]:
    stmt = (
        select(ResourceDefinition)
        .join(FacilityResource, FacilityResource.resource_id == ResourceDefinition.resource_id)
        .where(FacilityResource.facility_id == facility_id)
        .order_by(ResourceDefinition.resource_id)
    )
    return list(db.scalars(stmt))


def get_applicable_resource(
    db: Session, facility_id: str, resource_id: str
) -> ResourceDefinition | None:
    stmt = (
        select(ResourceDefinition)
        .join(FacilityResource, FacilityResource.resource_id == ResourceDefinition.resource_id)
        .where(
            FacilityResource.facility_id == facility_id,
            FacilityResource.resource_id == resource_id,
        )
    )
    return db.scalars(stmt).one_or_none()


def latest_observations(db: Session, facility_id: str) -> dict[str, ResourceObservation]:
    """Latest observation per resource by observed_at, then recorded_at, then ID.

    A late upload of an older reading is kept as history but never replaces a
    reading that was observed more recently.
    """
    obs = ResourceObservation
    ranked = (
        select(
            obs,
            func.row_number()
            .over(
                partition_by=obs.resource_id,
                order_by=(
                    obs.observed_at.desc(),
                    obs.recorded_at.desc(),
                    obs.observation_id.desc(),
                ),
            )
            .label("row_rank"),
        )
        .where(obs.facility_id == facility_id)
        .subquery()
    )
    latest = aliased(ResourceObservation, ranked)
    rows = db.scalars(select(latest).where(ranked.c.row_rank == 1))
    return {row.resource_id: row for row in rows}


def add_observation(db: Session, observation: ResourceObservation) -> ResourceObservation:
    db.add(observation)
    db.flush()
    return observation
