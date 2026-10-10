"""Internal records for mathematical kernel tests.

Public types live in allocation/schemas.py.

All snapshots/profiles are frozen effective scenario inputs supplied by the backend.
No live data, database IDs or API wire response models are introduced here.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.modules.capacity.schemas import ServiceRequirement
from app.modules.facilities.schemas import FacilitySnapshotResponse


@dataclass(frozen=True)
class FacilityConstraint:
    facility_id: str
    required_service_places: int | None
    minimum_retained_service_places: int | None
    minimum_retained_resource_quantity: int | None
    transferable_quantity: int | None
    maximum_inbound_quantity: int | None
    source_note: str
    confirmed_at: datetime


@dataclass(frozen=True)
class ApprovedRoute:
    route_id: str
    from_facility_id: str
    to_facility_id: str
    lead_time_minutes: int
    cost_per_unit_minor_units: int
    maximum_quantity: int
    source_note: str
    confirmed_at: datetime


@dataclass(frozen=True)
class SolverSettings:
    time_limit_seconds: float = 5.0
    random_seed: int = 0
    num_search_workers: int = 1


@dataclass(frozen=True)
class AllocationEngineInput:
    service_id: str
    resource_id: str
    snapshots: tuple[FacilitySnapshotResponse, ...]
    requirement_profiles: tuple[ServiceRequirement, ...]
    facility_constraints: tuple[FacilityConstraint, ...]
    routes: tuple[ApprovedRoute, ...]
    planning_horizon_minutes: int
    budget_minor_units: int
    currency: Literal["USD"] = "USD"
    solver_settings: SolverSettings = field(default_factory=SolverSettings)
