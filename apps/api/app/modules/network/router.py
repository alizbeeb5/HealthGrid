"""Network capacity dashboard endpoints. Owner: backend/data."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.facilities.errors import FacilityRoute
from app.modules.facilities.router import ERRORS, server_now
from app.modules.network import service
from app.modules.network.schemas import NetworkOverviewResponse, NetworkServiceListResponse

# FacilityRoute maps request validation to the shared invalid_request envelope.
router = APIRouter(prefix="/network", tags=["network"], route_class=FacilityRoute)


@router.get("/services", operation_id="list_network_services")
def list_network_services(db: Session = Depends(get_session)) -> NetworkServiceListResponse:
    return service.list_services(db)


@router.get(
    "/overview",
    operation_id="get_network_overview",
    responses={422: ERRORS[422]},
)
def get_network_overview(
    service_id: str = Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
) -> NetworkOverviewResponse:
    """Modeled single-service capacity for every facility offering the service.

    An unknown service_id returns 200 with service_name null and no facilities.
    Estimates are demo resource-based models, not spare admission capacity.
    """
    return service.get_overview(db, service_id, now)
