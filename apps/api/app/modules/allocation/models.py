"""Allocation ORM model. Owner: backend/data. Changes need a matching migration.

Insert-only. The full request, frozen evidence references and result are stored so
reopening returns the saved proposal, never a new solve.
"""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import UTCDateTime


class AllocationRun(Base):
    __tablename__ = "allocation_runs"

    allocation_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    simulation_run_id: Mapped[str] = mapped_column(
        ForeignKey("simulation_runs.run_id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    engine_version: Mapped[str] = mapped_column(String(64))
    solver_version: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)  # the complete AllocationRun
