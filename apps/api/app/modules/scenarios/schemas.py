"""Shared Feature 5 incident and simulation contract. Owner: backend/data.

See docs/feature-5-contract.md. Per-field rules live here; cross-field and catalog
rules (override pairs, affected facilities, units, applicability) are checked by
scenarios.service.validate_incident so errors carry exact field paths. Scenario
values are planner assumptions; they never become reported observations.
"""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.modules.capacity.schemas import (
    CapacityUnit,
    ServiceCapacityResult,
    ServiceRequirement,
)
from app.modules.facilities.schemas import (
    ContractModel,
    DataStatus,
    Facility,
    FacilitySnapshotResponse,
    FieldError,
    Identifier,
    Quantity,
    ResourceUnit,
    ServiceStatus,
)

SCHEMA_VERSION = 1
Note = Annotated[str, Field(min_length=1, max_length=500)]


class RevisionStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


# Incident input.


class ServiceOverride(ContractModel):
    facility_id: Identifier
    service_id: Identifier
    status: ServiceStatus
    restriction_note: Note | None

    @model_validator(mode="after")
    def limited_needs_note(self) -> Self:
        if self.status == ServiceStatus.LIMITED and self.restriction_note is None:
            raise ValueError("A limited service needs a restriction_note.")
        return self


class ResourceOverride(ContractModel):
    """Absolute scenario availability, not a loss to subtract. Zero is explicit zero."""

    facility_id: Identifier
    resource_id: Identifier
    available_quantity: Quantity
    unit: ResourceUnit


class IncidentDraftInput(ContractModel):
    title: str = Field(min_length=1, max_length=200)
    report_text: str | None = Field(max_length=10_000)
    service_id: Identifier | None
    starts_at: AwareDatetime | None
    expected_ends_at: AwareDatetime | None
    affected_facility_ids: list[Identifier]
    service_overrides: list[ServiceOverride]
    resource_overrides: list[ResourceOverride]
    assumptions: list[Note]

    @field_validator("affected_facility_ids")
    @classmethod
    def sorted_unique(cls, value: list[str]) -> list[str]:
        if value != sorted(set(value)):
            raise ValueError("affected_facility_ids must be sorted and unique.")
        return value


class IncidentInput(IncidentDraftInput):
    """Confirmed input: same shape, with the selection and start time required."""

    service_id: Identifier
    starts_at: AwareDatetime
    affected_facility_ids: list[Identifier] = Field(min_length=1)


class IncidentConfirmRequest(ContractModel):
    draft_revision_id: Identifier
    input: IncidentInput
    confirmed_by: str = Field(min_length=1, max_length=100)  # demo display name only


# Revisions and baseline.


class IncidentRevision(ContractModel):
    incident_id: Identifier
    revision_id: Identifier
    parent_revision_id: Identifier | None
    status: RevisionStatus
    input: IncidentDraftInput
    created_at: AwareDatetime
    confirmed_at: AwareDatetime | None
    confirmed_by: str | None
    baseline_id: Identifier | None

    @model_validator(mode="after")
    def confirmation_fields(self) -> Self:
        confirmed = (self.confirmed_at, self.confirmed_by, self.baseline_id)
        if self.status == RevisionStatus.DRAFT and any(v is not None for v in confirmed):
            raise ValueError("A draft has no confirmation fields.")
        if self.status == RevisionStatus.CONFIRMED and any(v is None for v in confirmed):
            raise ValueError("A confirmed revision needs confirmed_at, confirmed_by, baseline_id.")
        return self


class IncidentListResponse(ContractModel):
    items: list[IncidentRevision]


class IncidentBaseline(ContractModel):
    """Reports and profiles captured once at confirmation; never modified."""

    baseline_id: Identifier
    captured_at: AwareDatetime
    service_id: Identifier
    facility_snapshots: list[FacilitySnapshotResponse]
    requirement_profiles: list[ServiceRequirement]
    schema_version: Literal[1]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        ids = [s.facility.facility_id for s in self.facility_snapshots]
        if ids != sorted(set(ids)):
            raise ValueError("facility_snapshots must be ordered by unique facility_id.")
        if any(s.as_of != self.captured_at for s in self.facility_snapshots):
            raise ValueError("All snapshots share the baseline captured_at.")
        return self


# Impact and saved runs.


class AppliedServiceOverride(ContractModel):
    override_type: Literal["service_status"]
    service_id: Identifier
    baseline_status: ServiceStatus
    scenario_status: ServiceStatus
    restriction_note: Note | None


class AppliedResourceOverride(ContractModel):
    """Scenario quantity is a planner assumption, not a reported observation."""

    override_type: Literal["resource_quantity"]
    resource_id: Identifier
    unit: ResourceUnit
    baseline_quantity: Quantity | None
    baseline_data_status: DataStatus
    scenario_quantity: Quantity
    affects_modeled_estimate: bool  # false when outside the requirement profile


AppliedOverride = Annotated[
    AppliedServiceOverride | AppliedResourceOverride, Field(discriminator="override_type")
]


class ImpactRow(ContractModel):
    facility: Facility
    baseline_capacity: ServiceCapacityResult
    scenario_capacity: ServiceCapacityResult
    capacity_change: int | None
    affected: bool
    applied_overrides: list[AppliedOverride]

    @model_validator(mode="after")
    def consistent_change(self) -> Self:
        before = self.baseline_capacity.estimated_capacity
        after = self.scenario_capacity.estimated_capacity
        expected = after - before if before is not None and after is not None else None
        if self.capacity_change != expected:
            raise ValueError("capacity_change is scenario minus baseline only when both known.")
        if self.applied_overrides and not self.affected:
            raise ValueError("Only affected facilities have applied overrides.")
        if not self.affected and self.scenario_capacity != self.baseline_capacity:
            raise ValueError("Unaffected rows keep the baseline result.")
        return self


class IncidentImpact(ContractModel):
    incident_id: Identifier
    revision_id: Identifier
    baseline_id: Identifier
    baseline_captured_at: AwareDatetime
    service_id: Identifier
    capacity_unit: CapacityUnit
    rows: list[ImpactRow]

    @model_validator(mode="after")
    def ordered_single_service(self) -> Self:
        ids = [row.facility.facility_id for row in self.rows]
        if ids != sorted(set(ids)):
            raise ValueError("rows must be ordered by unique facility_id.")
        for row in self.rows:
            services = {row.baseline_capacity.service_id, row.scenario_capacity.service_id}
            if services != {self.service_id}:
                raise ValueError("Every row must be for the incident's service.")
        return self


class SimulationRun(ContractModel):
    run_id: Identifier
    created_at: AwareDatetime
    engine_version: str = Field(min_length=1, max_length=64)
    schema_version: Literal[1]
    impact: IncidentImpact


class EffectiveFacility(ContractModel):
    """One facility under the saved scenario: overrides applied to its frozen snapshot."""

    snapshot: FacilitySnapshotResponse
    affected: bool
    applied_overrides: list[AppliedOverride]
    scenario_capacity: ServiceCapacityResult


class EffectiveScenario(ContractModel):
    """Frozen allocation input from a saved run; never reads live observations."""

    run_id: Identifier
    incident_id: Identifier
    revision_id: Identifier
    baseline_id: Identifier
    baseline_captured_at: AwareDatetime
    planning_starts_at: AwareDatetime
    service_id: Identifier
    requirement_profiles: list[ServiceRequirement]
    facilities: list[EffectiveFacility]


# Errors: same envelope shape as Feature 1, scenarios-owned codes.

ScenarioErrorCode = Literal[
    "invalid_request",
    "incident_not_found",
    "revision_not_found",
    "run_not_found",
    "revision_conflict",
    "incident_not_confirmed",
]


class ScenarioErrorDetail(ContractModel):
    code: ScenarioErrorCode
    message: str
    fields: list[FieldError]
    existing_revision_id: Identifier | None  # set on 409 when a revision already exists


class ScenarioErrorResponse(ContractModel):
    error: ScenarioErrorDetail
