"""Investment ORM model. Owner: backend/data. Changes need a matching migration.

Insert-only. The full request (including the run-local candidate list), evidence
references and result are stored, so catalog or source changes never rewrite a run.
"""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import UTCDateTime


class InvestmentRun(Base):
    __tablename__ = "investment_runs"

    investment_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    allocation_run_id: Mapped[str] = mapped_column(
        ForeignKey("allocation_runs.allocation_run_id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    catalog_version: Mapped[str] = mapped_column(String(64))
    engine_version: Mapped[str] = mapped_column(String(64))
    solver_version: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)  # the complete InvestmentRun
