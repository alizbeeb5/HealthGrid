"""Facility ORM models. Owner: backend/data. Changes need a matching migration."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import UTCDateTime


class Facility(Base):
    __tablename__ = "facilities"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
    )

    facility_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)


class Service(Base):
    """A service type, e.g. emergency-care. Status is per facility."""

    __tablename__ = "services"

    service_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))


class FacilityService(Base):
    __tablename__ = "facility_services"
    __table_args__ = (
        CheckConstraint("status IN ('operating', 'limited', 'unavailable')", name="status"),
    )

    facility_id: Mapped[str] = mapped_column(
        ForeignKey("facilities.facility_id"), primary_key=True
    )
    service_id: Mapped[str] = mapped_column(ForeignKey("services.service_id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))


class ResourceDefinition(Base):
    __tablename__ = "resource_definitions"
    __table_args__ = (
        CheckConstraint(
            "category IN ('beds', 'staff', 'equipment', 'supplies', 'infrastructure')",
            name="category",
        ),
        CheckConstraint("unit IN ('bed', 'person', 'item', 'liter')", name="unit"),
    )

    resource_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32))
    unit: Mapped[str] = mapped_column(String(32))
    allows_fractional: Mapped[bool] = mapped_column(Boolean)


class FacilityResource(Base):
    """Resources applicable to a facility; unreported ones appear as unknown."""

    __tablename__ = "facility_resources"

    facility_id: Mapped[str] = mapped_column(
        ForeignKey("facilities.facility_id"), primary_key=True
    )
    resource_id: Mapped[str] = mapped_column(
        ForeignKey("resource_definitions.resource_id"), primary_key=True
    )


class ResourceObservation(Base):
    """Append-only reported values. The API never updates or deletes rows."""

    __tablename__ = "resource_observations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["facility_id", "resource_id"],
            ["facility_resources.facility_id", "facility_resources.resource_id"],
            name="fk_resource_observations_facility_resource",
        ),
        CheckConstraint("available_quantity >= 0", name="quantity_nonnegative"),
        Index(
            "ix_resource_observations_latest",
            "facility_id",
            "resource_id",
            "observed_at",
            "recorded_at",
        ),
    )

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    facility_id: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(64))
    available_quantity: Mapped[float] = mapped_column(Float)
    # Stored as reported; equals the resource's unit because conversion is not allowed.
    unit: Mapped[str] = mapped_column(String(32))
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
