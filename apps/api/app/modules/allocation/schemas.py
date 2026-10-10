"""Shared Feature 6 allocation contract. Owner: backend/data (engine owner reviews
numerical fields). See docs/feature-6-contract.md.

The engine interface is `optimize_allocation(AllocationEngineInput) ->
AllocationEngineResult` in engines/allocation.py; it imports these types rather than
redefining them. Results are proposals for human review, never dispatch decisions.
"""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.modules.capacity.schemas import CapacityUnit, ServiceRequirement
from app.modules.facilities.schemas import (
    ContractModel,
    FacilitySnapshotResponse,
    Identifier,
    ResourceUnit,
    ServiceStatus,
)
from app.modules.scenarios.schemas import AppliedOverride

SCHEMA_VERSION = 1
DEFAULT_TIME_LIMIT_SECONDS = 5.0
Count = Annotated[int, Field(ge=0, strict=True)]
PositiveCount = Annotated[int, Field(gt=0, strict=True)]
SourceNote = Annotated[str, Field(min_length=1, max_length=500)]


class SolverStatus(StrEnum):
    NOT_RUN = "not_run"
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"  # a valid incumbent without an optimality proof
    INFEASIBLE = "infeasible"
    UNKNOWN = "unknown"  # no solution or proof within limits; not proven infeasible


class PlanOutcome(StrEnum):
    NEEDS_INPUTS = "needs_inputs"
    IMPROVED = "improved"
    NO_IMPROVEMENT = "no_improvement"
    NO_SOLUTION = "no_solution"


class ExclusionReason(StrEnum):
    NO_PLANNING_CONSTRAINTS = "no_planning_constraints"
    SERVICE_UNAVAILABLE = "service_unavailable"
    SERVICE_LIMITED = "service_limited"
    REQUIREMENTS_NOT_CONFIGURED = "requirements_not_configured"
    MISSING_REQUIRED_EVIDENCE = "missing_required_evidence"
    STALE_REQUIRED_EVIDENCE = "stale_required_evidence"


# Request.


class FacilityConstraint(ContractModel):
    """Planner-confirmed limits for one facility. transferable_quantity is explicitly
    approved movable inventory, not all reported equipment."""

    facility_id: Identifier
    required_service_places: Count
    minimum_retained_service_places: Count
    minimum_retained_resource_quantity: Count
    transferable_quantity: Count
    maximum_inbound_quantity: Count
    source_note: SourceNote
    confirmed_at: AwareDatetime


class RouteConstraint(ContractModel):
    """An explicitly approved directed route; coordinates never imply one."""

    route_id: Identifier
    from_facility_id: Identifier
    to_facility_id: Identifier
    lead_time_minutes: Count
    cost_per_unit_minor_units: Count
    maximum_quantity: PositiveCount
    source_note: SourceNote
    confirmed_at: AwareDatetime

    @model_validator(mode="after")
    def not_self(self) -> Self:
        if self.from_facility_id == self.to_facility_id:
            raise ValueError("A route cannot start and end at the same facility.")
        return self


class AllocationRunRequest(ContractModel):
    simulation_run_id: Identifier
    resource_id: Literal["working-monitors"]  # first milestone
    planning_horizon_minutes: PositiveCount
    budget_minor_units: Count  # USD cents
    currency: Literal["USD"]
    facility_constraints: list[FacilityConstraint]
    routes: list[RouteConstraint]
    assumptions: list[SourceNote]

    @field_validator("facility_constraints")
    @classmethod
    def unique_facilities(cls, value: list[FacilityConstraint]) -> list[FacilityConstraint]:
        ids = [c.facility_id for c in value]
        if len(ids) != len(set(ids)):
            raise ValueError("One constraint per facility.")
        return value

    @field_validator("routes")
    @classmethod
    def unique_routes(cls, value: list[RouteConstraint]) -> list[RouteConstraint]:
        if len({r.route_id for r in value}) != len(value):
            raise ValueError("route_id values must be unique.")
        if len({(r.from_facility_id, r.to_facility_id) for r in value}) != len(value):
            raise ValueError("Only one route per directed facility pair.")
        return value


class SolverSettings(ContractModel):
    time_limit_seconds: float = Field(gt=0, le=60)  # total across sequential solves
    objective_order: list[str]


DEFAULT_SOLVER_SETTINGS = SolverSettings(
    time_limit_seconds=DEFAULT_TIME_LIMIT_SECONDS,
    objective_order=["minimize_unmet_demand", "minimize_transfer_cost", "minimize_moved_items"],
)


# Engine interface.


class AllocationFacilityInput(ContractModel):
    """Effective scenario snapshot plus the planner's constraint (null if none given)."""

    snapshot: FacilitySnapshotResponse
    applied_overrides: list[AppliedOverride]
    constraint: FacilityConstraint | None


class AllocationEngineInput(ContractModel):
    service_id: Identifier
    resource_id: Identifier
    unit: ResourceUnit
    capacity_unit: CapacityUnit
    requirement: ServiceRequirement | None  # frozen profile for the service
    facilities: list[AllocationFacilityInput]  # all baseline facilities, by facility_id
    routes: list[RouteConstraint]
    planning_horizon_minutes: PositiveCount
    budget_minor_units: Count
    currency: Literal["USD"]
    solver_settings: SolverSettings


class FacilityExclusion(ContractModel):
    facility_id: Identifier
    reasons: list[ExclusionReason] = Field(min_length=1)


class Coverage(ContractModel):
    included_facility_ids: list[Identifier]
    excluded: list[FacilityExclusion]

    @model_validator(mode="after")
    def disjoint_sorted(self) -> Self:
        excluded = [e.facility_id for e in self.excluded]
        if self.included_facility_ids != sorted(set(self.included_facility_ids)):
            raise ValueError("included_facility_ids must be sorted and unique.")
        if excluded != sorted(set(excluded)) or set(excluded) & set(self.included_facility_ids):
            raise ValueError("Excluded facilities are sorted, unique and not included.")
        return self


class FacilityPlanRow(ContractModel):
    facility_id: Identifier
    service_status: ServiceStatus
    required_service_places: Count
    resource_quantity: Count | None  # the planned resource after transfers
    estimated_capacity: Count | None
    covered_service_places: Count | None
    unmet_service_places: Count | None
    bottleneck_resource_ids: list[Identifier]

    @model_validator(mode="after")
    def consistent_coverage(self) -> Self:
        if self.estimated_capacity is None:
            if self.covered_service_places is not None or self.unmet_service_places is not None:
                raise ValueError("Unknown capacity has unknown coverage.")
            return self
        covered = min(self.estimated_capacity, self.required_service_places)
        if (self.covered_service_places, self.unmet_service_places) != (
            covered, self.required_service_places - covered
        ):
            raise ValueError("covered = min(capacity, required); unmet = required - covered.")
        return self


class PlanSummary(ContractModel):
    """Totals over included facilities only; excluded demand is not counted as zero."""

    included_facility_ids: list[Identifier]
    required_service_places: Count
    covered_service_places: Count
    unmet_service_places: Count
    rows: list[FacilityPlanRow]

    @model_validator(mode="after")
    def totals(self) -> Self:
        ids = [row.facility_id for row in self.rows]
        if ids != self.included_facility_ids or ids != sorted(set(ids)):
            raise ValueError("One row per included facility, ordered by facility_id.")
        if any(row.estimated_capacity is None for row in self.rows):
            raise ValueError("Included facilities have known capacity.")
        sums = (
            sum(r.required_service_places for r in self.rows),
            sum(r.covered_service_places for r in self.rows),
            sum(r.unmet_service_places for r in self.rows),
        )
        if sums != (self.required_service_places, self.covered_service_places,
                    self.unmet_service_places):
            raise ValueError("Summary totals must equal the sum of rows.")
        return self


class Transfer(ContractModel):
    route_id: Identifier
    from_facility_id: Identifier
    to_facility_id: Identifier
    resource_id: Identifier
    quantity: PositiveCount
    unit: ResourceUnit
    lead_time_minutes: Count
    cost_minor_units: Count  # quantity * route cost per unit


class AllocationEngineResult(ContractModel):
    engine_version: str = Field(min_length=1, max_length=64)
    solver_version: str = Field(min_length=1, max_length=64)
    solver_status: SolverStatus
    plan_outcome: PlanOutcome
    coverage: Coverage
    baseline_summary: PlanSummary
    proposed_summary: PlanSummary | None
    transfers: list[Transfer]
    total_cost_minor_units: Count
    remaining_gap_reasons: list[SourceNote]
    validation_passed: bool
    review_required: Literal[True]
    objective_description: str = Field(min_length=1, max_length=500)
    solve_duration_ms: Count

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        status, outcome, proposed = self.solver_status, self.plan_outcome, self.proposed_summary
        if status == SolverStatus.NOT_RUN and outcome != PlanOutcome.NEEDS_INPUTS:
            raise ValueError("A plan that was not solved needs inputs.")
        if outcome == PlanOutcome.NEEDS_INPUTS and status != SolverStatus.NOT_RUN:
            raise ValueError("needs_inputs means the solver did not run.")
        has_plan = status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
        if has_plan != (proposed is not None):
            raise ValueError("Only optimal/feasible results have a proposed summary.")
        if not has_plan and status != SolverStatus.NOT_RUN and outcome != PlanOutcome.NO_SOLUTION:
            raise ValueError("Infeasible/unknown results have no solution.")
        if proposed is not None:
            if not self.validation_passed:
                raise ValueError("Never publish a proposal that failed validation.")
            if proposed.included_facility_ids != self.baseline_summary.included_facility_ids:
                raise ValueError("Baseline and proposal cover the same facilities.")
            baseline_covered = self.baseline_summary.covered_service_places
            improved = proposed.covered_service_places > baseline_covered
            expected = PlanOutcome.IMPROVED if improved else PlanOutcome.NO_IMPROVEMENT
            if outcome != expected:
                raise ValueError(f"plan_outcome must be {expected} for this proposal.")
        elif self.transfers:
            raise ValueError("Transfers exist only with a proposed plan.")
        if self.baseline_summary.included_facility_ids != self.coverage.included_facility_ids:
            raise ValueError("Summaries cover exactly the included facilities.")
        if self.total_cost_minor_units != sum(t.cost_minor_units for t in self.transfers):
            raise ValueError("total_cost_minor_units is the sum of transfer costs.")
        return self


# Saved run.


class AllocationRun(AllocationEngineResult):
    """Saved proposal. Reopening returns this record; it is never re-solved."""

    allocation_run_id: Identifier
    simulation_run_id: Identifier
    incident_id: Identifier
    revision_id: Identifier
    baseline_id: Identifier
    created_at: AwareDatetime
    schema_version: Literal[1]
    input: AllocationRunRequest
    solver_settings: SolverSettings


class PostAllocationFacility(ContractModel):
    """A facility after the proposal's transfers; demand is null when excluded."""

    snapshot: FacilitySnapshotResponse
    required_service_places: Count | None


class PostAllocationState(ContractModel):
    """Public allocation contract for later planning (Feature 7): a saved proposal's
    frozen scenario with its transfers reapplied once and verified against the saved
    proposed summary. Never built from live observations."""

    allocation_run_id: Identifier
    simulation_run_id: Identifier
    incident_id: Identifier
    revision_id: Identifier
    baseline_id: Identifier
    service_id: Identifier
    incident_starts_at: AwareDatetime
    allocation_horizon_minutes: PositiveCount
    requirement: ServiceRequirement
    facilities: list[PostAllocationFacility]
    included_facility_ids: list[Identifier]
    excluded_facilities: list[FacilityExclusion]
    transfers: list[Transfer]


AllocationErrorCode = Literal["invalid_request", "simulation_run_not_found",
                              "allocation_run_not_found"]
