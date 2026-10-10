"""Pure seven-day weekly seasonal forecasts; no persistence, HTTP or implicit clock.

The canonical boundary accepts ForecastInput and returns the Pydantic API result.
Dataclasses describe the internal snapshot-based seasonal model only.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import ceil
from statistics import mean
from typing import TYPE_CHECKING, Sequence

from app.engines.capacity import CAPACITY_UNIT, calculate_service_capacity
from app.modules.capacity.schemas import ServiceRequirement
from app.modules.facilities.schemas import FacilitySnapshotResponse

if TYPE_CHECKING:
    from app.modules.forecasting.schemas import FacilityForecastResponse, ForecastInput

ENGINE_VERSION = "weekly-seasonal-v1"
HORIZON_DAYS = 7
HOLDOUT_DAYS = 14
MIN_HISTORY_DAYS = 56


class ForecastInputError(ValueError):
    """Invalid or inadequate inputs; never replace unknown observations with zero."""


@dataclass(frozen=True)
class DailyHistoryRecord:
    date: date
    snapshot: FacilitySnapshotResponse
    demand: int | None
    source: str
    data_quality: str
    capacity_unit: str
    profile_version: str


@dataclass(frozen=True)
class HistoricalDay:
    date: date
    modeled_capacity: int | None
    demand: int | None
    capacity_status: str
    reason_codes: tuple[str, ...]
    source: str
    data_quality: str
    observation_ids: tuple[str, ...]


@dataclass(frozen=True)
class ForecastDay:
    date: date
    predicted_capacity: int
    predicted_demand: int
    capacity_lower: int
    capacity_upper: int
    demand_lower: int
    demand_upper: int
    expected_gap: int


@dataclass(frozen=True)
class ForecastAlert:
    date: date
    expected_gap: int
    reason_code: str = "predicted_demand_exceeds_modeled_capacity"


@dataclass(frozen=True)
class ForecastValidation:
    method: str
    engine_version: str
    training_days: int
    withheld_days: int
    evaluated_days: int
    capacity_mae: float
    demand_mae: float
    interval_method: str
    capacity_error_radius: int
    demand_error_radius: int


@dataclass(frozen=True)
class ForecastResult:
    facility_id: str
    service_id: str
    generated_at: datetime
    horizon_days: int
    capacity_unit: str
    profile_version: str
    status: str
    history: tuple[HistoricalDay, ...]
    forecast: tuple[ForecastDay, ...]
    alerts: tuple[ForecastAlert, ...]
    validation: ForecastValidation


def _seasonal_values(values: Sequence[int | None], count: int) -> list[int]:
    if len(values) < 7 or any(value is None for value in values[-7:]):
        raise ForecastInputError("The last seven baseline days must have known values.")
    return [values[-7 + (index % 7)] for index in range(count)]


def _error_radius(errors: Sequence[int]) -> int:
    # Nearest-rank 90th percentile of absolute held-out errors, not a calibrated
    # prediction interval or shortage probability. The two measures stay separate.
    ordered = sorted(errors)
    return ordered[ceil(0.9 * len(ordered)) - 1]


def forecast_daily_history(
    records: Sequence[DailyHistoryRecord],
    requirement: ServiceRequirement,
    generated_at: datetime,
) -> ForecastResult:
    """Use 56+ consecutive days, last 14 held out, then refit the seven-day baseline.

    Unknowns remain visible in history. Both the seven-day training baseline and
    final baseline must be complete; all 14 held-out targets must be usable.
    Earlier missing records do not enter the weekly baseline or validation score.
    No imputation, probability, trend, resource update, or scenario is performed.
    """
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ForecastInputError("generated_at must include a timezone.")
    generated_at = generated_at.astimezone(UTC)
    ordered = sorted(records, key=lambda row: row.date)
    if len(ordered) < MIN_HISTORY_DAYS:
        raise ForecastInputError("At least 56 daily history records are required.")
    if any(b.date != a.date + timedelta(days=1) for a, b in zip(ordered, ordered[1:])):
        raise ForecastInputError("Daily history must have unique, consecutive dates.")
    if ordered[-1].date not in {generated_at.date(), generated_at.date() - timedelta(days=1)}:
        raise ForecastInputError(
            "History must end on the generation date or preceding complete UTC day; "
            "stale history rejected."
        )

    facility_id = ordered[0].snapshot.facility.facility_id
    history = []
    for record in ordered:
        snapshot = record.snapshot
        if snapshot.facility.facility_id != facility_id:
            raise ForecastInputError("Do not combine different facilities in one forecast.")
        if record.capacity_unit != requirement.capacity_unit:
            raise ForecastInputError(
                "History and requirements must use simultaneous service places."
            )
        if record.profile_version != requirement.profile_version:
            raise ForecastInputError("Historical profile versions must match the forecast profile.")
        if not record.source.strip() or record.data_quality not in {
            "synthetic",
            "estimated",
            "reported",
            "missing",
        }:
            raise ForecastInputError("Every daily record needs a source and a known data quality.")
        if snapshot.as_of.astimezone(UTC).date() != record.date:
            raise ForecastInputError("Snapshot timestamp must match the daily record date.")
        if snapshot.as_of > generated_at:
            raise ForecastInputError("Snapshots must not be later than generation time.")
        if record.demand is not None and (
            isinstance(record.demand, bool)
            or not isinstance(record.demand, int)
            or record.demand < 0
        ):
            raise ForecastInputError(
                "Demand must be nonnegative whole simultaneous places or null."
            )
        services = [s for s in snapshot.services if s.service_id == requirement.service_id]
        if len(services) != 1:
            raise ForecastInputError(
                "Each daily snapshot must offer the requested service exactly once."
            )
        # Calculate capacity with the existing engine; no duplicate resource formula.
        result = calculate_service_capacity(snapshot, services[0], requirement)
        history.append(
            HistoricalDay(
                date=record.date,
                modeled_capacity=result.estimated_capacity,
                demand=record.demand,
                capacity_status=result.status.value,
                reason_codes=tuple(reason.value for reason in result.reason_codes),
                source=record.source,
                data_quality=record.data_quality,
                observation_ids=tuple(
                    limit.observation_id
                    for limit in result.resource_limits
                    if limit.observation_id is not None
                ),
            )
        )

    capacities = [day.modeled_capacity for day in history]
    demands = [day.demand for day in history]
    usable = sum(day.modeled_capacity is not None and day.demand is not None for day in history)
    if usable < MIN_HISTORY_DAYS - HOLDOUT_DAYS:
        raise ForecastInputError("At least 42 days need known capacity and demand.")
    split = len(history) - HOLDOUT_DAYS
    capacity_pred = _seasonal_values(capacities[:split], HOLDOUT_DAYS)
    demand_pred = _seasonal_values(demands[:split], HOLDOUT_DAYS)
    if any(value is None for value in capacities[split:] + demands[split:]):
        raise ForecastInputError("All 14 withheld days need known capacity and demand.")
    capacity_errors = [
        abs(actual - predicted) for actual, predicted in zip(capacities[split:], capacity_pred)
    ]
    demand_errors = [
        abs(actual - predicted) for actual, predicted in zip(demands[split:], demand_pred)
    ]
    capacity_radius, demand_radius = _error_radius(capacity_errors), _error_radius(demand_errors)
    future_capacities = _seasonal_values(capacities, HORIZON_DAYS)
    future_demands = _seasonal_values(demands, HORIZON_DAYS)
    forecast = tuple(
        ForecastDay(
            date=ordered[-1].date + timedelta(days=index + 1),
            predicted_capacity=capacity,
            predicted_demand=demand,
            capacity_lower=max(0, capacity - capacity_radius),
            capacity_upper=capacity + capacity_radius,
            demand_lower=max(0, demand - demand_radius),
            demand_upper=demand + demand_radius,
            expected_gap=max(0, demand - capacity),
        )
        for index, (capacity, demand) in enumerate(zip(future_capacities, future_demands))
    )
    return ForecastResult(
        facility_id=facility_id,
        service_id=requirement.service_id,
        generated_at=generated_at,
        horizon_days=HORIZON_DAYS,
        capacity_unit=requirement.capacity_unit,
        profile_version=requirement.profile_version,
        status="forecasted",
        history=tuple(history),
        forecast=forecast,
        alerts=tuple(
            ForecastAlert(day.date, day.expected_gap) for day in forecast if day.expected_gap > 0
        ),
        validation=ForecastValidation(
            method="fixed_origin_14_day_holdout",
            engine_version=ENGINE_VERSION,
            training_days=split,
            withheld_days=HOLDOUT_DAYS,
            evaluated_days=HOLDOUT_DAYS,
            capacity_mae=mean(capacity_errors),
            demand_mae=mean(demand_errors),
            interval_method="symmetric_90th_percentile_absolute_holdout_error_uncalibrated",
            capacity_error_radius=capacity_radius,
            demand_error_radius=demand_radius,
        ),
    )


def forecast_service_capacity(inputs: "ForecastInput") -> "FacilityForecastResponse":
    """Canonical API boundary: ForecastInput -> FacilityForecastResponse.

    Daily aggregates are complete only after their UTC date ends. Adapting them
    into snapshots reuses the capacity formula; it does not invent observation IDs.
    Historical service status comes from the daily record, never today's status.
    """
    from app.modules.facilities.schemas import Facility, FacilityService, ResourceSnapshot
    from app.modules.forecasting.schemas import (
        FacilityForecastResponse,
        HistoryDay,
    )
    from app.modules.forecasting.schemas import (
        ForecastAlert as Alert,
    )
    from app.modules.forecasting.schemas import (
        ForecastDay as Day,
    )
    from app.modules.forecasting.schemas import (
        ForecastValidation as Validation,
    )

    now = inputs.generated_at.astimezone(UTC)
    resources = {}
    demands = {}
    for record in inputs.resource_records:
        if record.facility_id != inputs.facility_id:
            raise ValueError("Historical resources belong to a different facility.")
        if record.date >= now.date():
            continue  # Today's daily peak/aggregate is not complete yet.
        key = (record.date, record.resource_id)
        if key in resources:
            raise ValueError("Duplicate historical resource record.")
        resources[key] = record
    for record in inputs.demand_records:
        if (record.facility_id, record.service_id) != (inputs.facility_id, inputs.service_id):
            raise ValueError("Historical demand belongs to a different facility/service.")
        if record.date >= now.date():
            continue
        if record.date in demands:
            raise ValueError("Duplicate historical demand record.")
        demands[record.date] = record
    profile = inputs.requirement
    if profile is not None and profile.service_id != inputs.service_id:
        raise ValueError("Requirement profile does not match the requested service.")
    required = {r.resource_id: r for r in profile.requirements} if profile else {}
    dates = {day for day, rid in resources if rid in required} | set(demands)
    history, records = [], []
    if dates:
        day = min(dates)
        last = max(dates)
        while day <= last:
            demand = demands.get(day)
            used = [resources[(day, rid)] for rid in sorted(required) if (day, rid) in resources]
            evidence = used + ([demand] if demand else [])
            sources = sorted({r.source for r in evidence})
            quality = (
                (
                    "estimated"
                    if any(r.data_quality == "estimated" for r in evidence)
                    else "reported"
                )
                if evidence
                else None
            )
            timestamp = datetime.combine(day, datetime.max.time(), tzinfo=UTC)
            snapshot = FacilitySnapshotResponse(
                facility=Facility(
                    facility_id=inputs.facility_id,
                    name=inputs.facility_id,
                    latitude=0,
                    longitude=0,
                    last_reported_at=None,
                ),
                services=[
                    FacilityService(
                        facility_id=inputs.facility_id,
                        service_id=inputs.service_id,
                        name=inputs.service_id,
                        status=demand.service_status if demand else "limited",
                    )
                ],
                resources=[
                    ResourceSnapshot(
                        resource_id=r.resource_id,
                        name=r.resource_id,
                        category="infrastructure",
                        unit=r.unit,
                        allows_fractional=r.unit == "liter",
                        available_quantity=r.available_quantity,
                        observation_id=None,
                        observed_at=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
                        recorded_at=None,
                        data_status="current",
                    )
                    for r in used
                ],
                as_of=timestamp,
                stale_after_hours=24,
            )
            if profile:
                for r in used:
                    if r.unit != required[r.resource_id].unit:
                        raise ValueError("Historical resource unit does not match profile.")
                modeled = calculate_service_capacity(snapshot, snapshot.services[0], profile)
                value = modeled.estimated_capacity
                records.append(
                    DailyHistoryRecord(
                        date=day,
                        snapshot=snapshot,
                        demand=demand.peak_required_places if demand else None,
                        source="; ".join(sources) or "missing daily records",
                        data_quality=quality or "missing",
                        capacity_unit=profile.capacity_unit,
                        profile_version=profile.profile_version,
                    )
                )
            else:
                value = None
            history.append(
                HistoryDay(
                    date=day,
                    capacity=value,
                    demand=demand.peak_required_places if demand else None,
                    sources=sources,
                    data_quality=quality,
                )
            )
            day += timedelta(days=1)
    common = dict(
        facility_id=inputs.facility_id,
        service_id=inputs.service_id,
        generated_at=now,
        horizon_days=7,
        capacity_unit=CAPACITY_UNIT,
        profile_version=profile.profile_version if profile else None,
        history=history,
    )
    if profile is None:
        return FacilityForecastResponse(
            **common, status="not_configured", forecast=[], alerts=[], validation=None
        )
    try:
        result = forecast_daily_history(records, profile, now)
    except ForecastInputError:
        return FacilityForecastResponse(
            **common, status="insufficient_history", forecast=[], alerts=[], validation=None
        )
    days = [
        Day(**{field: getattr(day, field) for field in Day.model_fields}) for day in result.forecast
    ]
    return FacilityForecastResponse(
        **common,
        status="forecasted",
        forecast=days,
        alerts=[
            Alert(
                date=d.date,
                code="predicted_gap",
                expected_gap=d.expected_gap,
                message=f"Expected simultaneous demand exceeds modeled capacity by "
                f"{d.expected_gap} places.",
            )
            for d in days
            if d.expected_gap > 0
        ],
        validation=Validation(
            method=result.validation.method,
            holdout_days=HOLDOUT_DAYS,
            evaluated_from=history[-HOLDOUT_DAYS].date,
            evaluated_to=history[-1].date,
            capacity_mae=result.validation.capacity_mae,
            demand_mae=result.validation.demand_mae,
        ),
    )
