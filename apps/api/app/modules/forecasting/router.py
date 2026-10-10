"""Capacity and demand forecasts. Owner: backend/data (API); engine: forecasting/data."""

from datetime import datetime

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.facilities.errors import FacilityRoute
from app.modules.facilities.router import ERRORS, server_now
from app.modules.forecasting import service
from app.modules.forecasting.schemas import FacilityForecastResponse

# FacilityRoute gives the shared facility_not_found / invalid_request envelopes.
router = APIRouter(prefix="/forecasts", tags=["forecasts"], route_class=FacilityRoute)


@router.get(
    "/facilities/{facility_id}",
    operation_id="get_facility_forecast",
    responses={404: ERRORS[404], 422: ERRORS[422]},
)
def get_facility_forecast(
    facility_id: str = Path(min_length=1, max_length=64),
    service_id: str = Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
) -> FacilityForecastResponse:
    """Seven-day modeled capacity and demand forecast for one facility service.

    Insufficient history is a successful result with status insufficient_history.
    Predicted gaps are not calibrated shortage probabilities. Synthetic demo data.
    """
    return service.get_facility_forecast(db, facility_id, service_id, now)
