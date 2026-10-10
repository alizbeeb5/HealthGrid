"""Resource transfer proposals under hard constraints. Owner: backend/data (API);
engine: optimization/data. Proposals require human review; nothing is dispatched."""

from datetime import datetime

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.allocation import service
from app.modules.allocation.errors import AllocationErrorResponse, AllocationRoute
from app.modules.allocation.schemas import AllocationRun, AllocationRunRequest
from app.modules.facilities.router import server_now

router = APIRouter(prefix="/allocation", tags=["allocation"], route_class=AllocationRoute)
ERRORS = {code: {"model": AllocationErrorResponse} for code in (404, 422)}


@router.post("/runs", status_code=201, operation_id="create_allocation_run", responses=ERRORS)
def create_allocation_run(
    request: AllocationRunRequest,
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
) -> AllocationRun:
    """Solve and save a transfer proposal from a saved simulation's frozen scenario.
    Needs-inputs, no-improvement and no-solution outcomes are saved results too."""
    return service.create_run(db, request, now)


@router.get("/runs/{allocation_run_id}", operation_id="get_allocation_run", responses=ERRORS)
def get_allocation_run(
    allocation_run_id: str = Path(min_length=1, max_length=64),
    db: Session = Depends(get_session),
) -> AllocationRun:
    """The saved proposal as computed; reopening never re-solves."""
    return service.get_run(db, allocation_run_id)
