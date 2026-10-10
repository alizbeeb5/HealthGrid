"""Shared Feature 3 contract. Owner: backend/data. See docs/feature-3-contract.md.

Rows reuse Feature 1 Facility and Feature 2 ServiceCapacityResult unchanged.
Summaries (counts, subtotals) are display rules computed by the frontend helper.
"""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from app.modules.capacity.schemas import CapacityUnit, ServiceCapacityResult
from app.modules.facilities.schemas import ContractModel, Facility, Identifier


class NetworkService(ContractModel):
    service_id: Identifier
    name: str = Field(min_length=1, max_length=200)


class NetworkServiceListResponse(ContractModel):
    """Services offered by at least one facility, ordered by service_id."""

    items: list[NetworkService]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        ids = [item.service_id for item in self.items]
        if ids != sorted(set(ids)):
            raise ValueError("items must be sorted by unique service_id.")
        return self


class NetworkFacilityResult(ContractModel):
    facility: Facility
    capacity: ServiceCapacityResult


class NetworkOverviewResponse(ContractModel):
    service_id: Identifier
    service_name: str | None = Field(min_length=1, max_length=200)
    as_of: AwareDatetime
    stale_after_hours: int = Field(gt=0)
    calculation_scope: Literal["single_service"]
    capacity_unit: CapacityUnit
    facilities: list[NetworkFacilityResult]

    @model_validator(mode="after")
    def consistent_rows(self) -> Self:
        ids = [row.facility.facility_id for row in self.facilities]
        if ids != sorted(set(ids)):
            raise ValueError("facilities must be sorted by unique facility_id.")
        if any(row.capacity.service_id != self.service_id for row in self.facilities):
            raise ValueError("Every row must be for the requested service; never mix services.")
        if self.service_name is None and self.facilities:
            raise ValueError("An unknown service has no facilities.")
        return self
