"""Daily history ORM models. Owner: backend/data. Changes need a matching migration.

Insert-only history kept apart from Feature 1 observations. Forecast results are
computed per request and never stored here or as observations.
"""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKeyConstraint,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import UTCDateTime


class DailyResourceRecord(Base):
    __tablename__ = "daily_resource_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["facility_id", "resource_id"],
            ["facility_resources.facility_id", "facility_resources.resource_id"],
            name="fk_daily_resource_records_facility_resource",
        ),
        CheckConstraint("available_quantity >= 0", name="quantity_nonnegative"),
        CheckConstraint("data_quality IN ('reported', 'estimated')", name="data_quality"),
    )

    facility_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    record_date: Mapped[date] = mapped_column(Date, primary_key=True)
    available_quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(200))
    data_quality: Mapped[str] = mapped_column(String(20))
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime())


class DailyServiceDemand(Base):
    __tablename__ = "daily_service_demand"
    __table_args__ = (
        ForeignKeyConstraint(
            ["facility_id", "service_id"],
            ["facility_services.facility_id", "facility_services.service_id"],
            name="fk_daily_service_demand_facility_service",
        ),
        CheckConstraint("peak_required_places >= 0", name="places_nonnegative"),
        CheckConstraint("data_quality IN ('reported', 'estimated')", name="data_quality"),
    )

    facility_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    service_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    record_date: Mapped[date] = mapped_column(Date, primary_key=True)
    peak_required_places: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(200))
    data_quality: Mapped[str] = mapped_column(String(20))
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime())
