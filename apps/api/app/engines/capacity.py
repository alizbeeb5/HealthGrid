"""Deterministic single-service estimates from snapshots and explicit demo rules.

No I/O, system clock, persistence, HTTP or AI calls belong here. Validate the full
profile collection against the resource catalog at application startup.
"""

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Sequence

from app.modules.facilities.schemas import (
    FacilityService,
    FacilitySnapshotResponse,
    ResourceDefinition,
)

if TYPE_CHECKING:
    from app.modules.capacity.schemas import ServiceCapacityResult, ServiceRequirement


CAPACITY_UNIT = "simultaneous_service_place"


def _positive_ratio(value: object) -> Decimal:
    try:
        if isinstance(value, bool):
            raise ValueError("Requirement ratios must be finite and strictly positive.")
        ratio = Decimal(str(value))
    except (InvalidOperation, TypeError) as error:
        raise ValueError("Requirement ratios must be finite and strictly positive.") from error
    if not ratio.is_finite() or ratio <= 0:
        raise ValueError("Requirement ratios must be finite and strictly positive.")
    return ratio


def _validate_profile(profile: "ServiceRequirement") -> None:
    if not profile.profile_version or not profile.profile_version.strip():
        raise ValueError("A requirement profile must have an explicit version.")
    if profile.capacity_unit != CAPACITY_UNIT:
        raise ValueError(f"Capacity unit must be {CAPACITY_UNIT}.")
    if not profile.requirements:
        raise ValueError("A requirement profile must contain at least one resource.")
    seen = set()
    for requirement in profile.requirements:
        if requirement.resource_id in seen:
            raise ValueError(f"Duplicate required resource: {requirement.resource_id}.")
        seen.add(requirement.resource_id)
        _positive_ratio(requirement.required_per_capacity_unit)


def validate_requirement_profiles(
    profiles: Sequence["ServiceRequirement"],
    catalog: Sequence[ResourceDefinition],
) -> None:
    """Reject invalid configuration before requests; this does not load files.

    The backend loads the runtime JSON as ServiceRequirement models and passes
    all configured profiles and the complete authoritative resource catalog here.
    A resource absent from one snapshot is not necessarily absent from the catalog.
    """
    definitions = {resource.resource_id: resource for resource in catalog}
    if len(definitions) != len(catalog):
        raise ValueError("Resource catalog contains duplicate IDs.")
    seen = set()
    for profile in profiles:
        _validate_profile(profile)
        if profile.service_id in seen:
            raise ValueError(f"Duplicate service profile: {profile.service_id}.")
        seen.add(profile.service_id)
        for requirement in profile.requirements:
            definition = definitions.get(requirement.resource_id)
            if definition is None:
                raise ValueError(f"Unknown required resource: {requirement.resource_id}.")
            if requirement.unit != definition.unit:
                raise ValueError(f"Unit mismatch for resource {requirement.resource_id}.")


def _capacity_limit(quantity: float, ratio: Decimal) -> int:
    available = Decimal(str(quantity))
    if not available.is_finite() or available < 0:
        raise ValueError("Available quantities must be finite and nonnegative.")
    # Exact decimal ratios represented as integers avoid both binary floating
    # point undercounts (0.3 / 0.1) and Decimal context rounding near integers.
    numerator, denominator = available.as_integer_ratio()
    ratio_numerator, ratio_denominator = ratio.as_integer_ratio()
    return (numerator * ratio_denominator) // (denominator * ratio_numerator)


def calculate_service_capacity(
    snapshot: FacilitySnapshotResponse,
    service: FacilityService,
    requirement: "ServiceRequirement | None",
) -> "ServiceCapacityResult":
    """Calculate one service in isolation; never sum results across services.

    Freshness is supplied by the Feature 1 snapshot, evaluated at its as_of.
    Preserve its reported quantities and provenance even for stale inputs.
    """
    from app.modules.capacity.schemas import ResourceCapacityLimit, ServiceCapacityResult

    if service.facility_id != snapshot.facility.facility_id or service not in snapshot.services:
        raise ValueError("The supplied service must belong to the snapshot.")
    if requirement is not None:
        if requirement.service_id != service.service_id:
            raise ValueError("The requirement profile must match the supplied service.")
        _validate_profile(requirement)

    resources = {resource.resource_id: resource for resource in snapshot.resources}
    if len(resources) != len(snapshot.resources):
        raise ValueError("Snapshot contains duplicate resource IDs.")
    reasons = set()
    limits = []
    if service.status == "unavailable":
        reasons.add("service_unavailable")
    if service.status == "limited":
        reasons.add("service_restriction_unquantified")
    if requirement is None:
        reasons.add("requirements_not_configured")
    else:
        for rule in sorted(requirement.requirements, key=lambda row: row.resource_id):
            resource = resources.get(rule.resource_id)
            if resource is not None and resource.unit != rule.unit:
                raise ValueError(f"Unit mismatch for resource {rule.resource_id}.")
            data_status = resource.data_status if resource is not None else "unknown"
            if data_status == "unknown":
                reasons.add("missing_required_observation")
            elif data_status == "stale":
                reasons.add("stale_required_observation")
            capacity_limit = None
            if data_status == "current":
                if resource.available_quantity is None:
                    raise ValueError("A current observation must have an available quantity.")
                capacity_limit = _capacity_limit(
                    resource.available_quantity, _positive_ratio(rule.required_per_capacity_unit)
                )
            limits.append(ResourceCapacityLimit(
                resource_id=rule.resource_id,
                unit=rule.unit,
                required_per_capacity_unit=rule.required_per_capacity_unit,
                available_quantity=resource.available_quantity if resource is not None else None,
                capacity_limit=capacity_limit,
                data_status=data_status,
                observation_id=resource.observation_id if resource is not None else None,
                observed_at=resource.observed_at if resource is not None else None,
            ))

    estimate = None
    bottlenecks = []
    if service.status == "unavailable":
        status, estimate = "unavailable", 0
    elif requirement is None:
        status = "not_configured"
    elif reasons:
        status = "unknown"
    else:
        status = "calculated"
        estimate = min(row.capacity_limit for row in limits)
        bottlenecks = sorted(row.resource_id for row in limits if row.capacity_limit == estimate)
    return ServiceCapacityResult(
        service_id=service.service_id,
        service_status=service.status,
        profile_version=requirement.profile_version if requirement is not None else None,
        capacity_unit=CAPACITY_UNIT,
        status=status,
        estimated_capacity=estimate,
        bottleneck_resource_ids=bottlenecks,
        resource_limits=limits,
        reason_codes=sorted(reasons),
    )
