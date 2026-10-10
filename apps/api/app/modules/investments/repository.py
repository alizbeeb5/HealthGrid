"""Database access for investment runs. Insert and read only."""

from sqlalchemy.orm import Session

from app.modules.investments.models import InvestmentRun


def add(db: Session, row: InvestmentRun) -> None:
    db.add(row)
    db.flush()


def get(db: Session, investment_run_id: str) -> InvestmentRun | None:
    return db.get(InvestmentRun, investment_run_id)
