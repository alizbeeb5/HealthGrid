"""Decision ORM models. Owner: backend/data. Changes need a matching migration.

Events and reviews are insert-only. The decision row holds the current state and a
version used for optimistic locking; every change appends an event.
"""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import UTCDateTime

ACTIVE = text("status NOT IN ('rejected', 'cancelled')")


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        # At most one non-rejected/non-cancelled decision per exact source run.
        Index("uq_decisions_active_source", "source_type", "source_run_id", unique=True,
              sqlite_where=ACTIVE, postgresql_where=ACTIVE),
    )

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(20))
    source_run_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    state: Mapped[dict] = mapped_column(JSON)  # DecisionRecord without events

    __mapper_args__ = {"version_id_col": version}


class DecisionEvent(Base):
    __tablename__ = "decision_events"
    __table_args__ = (
        UniqueConstraint("decision_id", "sequence", name="uq_decision_events_sequence"),
        UniqueConstraint("decision_id", "request_id", name="uq_decision_events_request"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.decision_id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str | None] = mapped_column(String(64))
    request_hash: Mapped[str | None] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(40))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime())
    event: Mapped[dict] = mapped_column(JSON)  # DecisionEvent
    response: Mapped[dict | None] = mapped_column(JSON)  # DecisionRecord after the event


class OutcomeReview(Base):
    __tablename__ = "outcome_reviews"
    __table_args__ = (
        UniqueConstraint("decision_id", "request_id", name="uq_outcome_reviews_request"),
    )

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.decision_id"), index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime())
    engine_version: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)  # OutcomeReview
