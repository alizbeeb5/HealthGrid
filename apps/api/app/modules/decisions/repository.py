"""Database access for decisions. Events and reviews are insert-only."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.decisions.models import Decision, DecisionEvent, OutcomeReview


def add(db: Session, *rows) -> None:
    for row in rows:
        db.add(row)
        db.flush()  # models have no relationships, so insert order is explicit


def get(db: Session, decision_id: str) -> Decision | None:
    return db.get(Decision, decision_id)


def list_decisions(db: Session, status: str | None = None) -> list[Decision]:
    stmt = select(Decision).order_by(Decision.updated_at.desc(), Decision.decision_id)
    if status is not None:
        stmt = stmt.where(Decision.status == status)
    return list(db.scalars(stmt))


def active_for_source(db: Session, source_type: str, source_run_id: str) -> Decision | None:
    stmt = select(Decision).where(
        Decision.source_type == source_type, Decision.source_run_id == source_run_id,
        Decision.status.not_in(("rejected", "cancelled")))
    return db.scalars(stmt).first()


def events(db: Session, decision_id: str) -> list[DecisionEvent]:
    stmt = select(DecisionEvent).where(DecisionEvent.decision_id == decision_id).order_by(
        DecisionEvent.sequence)
    return list(db.scalars(stmt))


def event_for_request(db: Session, decision_id: str, request_id: str) -> DecisionEvent | None:
    stmt = select(DecisionEvent).where(DecisionEvent.decision_id == decision_id,
                                       DecisionEvent.request_id == request_id)
    return db.scalars(stmt).first()


def get_review(db: Session, review_id: str) -> OutcomeReview | None:
    return db.get(OutcomeReview, review_id)


def review_for_request(db: Session, decision_id: str, request_id: str) -> OutcomeReview | None:
    stmt = select(OutcomeReview).where(OutcomeReview.decision_id == decision_id,
                                       OutcomeReview.request_id == request_id)
    return db.scalars(stmt).first()



def list_reviews(db: Session, decision_id: str) -> list[OutcomeReview]:
    stmt = select(OutcomeReview).where(OutcomeReview.decision_id == decision_id).order_by(
        OutcomeReview.captured_at.desc(), OutcomeReview.review_id)
    return list(db.scalars(stmt))
