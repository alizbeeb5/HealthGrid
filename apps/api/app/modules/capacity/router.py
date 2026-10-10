"""Usable capacity calculations and bottlenecks. Owner: backend/data."""

from datetime import datetime

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.capacity import service
from app.modules.capacity.schemas import FacilityCapacityResponse
from app.modules.facilities.errors import FacilityRoute
from app.modules.facilities.router import ERRORS, server_now

# FacilityRoute gives the Feature 1 error envelope, including facility_not_found.
router = APIRouter(prefix="/capacity", tags=["capacity"], route_class=FacilityRoute)


@router.get(
    "/facilities/{facility_id}",
    operation_id="get_facility_capacity",
    responses={404: ERRORS[404], 422: ERRORS[422]},
)
def get_facility_capacity(
    facility_id: str = Path(min_length=1, max_length=64),
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
) -> FacilityCapacityResponse:
    """Modeled single-service capacity from reported resources.

    A resource-based estimate under demo requirement profiles, not confirmed spare
    admission capacity. Unknown capacity is a successful result, not an error.
    """
    return service.get_facility_capacity(db, facility_id, now)
