"""Shared Feature 1 contract. Domain endpoints are not implemented yet."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

Identifier = Annotated[
    str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
]
Quantity = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServiceStatus(StrEnum):
    OPERATING = "operating"
    LIMITED = "limited"
    UNAVAILABLE = "unavailable"


class ResourceCategory(StrEnum):
    BEDS = "beds"
    STAFF = "staff"
    EQUIPMENT = "equipment"
    SUPPLIES = "supplies"
    INFRASTRUCTURE = "infrastructure"


class ResourceUnit(StrEnum):
    BED = "bed"
    PERSON = "person"
    ITEM = "item"
    LITER = "liter"


class DataStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


class Facility(ContractModel):
    facility_id: Identifier
    name: str = Field(min_length=1, max_length=200)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    last_reported_at: AwareDatetime | None


class FacilityListResponse(ContractModel):
    items: list[Facility]


class FacilityService(ContractModel):
    facility_id: Identifier
    service_id: Identifier
    name: str = Field(min_length=1, max_length=200)
    status: ServiceStatus


class ResourceDefinition(ContractModel):
    resource_id: Identifier
    name: str = Field(min_length=1, max_length=200)
    category: ResourceCategory
    unit: ResourceUnit
    allows_fractional: bool


class ResourceSnapshot(ResourceDefinition):
    observation_id: Identifier | None
    available_quantity: Quantity | None
    observed_at: AwareDatetime | None
    recorded_at: AwareDatetime | None
    data_status: DataStatus


class FacilitySnapshotResponse(ContractModel):
    facility: Facility
    services: list[FacilityService]
    resources: list[ResourceSnapshot]
    as_of: AwareDatetime
    stale_after_hours: int = Field(gt=0)


class ObservationCreate(ContractModel):
    resource_id: Identifier
    available_quantity: Quantity
    unit: ResourceUnit
    observed_at: AwareDatetime

    @field_validator("observed_at", mode="before")
    @classmethod
    def require_timestamp_format(cls, value: object) -> object:
        if not isinstance(value, (str, datetime)):
            raise ValueError("Use a timezone-aware ISO 8601 timestamp.")
        return value


class ObservationResponse(ObservationCreate):
    observation_id: Identifier
    facility_id: Identifier
    recorded_at: AwareDatetime


class FieldError(ContractModel):
    field: str
    message: str


class ErrorDetail(ContractModel):
    code: Literal["facility_not_found", "invalid_observation", "invalid_request"]
    message: str
    fields: list[FieldError]


class ErrorResponse(ContractModel):
    error: ErrorDetail
