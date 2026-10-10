"""Facility capacity use case: one Feature 1 snapshot -> pure engine per service."""

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.engines import capacity as capacity_engine
from app.modules.capacity.schemas import (
    FacilityCapacityResponse,
    ServiceCapacityResult,
    ServiceRequirement,
)
from app.modules.facilities import service as facilities
from app.modules.facilities.schemas import FacilityService, FacilitySnapshotResponse

# Runtime copy of contracts/examples/feature-2/service-requirement.json, maintained
# by the data/calculation owner. Fictional demo rules, not clinical standards.
PROFILES_PATH = (
    Path(__file__).resolve().parents[5]
    / "data"
    / "synthetic"
    / "feature-2"
    / "service-requirement.json"
)

_profiles_adapter = TypeAdapter(list[ServiceRequirement])


class CapacityConfigurationError(RuntimeError):
    """Invalid or missing requirement configuration. Served as HTTP 500, never as 0."""


@lru_cache
def _load_profiles(path: Path) -> tuple[ServiceRequirement, ...]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CapacityConfigurationError(f"Cannot read capacity profiles {path}: {exc}") from exc
    try:
        # The file may hold one profile (as in the contract example) or a list.
        profiles = _profiles_adapter.validate_python(raw if isinstance(raw, list) else [raw])
    except ValidationError as exc:
        raise CapacityConfigurationError(f"Invalid capacity profiles {path}: {exc}") from exc
    return tuple(profiles)


def get_profiles(db: Session) -> dict[str, ServiceRequirement]:
    """Load profiles and validate them against the complete resource catalog."""
    path = PROFILES_PATH
    if get_settings().demo_scenario == "beirut":
        path = path.parents[1] / "beirut-explosion" / "service-requirement.json"
    profiles = _load_profiles(path)
    try:
        capacity_engine.validate_requirement_profiles(
            profiles, facilities.list_resource_definitions(db)
        )
    except ValueError as exc:
        raise CapacityConfigurationError(f"Invalid capacity profiles: {exc}") from exc
    return {profile.service_id: profile for profile in profiles}


def calculate_service(
    snapshot: FacilitySnapshotResponse,
    service: FacilityService,
    profiles: dict[str, ServiceRequirement],
) -> ServiceCapacityResult:
    """One service of one snapshot through the engine; profiles from get_profiles."""
    result = capacity_engine.calculate_service_capacity(
        snapshot, service, profiles.get(service.service_id)
    )
    if result.service_id != service.service_id:
        raise CapacityConfigurationError(
            f"Engine returned {result.service_id} for service {service.service_id}."
        )
    return result


def get_facility_capacity(db: Session, facility_id: str, now: datetime) -> FacilityCapacityResponse:
    snapshot = facilities.get_snapshot(db, facility_id, now)  # raises FacilityNotFound
    profiles = get_profiles(db)
    results = [
        calculate_service(snapshot, service, profiles)
        for service in sorted(snapshot.services, key=lambda s: s.service_id)
    ]

    # Revalidate so engine output that breaks contract invariants fails visibly.
    return FacilityCapacityResponse.model_validate(
        {
            "facility_id": snapshot.facility.facility_id,
            "as_of": snapshot.as_of,
            "stale_after_hours": snapshot.stale_after_hours,
            "calculation_scope": "single_service",
            "services": [result.model_dump() for result in results],
        }
    )
