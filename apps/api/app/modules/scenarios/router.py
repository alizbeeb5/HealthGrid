"""Incident drafts, confirmed revisions, baselines and saved runs. Owner: backend/data."""

from datetime import datetime

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.facilities.router import server_now
from app.modules.scenarios import service
from app.modules.scenarios.errors import ScenarioRoute
from app.modules.scenarios.schemas import (
    IncidentConfirmRequest,
    IncidentDraftInput,
    IncidentListResponse,
    IncidentRevision,
    ScenarioErrorResponse,
    SimulationRun,
)

router = APIRouter(prefix="/scenarios", tags=["scenarios"], route_class=ScenarioRoute)


def Id():  # noqa: N802 - a fresh Path per parameter; FastAPI mutates shared ones
    return Path(min_length=1, max_length=64)


def errors(*codes: int) -> dict:
    return {code: {"model": ScenarioErrorResponse} for code in (422, *codes)}


@router.post("/incidents", status_code=201, operation_id="create_incident_draft",
             responses=errors())
def create_incident_draft(
    payload: IncidentDraftInput,
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
) -> IncidentRevision:
    """Save a draft. A draft is not an operational approval."""
    return service.create_draft(db, payload, now)


@router.get("/incidents", operation_id="list_incidents")
def list_incidents(db: Session = Depends(get_session)) -> IncidentListResponse:
    return service.list_incidents(db)


@router.get("/incidents/{incident_id}/revisions/{revision_id}",
            operation_id="get_incident_revision", responses=errors(404))
def get_incident_revision(
    incident_id: str = Id(), revision_id: str = Id(), db: Session = Depends(get_session)
) -> IncidentRevision:
    return service.get_revision(db, incident_id, revision_id)


@router.post("/incidents/{incident_id}/confirm", status_code=201,
             operation_id="confirm_incident", responses=errors(404, 409))
def confirm_incident(
    request: IncidentConfirmRequest,
    incident_id: str = Id(),
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
) -> IncidentRevision:
    """Confirm reviewed inputs and capture the baseline atomically. Do not auto-retry;
    a repeated or concurrent confirmation returns 409 with the existing revision."""
    return service.confirm(db, incident_id, request, now)


@router.post("/incidents/{incident_id}/revisions/{revision_id}/simulate", status_code=201,
             operation_id="simulate_incident", responses={200: {"model": SimulationRun},
                                                          **errors(404, 409)})
def simulate_incident(
    response: Response,
    incident_id: str = Id(),
    revision_id: str = Id(),
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
) -> SimulationRun:
    """201 with a new saved run, or 200 with the run already saved for this revision."""
    run, created = service.simulate(db, incident_id, revision_id, now)
    if not created:
        response.status_code = 200
    return run


@router.get("/runs/{run_id}", operation_id="get_simulation_run", responses=errors(404))
def get_simulation_run(run_id: str = Id(), db: Session = Depends(get_session)) -> SimulationRun:
    return service.get_run(db, run_id)
