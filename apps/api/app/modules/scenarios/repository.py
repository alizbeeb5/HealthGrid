"""Database access for scenarios. Insert and read only; rows are never updated."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.scenarios.models import (
    Incident,
    IncidentBaseline,
    IncidentRevision,
    SimulationRun,
)


def add(db: Session, *rows) -> None:
    for row in rows:
        db.add(row)
        db.flush()  # models have no relationships, so insert order is explicit


def get_incident(db: Session, incident_id: str) -> Incident | None:
    return db.get(Incident, incident_id)


def get_revision(db: Session, revision_id: str) -> IncidentRevision | None:
    return db.get(IncidentRevision, revision_id)


def list_revisions(db: Session, incident_id: str | None = None) -> list[IncidentRevision]:
    stmt = select(IncidentRevision).order_by(
        IncidentRevision.incident_id, IncidentRevision.created_at, IncidentRevision.revision_id
    )
    if incident_id is not None:
        stmt = stmt.where(IncidentRevision.incident_id == incident_id)
    return list(db.scalars(stmt))


def get_confirmed_revision(db: Session, incident_id: str) -> IncidentRevision | None:
    stmt = select(IncidentRevision).where(
        IncidentRevision.incident_id == incident_id, IncidentRevision.status == "confirmed"
    )
    return db.scalars(stmt).first()


def get_baseline(db: Session, baseline_id: str) -> IncidentBaseline | None:
    return db.get(IncidentBaseline, baseline_id)


def get_run(db: Session, run_id: str) -> SimulationRun | None:
    return db.get(SimulationRun, run_id)


def find_run(db: Session, revision_id: str, engine_version: str) -> SimulationRun | None:
    stmt = select(SimulationRun).where(
        SimulationRun.revision_id == revision_id, SimulationRun.engine_version == engine_version
    )
    return db.scalars(stmt).first()
