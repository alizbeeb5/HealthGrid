"""Shared Feature 2 contract. Owner: backend/data. See docs/feature-2-contract.md.

Invariants from the contract are enforced here, so an engine result that breaks
them fails visibly instead of being served as a plausible estimate.
"""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from app.modules.facilities.schemas import (
    ContractModel,
    DataStatus,
    Identifier,
    Quantity,
    ResourceUnit,
    ServiceStatus,
)

CapacityUnit = Literal["simultaneous_service_place"]
RequirementRatio = Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)]
CapacityCount = Annotated[int, Field(ge=0, strict=True)]


class CapacityStatus(StrEnum):
    CALCULATED = "calculated"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class ReasonCode(StrEnum):
    SERVICE_UNAVAILABLE = "service_unavailable"
    REQUIREMENTS_NOT_CONFIGURED = "requirements_not_configured"
    SERVICE_RESTRICTION_UNQUANTIFIED = "service_restriction_unquantified"
    MISSING_REQUIRED_OBSERVATION = "missing_required_observation"
    STALE_REQUIRED_OBSERVATION = "stale_required_observation"


def _require_sorted_unique(values: list, name: str) -> None:
    if values != sorted(set(values)):
        raise ValueError(f"{name} must be sorted and unique.")


class ResourceRequirement(ContractModel):
    resource_id: Identifier
    unit: ResourceUnit
    required_per_capacity_unit: RequirementRatio


class ServiceRequirement(ContractModel):
    """Configurable requirement profile; demo values are not clinical standards."""

    service_id: Identifier
    profile_version: str = Field(min_length=1, max_length=64)
    capacity_unit: CapacityUnit
    requirements: list[ResourceRequirement] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_resources(self) -> Self:
        ids = [requirement.resource_id for requirement in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("Each resource may appear only once in a profile.")
        return self


class ResourceCapacityLimit(ContractModel):
    resource_id: Identifier
    unit: ResourceUnit
    required_per_capacity_unit: RequirementRatio
    available_quantity: Quantity | None
    capacity_limit: CapacityCount | None
    data_status: DataStatus
    observation_id: Identifier | None
    observed_at: AwareDatetime | None


class ServiceCapacityResult(ContractModel):
    service_id: Identifier
    service_status: ServiceStatus
    profile_version: str | None = Field(min_length=1, max_length=64)
    capacity_unit: CapacityUnit
    status: CapacityStatus
    estimated_capacity: CapacityCount | None
    bottleneck_resource_ids: list[Identifier]
    resource_limits: list[ResourceCapacityLimit]
    reason_codes: list[ReasonCode]

    @model_validator(mode="after")
    def consistent_result(self) -> Self:
        _require_sorted_unique(self.bottleneck_resource_ids, "bottleneck_resource_ids")
        _require_sorted_unique(self.reason_codes, "reason_codes")
        _require_sorted_unique(
            [limit.resource_id for limit in self.resource_limits], "resource_limits"
        )
        estimate, status = self.estimated_capacity, self.status
        if status == CapacityStatus.CALCULATED:
            if estimate is None or not self.bottleneck_resource_ids:
                raise ValueError("A calculated result needs an estimate and bottlenecks.")
        elif self.bottleneck_resource_ids:
            raise ValueError("Only a calculated result has bottleneck resources.")
        if status == CapacityStatus.UNAVAILABLE and estimate != 0:
            raise ValueError("An unavailable service has an estimate of 0.")
        unresolved = (CapacityStatus.UNKNOWN, CapacityStatus.NOT_CONFIGURED)
        if status in unresolved and estimate is not None:
            raise ValueError(f"A {status} result has a null estimate.")
        # Unavailable takes precedence over a missing profile, so it allows either.
        if status == CapacityStatus.NOT_CONFIGURED and self.profile_version is not None:
            raise ValueError("A not_configured result has no profile_version.")
        if status in (CapacityStatus.CALCULATED, CapacityStatus.UNKNOWN) and (
            self.profile_version is None
        ):
            raise ValueError(f"A {status} result needs a profile_version.")
        if self.profile_version is None and self.resource_limits:
            raise ValueError("A result without a profile has no resource limits.")
        return self


class FacilityCapacityResponse(ContractModel):
    facility_id: Identifier
    as_of: AwareDatetime
    stale_after_hours: int = Field(gt=0)
    calculation_scope: Literal["single_service"]
    services: list[ServiceCapacityResult]

    @model_validator(mode="after")
    def ordered_services(self) -> Self:
        _require_sorted_unique([service.service_id for service in self.services], "services")
        return self
