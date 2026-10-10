"""Database access for daily history. Other modules should call the service instead."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.forecasting.models import DailyResourceRecord, DailyServiceDemand


def list_resource_records(db: Session, facility_id: str) -> list[DailyResourceRecord]:
    stmt = (
        select(DailyResourceRecord)
        .where(DailyResourceRecord.facility_id == facility_id)
        .order_by(DailyResourceRecord.record_date, DailyResourceRecord.resource_id)
    )
    return list(db.scalars(stmt))


def list_demand_records(db: Session, facility_id: str, service_id: str) -> list[DailyServiceDemand]:
    stmt = (
        select(DailyServiceDemand)
        .where(
            DailyServiceDemand.facility_id == facility_id,
            DailyServiceDemand.service_id == service_id,
        )
        .order_by(DailyServiceDemand.record_date)
    )
    return list(db.scalars(stmt))


def get_resource_record(db: Session, key: tuple) -> DailyResourceRecord | None:
    return db.get(DailyResourceRecord, key)


def get_demand_record(db: Session, key: tuple) -> DailyServiceDemand | None:
    return db.get(DailyServiceDemand, key)


def add(db: Session, record: DailyResourceRecord | DailyServiceDemand) -> None:
    db.add(record)
