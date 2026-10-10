"""Shared Feature 4 forecast contract. Owner: backend/data.

See docs/feature-4-forecast-contract.md. Capacity and demand are both measured in
simultaneous service places. Missing data stays null/absent; it never becomes zero.
Forecasts are model outputs and are never stored as reported observations.
"""

import datetime as dt
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from app.modules.capacity.schemas import CapacityUnit, ServiceRequirement
from app.modules.facilities.schemas import (
    ContractModel,
    Identifier,
    Quantity,
    ResourceUnit,
    ServiceStatus,
)

HORIZON_DAYS = 7
Places = Annotated[int, Field(ge=0, strict=True)]
PredictedPlaces = Annotated[float, Field(ge=0, allow_inf_nan=False)]
SourceLabel = Annotated[str, Field(min_length=1, max_length=200)]
# Tolerance for float comparisons in the invariants below.
_EPSILON = 1e-9


class DataQuality(StrEnum):
    REPORTED = "reported"  # as received from the facility or dataset source
    ESTIMATED = "estimated"  # backfilled or derived by a person, not directly reported


class ForecastStatus(StrEnum):
    FORECASTED = "forecasted"
    INSUFFICIENT_HISTORY = "insufficient_history"
    NOT_CONFIGURED = "not_configured"


def _require_ascending_unique(values: list, name: str) -> None:
    if values != sorted(set(values)):
        raise ValueError(f"{name} must be in ascending order without duplicates.")


# Historical inputs (import format and engine input).


class DailyResourceRecord(ContractModel):
    """One day's available quantity of a resource, as defined by the dataset source."""

    facility_id: Identifier
    resource_id: Identifier
    date: dt.date
    available_quantity: Quantity
    unit: ResourceUnit
    source: SourceLabel
    data_quality: DataQuality


class DailyDemandRecord(ContractModel):
    """One day's peak required simultaneous service places for a service."""

    facility_id: Identifier
    service_id: Identifier
    date: dt.date
    peak_required_places: Places
    source: SourceLabel
    data_quality: DataQuality
    service_status: ServiceStatus = ServiceStatus.OPERATING


class DailyHistoryImport(ContractModel):
    resource_records: list[DailyResourceRecord]
    demand_records: list[DailyDemandRecord]


class DailyHistoryImportResult(ContractModel):
    inserted_resource_records: int
    inserted_demand_records: int
    unchanged_records: int


class ForecastInput(ContractModel):
    """Everything the pure engine receives; built by the backend per request."""

    facility_id: Identifier
    service_id: Identifier
    service_status: ServiceStatus
    requirement: ServiceRequirement | None
    resource_records: list[DailyResourceRecord]  # this facility, by (date, resource_id)
    demand_records: list[DailyDemandRecord]  # this facility and service, by date
    generated_at: AwareDatetime
    horizon_days: Literal[7] = HORIZON_DAYS


# Response.


class HistoryDay(ContractModel):
    date: dt.date
    capacity: Places | None  # null when a required resource is missing that day
    demand: Places | None  # null when no demand record exists that day
    sources: list[SourceLabel]
    data_quality: DataQuality | None  # lowest quality among that day's used records

    @model_validator(mode="after")
    def sorted_sources(self) -> Self:
        if self.sources != sorted(set(self.sources)):
            raise ValueError("sources must be sorted and unique.")
        return self


class ForecastDay(ContractModel):
    date: dt.date
    predicted_capacity: PredictedPlaces
    predicted_demand: PredictedPlaces
    capacity_lower: PredictedPlaces
    capacity_upper: PredictedPlaces
    demand_lower: PredictedPlaces
    demand_upper: PredictedPlaces
    expected_gap: PredictedPlaces

    @model_validator(mode="after")
    def consistent_day(self) -> Self:
        if not self.capacity_lower <= self.predicted_capacity <= self.capacity_upper:
            raise ValueError("predicted_capacity must lie within its uncertainty range.")
        if not self.demand_lower <= self.predicted_demand <= self.demand_upper:
            raise ValueError("predicted_demand must lie within its uncertainty range.")
        gap = max(0.0, self.predicted_demand - self.predicted_capacity)
        if abs(self.expected_gap - gap) > _EPSILON:
            raise ValueError("expected_gap must equal max(0, demand - capacity).")
        return self


class ForecastAlert(ContractModel):
    """A predicted gap; not a calibrated shortage probability."""

    date: dt.date
    code: Literal["predicted_gap"]
    expected_gap: PredictedPlaces
    message: str = Field(min_length=1, max_length=500)


class ForecastValidation(ContractModel):
    """Error on withheld historical days, in simultaneous service places."""

    method: str = Field(min_length=1, max_length=100)
    holdout_days: int = Field(gt=0)
    evaluated_from: dt.date
    evaluated_to: dt.date
    capacity_mae: PredictedPlaces | None
    demand_mae: PredictedPlaces | None

    @model_validator(mode="after")
    def ordered_window(self) -> Self:
        if self.evaluated_from > self.evaluated_to:
            raise ValueError("evaluated_from must not be after evaluated_to.")
        return self


class FacilityForecastResponse(ContractModel):
    facility_id: Identifier
    service_id: Identifier
    generated_at: AwareDatetime
    horizon_days: Literal[7]
    capacity_unit: CapacityUnit
    profile_version: str | None = Field(min_length=1, max_length=64)
    status: ForecastStatus
    history: list[HistoryDay]
    forecast: list[ForecastDay]
    alerts: list[ForecastAlert]
    validation: ForecastValidation | None

    @model_validator(mode="after")
    def consistent_forecast(self) -> Self:
        _require_ascending_unique([day.date for day in self.history], "history")
        _require_ascending_unique([day.date for day in self.forecast], "forecast")
        _require_ascending_unique([alert.date for alert in self.alerts], "alerts")
        if self.history and self.forecast and self.forecast[0].date <= self.history[-1].date:
            raise ValueError("forecast must start after the last history day.")
        dates = [day.date for day in self.forecast]
        if any(b - a != dt.timedelta(days=1) for a, b in zip(dates, dates[1:])):
            raise ValueError("forecast days must be consecutive.")

        if self.status == ForecastStatus.FORECASTED:
            if len(self.forecast) != self.horizon_days or self.validation is None:
                raise ValueError("A forecast needs horizon_days days and validation results.")
        elif self.forecast or self.alerts:
            raise ValueError(f"A {self.status} result has no forecast or alerts.")
        if (self.profile_version is None) != (self.status == ForecastStatus.NOT_CONFIGURED):
            raise ValueError("profile_version is null exactly when no profile exists.")

        gaps = {day.date: day.expected_gap for day in self.forecast if day.expected_gap > 0}
        alerted = {alert.date: alert.expected_gap for alert in self.alerts}
        if alerted.keys() != gaps.keys() or any(
            abs(alerted[d] - gaps[d]) > _EPSILON for d in gaps
        ):
            raise ValueError("Exactly the forecast days with a gap must have a matching alert.")
        return self
