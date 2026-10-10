"""Facility snapshots and resource observations. Owner: backend/data."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.facilities import service
from app.modules.facilities.errors import FacilityRoute
from app.modules.facilities.schemas import (
    ErrorResponse,
    FacilityListResponse,
    FacilitySnapshotResponse,
    ObservationCreate,
    ObservationResponse,
)

router = APIRouter(prefix="/facilities", tags=["facilities"], route_class=FacilityRoute)

FacilityId = Path(min_length=1, max_length=64)
ERRORS = {
    404: {"model": ErrorResponse, "description": "Facility does not exist"},
    422: {"model": ErrorResponse, "description": "Invalid request or observation"},
}


def server_now() -> datetime:
    return datetime.now(UTC)


@router.get("", operation_id="list_facilities")
def list_facilities(db: Session = Depends(get_session)) -> FacilityListResponse:
    return service.list_facilities(db)


@router.get("/{facility_id}/snapshot", operation_id="get_facility_snapshot", responses=ERRORS)
def get_facility_snapshot(
    facility_id: str = FacilityId,
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
) -> FacilitySnapshotResponse:
    return service.get_snapshot(db, facility_id, now)


@router.post(
    "/{facility_id}/observations",
    status_code=201,
    operation_id="create_resource_observation",
    responses=ERRORS,
)
def create_resource_observation(
    payload: ObservationCreate,
    facility_id: str = FacilityId,
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
) -> ObservationResponse:
    return service.create_observation(db, facility_id, payload, now)
