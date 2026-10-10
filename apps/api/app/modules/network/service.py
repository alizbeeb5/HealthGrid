"""Network overview: one clock, one profile load, one snapshot per facility."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.capacity import service as capacity
from app.modules.facilities import service as facilities
from app.modules.network.schemas import (
    NetworkFacilityResult,
    NetworkOverviewResponse,
    NetworkService,
    NetworkServiceListResponse,
)


def list_services(db: Session) -> NetworkServiceListResponse:
    return NetworkServiceListResponse(
        items=[
            NetworkService(service_id=service_id, name=name)
            for service_id, name in facilities.list_offered_services(db)
        ]
    )


def get_overview(db: Session, service_id: str, now: datetime) -> NetworkOverviewResponse:
    """Any failure fails the whole request; rows are never dropped or turned into 0."""
    service_name = facilities.get_service_name(db, service_id)
    rows: list[NetworkFacilityResult] = []
    if service_name is not None:
        profiles = capacity.get_profiles(db)
        for facility_id in facilities.list_facility_ids_offering(db, service_id):
            snapshot = facilities.get_snapshot(db, facility_id, now)
            offered = [s for s in snapshot.services if s.service_id == service_id]
            if len(offered) != 1:
                raise RuntimeError(f"Facility {facility_id} no longer offers {service_id}.")
            rows.append(
                NetworkFacilityResult(
                    facility=snapshot.facility,
                    capacity=capacity.calculate_service(snapshot, offered[0], profiles),
                )
            )

    # Revalidate so results that break contract invariants fail visibly.
    return NetworkOverviewResponse.model_validate(
        {
            "service_id": service_id,
            "service_name": service_name,
            "as_of": now,
            "stale_after_hours": facilities.STALE_AFTER_HOURS,
            "calculation_scope": "single_service",
            "capacity_unit": "simultaneous_service_place",
            "facilities": [row.model_dump() for row in rows],
        }
    )
