"""Decision tracking and outcome review endpoints. Owner: backend/data.
Identities are self-reported demo names; nothing here changes hospital inventory."""

from datetime import datetime

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.decisions import service
from app.modules.decisions.errors import DecisionRoute
from app.modules.decisions.schemas import (
    DecisionCreateRequest,
    DecisionErrorResponse,
    DecisionEventRequest,
    DecisionListResponse,
    DecisionRecord,
    DecisionStatus,
    OutcomeReview,
    OutcomeReviewListResponse,
    OutcomeReviewRequest,
)
from app.modules.facilities.router import server_now

router = APIRouter(prefix="/decisions", tags=["decisions"], route_class=DecisionRoute)
ERRORS = {code: {"model": DecisionErrorResponse} for code in (404, 409, 422)}


def Id():  # noqa: N802 - a fresh Path per parameter; FastAPI mutates shared ones
    return Path(min_length=1, max_length=64)


@router.post("", status_code=201, operation_id="create_decision", responses=ERRORS)
def create_decision(
    request: DecisionCreateRequest,
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
) -> DecisionRecord:
    """Record a draft decision for a validated saved proposal. Freezes its expectation."""
    return service.create(db, request, now)


@router.get("", operation_id="list_decisions")
def list_decisions(
    status: DecisionStatus | None = None, db: Session = Depends(get_session)
) -> DecisionListResponse:
    return service.list_decisions(db, status)


@router.get("/{decision_id}", operation_id="get_decision", responses=ERRORS)
def get_decision(decision_id: str = Id(), db: Session = Depends(get_session)) -> DecisionRecord:
    return service.get(db, decision_id)


@router.post("/{decision_id}/events", status_code=201, operation_id="apply_decision_event",
             responses={200: {"model": DecisionRecord}, **ERRORS})
def apply_decision_event(
    command: DecisionEventRequest,
    response: Response,
    decision_id: str = Id(),
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
) -> DecisionRecord:
    """Apply one command. 201 when applied; 200 returns the saved result of a retried
    request_id. Outdated expected_version is 409."""
    record, applied = service.apply_event(db, decision_id, command, now)
    if not applied:
        response.status_code = 200
    return record


@router.post("/{decision_id}/reviews", status_code=201, operation_id="create_outcome_review",
             responses={200: {"model": OutcomeReview}, **ERRORS})
def create_outcome_review(
    request: OutcomeReviewRequest,
    response: Response,
    decision_id: str = Id(),
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
) -> OutcomeReview:
    """Capture current reports and compare them with the frozen expectation. The
    capture time is the server's; reopening returns this review unchanged."""
    review, created = service.create_review(db, decision_id, request, now)
    if not created:
        response.status_code = 200
    return review


@router.get("/{decision_id}/reviews/{review_id}", operation_id="get_outcome_review",
            responses=ERRORS)
def get_outcome_review(
    decision_id: str = Id(), review_id: str = Id(), db: Session = Depends(get_session)
) -> OutcomeReview:
    return service.get_review(db, decision_id, review_id)



@router.get("/{decision_id}/reviews", operation_id="list_outcome_reviews", responses=ERRORS)
def list_outcome_reviews(
    decision_id: str = Id(), db: Session = Depends(get_session)
) -> OutcomeReviewListResponse:
    """Return saved review history, newest first; never recapture or recalculate."""
    return OutcomeReviewListResponse(items=service.list_reviews(db, decision_id))
