"""Daily history import and facility forecasts through the pure forecasting engine."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.engines import forecasting as forecasting_engine
from app.modules.capacity import service as capacity
from app.modules.facilities import service as facilities
from app.modules.facilities.errors import FacilityNotFound, InvalidRequest
from app.modules.facilities.schemas import FacilitySnapshotResponse, FieldError
from app.modules.forecasting import repository
from app.modules.forecasting.models import (
    DailyResourceRecord as ResourceRow,
)
from app.modules.forecasting.models import (
    DailyServiceDemand as DemandRow,
)
from app.modules.forecasting.schemas import (
    DailyDemandRecord,
    DailyHistoryImport,
    DailyHistoryImportResult,
    DailyResourceRecord,
    FacilityForecastResponse,
    ForecastInput,
)


class HistoryImportError(ValueError):
    """The import was rejected as a whole; nothing was written."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


class ForecastEngineError(RuntimeError):
    """Engine missing or returned a result for the wrong request. Served as HTTP 500."""


def _snapshots(
    db: Session, facility_ids: set[str], now: datetime
) -> dict[str, FacilitySnapshotResponse]:
    snapshots = {}
    for facility_id in sorted(facility_ids):
        try:
            snapshots[facility_id] = facilities.get_snapshot(db, facility_id, now)
        except FacilityNotFound:
            pass
    return snapshots


def import_daily_history(
    db: Session, payload: DailyHistoryImport, now: datetime
) -> DailyHistoryImportResult:
    """Validate everything, then insert new days. Existing days are never overwritten:
    an identical record is skipped, a different one rejects the whole import."""
    facility_ids = {r.facility_id for r in payload.resource_records + payload.demand_records}
    snapshots = _snapshots(db, facility_ids, now)
    errors: list[str] = []
    new_rows: list[ResourceRow | DemandRow] = []
    unchanged = 0
    seen: set[tuple] = set()

    def check_common(path: str, record, key: tuple) -> FacilitySnapshotResponse | None:
        if key in seen:
            errors.append(f"{path}: duplicate record for {key}.")
        seen.add(key)
        if record.date > now.date():
            errors.append(f"{path}.date: history cannot be in the future.")
        snapshot = snapshots.get(record.facility_id)
        if snapshot is None:
            errors.append(f"{path}.facility_id: unknown facility {record.facility_id}.")
        return snapshot

    def store(path: str, row, existing) -> None:
        nonlocal unchanged
        fields = ("available_quantity", "unit", "source", "data_quality", "peak_required_places")
        if existing is None:
            new_rows.append(row)
        elif all(getattr(existing, f, None) == getattr(row, f, None) for f in fields):
            unchanged += 1
        else:
            errors.append(f"{path}: differs from the stored record; history is not overwritten.")

    for i, record in enumerate(payload.resource_records):
        path = f"resource_records.{i}"
        key = ("resource", record.facility_id, record.resource_id, record.date)
        snapshot = check_common(path, record, key)
        if snapshot is None:
            continue
        resource = next(
            (r for r in snapshot.resources if r.resource_id == record.resource_id), None
        )
        if resource is None:
            errors.append(
                f"{path}.resource_id: {record.resource_id} is not tracked for "
                f"{record.facility_id}."
            )
            continue
        if record.unit != resource.unit:
            errors.append(f"{path}.unit: expected {resource.unit.value}.")
        if not resource.allows_fractional and not record.available_quantity.is_integer():
            errors.append(f"{path}.available_quantity: must be a whole number.")
        row = ResourceRow(
            facility_id=record.facility_id,
            resource_id=record.resource_id,
            record_date=record.date,
            available_quantity=record.available_quantity,
            unit=record.unit,
            source=record.source,
            data_quality=record.data_quality,
            imported_at=now,
        )
        store(path, row, repository.get_resource_record(db, key[1:]))

    for i, record in enumerate(payload.demand_records):
        path = f"demand_records.{i}"
        key = ("demand", record.facility_id, record.service_id, record.date)
        snapshot = check_common(path, record, key)
        if snapshot is None:
            continue
        if not any(s.service_id == record.service_id for s in snapshot.services):
            errors.append(
                f"{path}.service_id: {record.facility_id} does not offer {record.service_id}."
            )
            continue
        row = DemandRow(
            facility_id=record.facility_id,
            service_id=record.service_id,
            record_date=record.date,
            peak_required_places=record.peak_required_places,
            source=record.source,
            data_quality=record.data_quality,
            imported_at=now,
        )
        store(path, row, repository.get_demand_record(db, key[1:]))

    if errors:
        db.rollback()
        raise HistoryImportError(errors)
    for row in new_rows:
        repository.add(db, row)
    db.commit()
    return DailyHistoryImportResult(
        inserted_resource_records=sum(isinstance(r, ResourceRow) for r in new_rows),
        inserted_demand_records=sum(isinstance(r, DemandRow) for r in new_rows),
        unchanged_records=unchanged,
    )


def _resource_record(row: ResourceRow) -> DailyResourceRecord:
    return DailyResourceRecord(
        facility_id=row.facility_id,
        resource_id=row.resource_id,
        date=row.record_date,
        available_quantity=row.available_quantity,
        unit=row.unit,
        source=row.source,
        data_quality=row.data_quality,
    )


def _demand_record(row: DemandRow) -> DailyDemandRecord:
    return DailyDemandRecord(
        facility_id=row.facility_id,
        service_id=row.service_id,
        date=row.record_date,
        peak_required_places=row.peak_required_places,
        source=row.source,
        data_quality=row.data_quality,
    )


def get_facility_forecast(
    db: Session, facility_id: str, service_id: str, now: datetime
) -> FacilityForecastResponse:
    snapshot = facilities.get_snapshot(db, facility_id, now)  # raises FacilityNotFound
    service = next((s for s in snapshot.services if s.service_id == service_id), None)
    if service is None:
        message = f"Facility {facility_id} does not offer service {service_id}."
        raise InvalidRequest([FieldError(field="service_id", message=message)])

    profiles = capacity.get_profiles(db)
    inputs = ForecastInput(
        facility_id=facility_id,
        service_id=service_id,
        service_status=service.status,
        requirement=profiles.get(service_id),
        resource_records=[
            _resource_record(row) for row in repository.list_resource_records(db, facility_id)
        ],
        demand_records=[
            _demand_record(row)
            for row in repository.list_demand_records(db, facility_id, service_id)
        ],
        generated_at=now,
    )
    forecast = getattr(forecasting_engine, "forecast_service_capacity", None)
    if forecast is None:
        raise ForecastEngineError("engines.forecasting.forecast_service_capacity is missing.")
    result = forecast(inputs)
    if (result.facility_id, result.service_id) != (facility_id, service_id):
        raise ForecastEngineError(
            f"Engine returned {result.facility_id}/{result.service_id} for "
            f"{facility_id}/{service_id}."
        )
    # Revalidate so engine output that breaks contract invariants fails visibly.
    return FacilityForecastResponse.model_validate(result.model_dump())
