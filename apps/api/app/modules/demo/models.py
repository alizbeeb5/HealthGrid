from datetime import datetime

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import UTCDateTime


class DemoExercise(Base):
    __tablename__ = "demo_exercises"

    exercise_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    phase: Mapped[str] = mapped_column(String(32))
    clock: Mapped[datetime] = mapped_column(UTCDateTime())
    manifest: Mapped[dict] = mapped_column(JSON)
