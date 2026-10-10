"""Database access for allocation runs. Insert and read only."""

from sqlalchemy.orm import Session

from app.modules.allocation.models import AllocationRun


def add(db: Session, row: AllocationRun) -> None:
    db.add(row)
    db.flush()


def get(db: Session, allocation_run_id: str) -> AllocationRun | None:
    return db.get(AllocationRun, allocation_run_id)
