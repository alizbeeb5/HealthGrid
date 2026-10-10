"""Facility capacity use case: one Feature 1 snapshot -> pure engine per service."""

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.engines import capacity as capacity_engine
from app.modules.capacity.schemas import (
    FacilityCapacityResponse,
    ServiceCapacityResult,
    ServiceRequirement,
)
from app.modules.facilities import service as facilities
from app.modules.facilities.schemas import ResourceDefinition

# Runtime copy of contracts/examples/feature-2/service-requirement.json, maintained
# by the data/calculation owner. Fictional demo rules, not clinical standards.
PROFILES_PATH = (
    Path(__file__).resolve().parents[5]
    / "data"
    / "synthetic"
    / "feature-2"
    / "service-requirements.json"
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


def _validate_against_catalog(
    profiles: tuple[ServiceRequirement, ...], catalog: list[ResourceDefinition]
) -> dict[str, ServiceRequirement]:
    service_ids = [profile.service_id for profile in profiles]
    if len(service_ids) != len(set(service_ids)):
        raise CapacityConfigurationError("Capacity profiles must have unique service IDs.")
    units = {resource.resource_id: resource.unit for resource in catalog}
    for profile in profiles:
        for requirement in profile.requirements:
            expected = units.get(requirement.resource_id)
            if expected is None:
                raise CapacityConfigurationError(
                    f"Profile {profile.service_id} requires unknown resource "
                    f"{requirement.resource_id}."
                )
            if requirement.unit != expected:
                raise CapacityConfigurationError(
                    f"Profile {profile.service_id} uses {requirement.unit} for "
                    f"{requirement.resource_id}; the catalog unit is {expected}."
                )
    return {profile.service_id: profile for profile in profiles}


def get_profiles(db: Session) -> dict[str, ServiceRequirement]:
    return _validate_against_catalog(
        _load_profiles(PROFILES_PATH), facilities.list_resource_definitions(db)
    )


def get_facility_capacity(db: Session, facility_id: str, now: datetime) -> FacilityCapacityResponse:
    snapshot = facilities.get_snapshot(db, facility_id, now)  # raises FacilityNotFound
    profiles = get_profiles(db)
    calculate = getattr(capacity_engine, "calculate_service_capacity", None)
    if calculate is None:
        raise CapacityConfigurationError("engines.capacity.calculate_service_capacity is missing.")

    results: list[ServiceCapacityResult] = []
    for service in sorted(snapshot.services, key=lambda s: s.service_id):
        result = calculate(snapshot, service, profiles.get(service.service_id))
        if result.service_id != service.service_id:
            raise CapacityConfigurationError(
                f"Engine returned {result.service_id} for service {service.service_id}."
            )
        results.append(result)

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
