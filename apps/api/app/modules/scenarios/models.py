"""Scenario ORM models. Owner: backend/data. Changes need a matching migration.

Rows are insert-only: drafts, confirmed revisions, baselines and runs are never
updated. Payloads are JSON with schema_version for the demo.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import UTCDateTime


class Incident(Base):
    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


class IncidentBaseline(Base):
    __tablename__ = "incident_baselines"

    baseline_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    service_id: Mapped[str] = mapped_column(String(64))
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime())
    schema_version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)


class IncidentRevision(Base):
    __tablename__ = "incident_revisions"
    __table_args__ = (
        # One confirmation per draft: a confirmed revision's parent is its draft.
        UniqueConstraint("parent_revision_id", name="uq_incident_revisions_parent_revision_id"),
        CheckConstraint("status IN ('draft', 'confirmed')", name="status"),
        CheckConstraint(
            "(status = 'draft' AND baseline_id IS NULL AND confirmed_at IS NULL"
            " AND confirmed_by IS NULL) OR (status = 'confirmed' AND baseline_id IS NOT NULL"
            " AND confirmed_at IS NOT NULL AND confirmed_by IS NOT NULL)",
            name="confirmation_fields",
        ),
    )

    revision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.incident_id"), index=True)
    parent_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("incident_revisions.revision_id")
    )
    status: Mapped[str] = mapped_column(String(20))
    input: Mapped[dict] = mapped_column(JSON)
    schema_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    confirmed_by: Mapped[str | None] = mapped_column(String(100))
    baseline_id: Mapped[str | None] = mapped_column(
        ForeignKey("incident_baselines.baseline_id"), unique=True
    )


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    __table_args__ = (
        UniqueConstraint(
            "revision_id", "engine_version", name="uq_simulation_runs_revision_engine"
        ),
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("incident_revisions.revision_id"))
    engine_version: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    impact: Mapped[dict] = mapped_column(JSON)
