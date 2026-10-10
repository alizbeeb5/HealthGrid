"""Funding package proposals. Owner: backend/data (API); engine: optimization/data.
Proposals require human review; nothing is purchased or approved."""

from datetime import datetime

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.facilities.router import server_now
from app.modules.investments import service
from app.modules.investments.errors import InvestmentErrorResponse, InvestmentRoute
from app.modules.investments.schemas import (
    InvestmentCatalog,
    InvestmentRun,
    InvestmentRunRequest,
)

router = APIRouter(prefix="/investments", tags=["investments"], route_class=InvestmentRoute)
ERRORS = {code: {"model": InvestmentErrorResponse} for code in (404, 422)}


@router.get("/catalog", operation_id="get_investment_catalog")
def get_investment_catalog() -> InvestmentCatalog:
    """Versioned synthetic starter catalog. Requests carry their own reviewed copy."""
    return service.get_catalog()


@router.post("/runs", status_code=201, operation_id="create_investment_run", responses=ERRORS)
def create_investment_run(
    request: InvestmentRunRequest,
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
) -> InvestmentRun:
    """Select and save a funding package from a saved allocation proposal's frozen
    post-transfer state. Every outcome, including no improvement, is saved."""
    return service.create_run(db, request, now)


@router.get("/runs/{investment_run_id}", operation_id="get_investment_run", responses=ERRORS)
def get_investment_run(
    investment_run_id: str = Path(min_length=1, max_length=64),
    db: Session = Depends(get_session),
) -> InvestmentRun:
    """The saved proposal as computed; reopening never re-solves or reloads the catalog."""
    return service.get_run(db, investment_run_id)
