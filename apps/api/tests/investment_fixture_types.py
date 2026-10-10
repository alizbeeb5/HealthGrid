"""Internal kernel fixtures only; backend owns InvestmentEngineInput/Result."""

from dataclasses import dataclass
from datetime import datetime

from app.modules.capacity.schemas import ServiceRequirement
from app.modules.facilities.schemas import FacilitySnapshotResponse


@dataclass(frozen=True)
class Effect:
    resource_id: str
    quantity_delta: int
    unit: str


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    name: str
    facility_id: str
    service_id: str
    capital_cost_minor_units: int
    monthly_operating_cost_minor_units: int
    implementation_days: int
    resource_effects: tuple[Effect, ...]
    requires_candidate_ids: tuple[str, ...]
    exclusive_group_id: str | None
    source_note: str | None
    confirmed_at: datetime | None


@dataclass(frozen=True)
class Exclusion:
    facility_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class SolverSettings:
    time_limit_seconds: float = 5
    random_seed: int = 0
    num_search_workers: int = 1


@dataclass(frozen=True)
class Problem:
    service_id: str
    capacity_unit: str
    currency: str
    snapshots: tuple[FacilitySnapshotResponse, ...]
    requirement_profiles: tuple[ServiceRequirement, ...]
    required_service_places: dict[str, int | None]
    included_facility_ids: tuple[str, ...]
    excluded_facilities: tuple[Exclusion, ...]
    candidates: tuple[Candidate, ...]
    planning_starts_at: datetime
    evaluation_at: datetime
    operating_cost_months: int
    budget_minor_units: int
    solver_settings: SolverSettings
