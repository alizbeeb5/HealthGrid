"""Allocation runs: frozen scenario -> validated constraints -> engine -> checked, saved."""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.engines import allocation as allocation_engine
from app.engines.capacity import calculate_service_capacity
from app.modules.allocation import models, repository
from app.modules.allocation.errors import AllocationError
from app.modules.allocation.schemas import (
    DEFAULT_SOLVER_SETTINGS,
    SCHEMA_VERSION,
    AllocationEngineInput,
    AllocationEngineResult,
    AllocationFacilityInput,
    AllocationRun,
    AllocationRunRequest,
    PostAllocationFacility,
    PostAllocationState,
)
from app.modules.facilities.schemas import FieldError, ServiceStatus
from app.modules.scenarios import service as scenarios
from app.modules.scenarios.errors import ScenarioError
from app.modules.scenarios.schemas import EffectiveScenario


class AllocationEngineError(RuntimeError):
    """Engine missing, or its proposal failed independent validation. HTTP 500; the
    proposal is never published or saved."""


def _validate_request(
    request: AllocationRunRequest, scenario: EffectiveScenario
) -> list[FieldError]:
    errors: list[FieldError] = []
    facilities = {f.snapshot.facility.facility_id: f for f in scenario.facilities}
    constrained = {c.facility_id for c in request.facility_constraints}
    profile = next(
        (p for p in scenario.requirement_profiles if p.service_id == scenario.service_id), None
    )
    if profile is None or request.resource_id not in {r.resource_id for r in profile.requirements}:
        errors.append(FieldError(field="resource_id", message=(
            f"{request.resource_id} is not required by the {scenario.service_id} profile.")))
    for i, constraint in enumerate(request.facility_constraints):
        if constraint.facility_id not in facilities:
            errors.append(FieldError(
                field=f"facility_constraints.{i}.facility_id",
                message=f"{constraint.facility_id} is not in the saved scenario."))
    for i, route in enumerate(request.routes):
        for end in ("from_facility_id", "to_facility_id"):
            facility_id = getattr(route, end)
            if facility_id not in facilities:
                errors.append(FieldError(field=f"routes.{i}.{end}",
                                         message=f"{facility_id} is not in the saved scenario."))
            elif facility_id not in constrained:
                errors.append(FieldError(field=f"routes.{i}.{end}", message=(
                    f"{facility_id} needs a facility constraint to use a route.")))
    return errors


def _engine_input(request: AllocationRunRequest, scenario: EffectiveScenario
                  ) -> AllocationEngineInput:
    constraints = {c.facility_id: c for c in request.facility_constraints}
    profile = next(
        (p for p in scenario.requirement_profiles if p.service_id == scenario.service_id), None
    )
    unit = next(r.unit for r in profile.requirements if r.resource_id == request.resource_id)
    return AllocationEngineInput(
        service_id=scenario.service_id,
        resource_id=request.resource_id,
        unit=unit,
        capacity_unit="simultaneous_service_place",
        requirement=profile,
        facilities=[
            AllocationFacilityInput(
                snapshot=f.snapshot,
                applied_overrides=f.applied_overrides,
                constraint=constraints.get(f.snapshot.facility.facility_id),
            )
            for f in scenario.facilities
        ],
        routes=request.routes,
        planning_horizon_minutes=request.planning_horizon_minutes,
        budget_minor_units=request.budget_minor_units,
        currency=request.currency,
        solver_settings=DEFAULT_SOLVER_SETTINGS,
    )


def check_plan(inputs: AllocationEngineInput, result: AllocationEngineResult) -> list[str]:
    """Independent check of every hard constraint and of the reported capacities,
    recomputed with the existing capacity engine. Empty means valid."""
    problems: list[str] = []
    by_id = {f.snapshot.facility.facility_id: f for f in inputs.facilities}
    routes = {r.route_id: r for r in inputs.routes}
    included = result.coverage.included_facility_ids
    for facility_id in included:
        f = by_id.get(facility_id)
        service = next((s for s in f.snapshot.services if s.service_id == inputs.service_id),
                       None) if f else None
        if f is None or f.constraint is None or service is None:
            problems.append(f"{facility_id} is included without a snapshot or constraint.")
        elif service.status != ServiceStatus.OPERATING:
            problems.append(f"{facility_id} is included but its service is {service.status}.")
    if problems:
        return problems

    outbound = dict.fromkeys(included, 0)
    inbound = dict.fromkeys(included, 0)
    for t in result.transfers:
        route = routes.get(t.route_id)
        if route is None or (route.from_facility_id, route.to_facility_id) != (
            t.from_facility_id, t.to_facility_id
        ):
            problems.append(f"Transfer on unapproved route {t.route_id}.")
            continue
        if t.from_facility_id not in outbound or t.to_facility_id not in inbound:
            problems.append(f"Transfer {t.route_id} involves an excluded facility.")
            continue
        if (t.resource_id, t.unit) != (inputs.resource_id, inputs.unit):
            problems.append(f"Transfer {t.route_id} moves the wrong resource or unit.")
        if t.quantity > route.maximum_quantity:
            problems.append(f"Transfer {t.route_id} exceeds the route maximum.")
        if t.lead_time_minutes != route.lead_time_minutes or (
            route.lead_time_minutes > inputs.planning_horizon_minutes
        ):
            problems.append(f"Transfer {t.route_id} misses the response deadline.")
        if t.cost_minor_units != t.quantity * route.cost_per_unit_minor_units:
            problems.append(f"Transfer {t.route_id} has the wrong cost.")
        outbound[t.from_facility_id] += t.quantity
        inbound[t.to_facility_id] += t.quantity
    if result.total_cost_minor_units > inputs.budget_minor_units:
        problems.append("Total cost exceeds the budget.")

    for summary, moved in ((result.baseline_summary, False), (result.proposed_summary, True)):
        if summary is None:
            continue
        for row in summary.rows:
            f = by_id[row.facility_id]
            constraint = f.constraint
            out, into = (outbound[row.facility_id], inbound[row.facility_id]) if moved else (0, 0)
            resource = next((r for r in f.snapshot.resources
                             if r.resource_id == inputs.resource_id), None)
            if resource is None or resource.available_quantity is None:
                problems.append(f"{row.facility_id} has no usable {inputs.resource_id} evidence.")
                continue
            final = resource.available_quantity - out + into
            if moved:
                if out and into:
                    problems.append(f"{row.facility_id} re-exports received inventory.")
                if out > constraint.transferable_quantity:
                    problems.append(f"{row.facility_id} sends more than its approved quantity.")
                if into > constraint.maximum_inbound_quantity:
                    problems.append(f"{row.facility_id} receives more than it can accept.")
                # A hard floor for every included facility, not only donors.
                if final < constraint.minimum_retained_resource_quantity:
                    problems.append(f"{row.facility_id} falls below its retained quantity.")
            updated = f.snapshot.model_copy(update={"resources": [
                r.model_copy(update={"available_quantity": final})
                if r.resource_id == inputs.resource_id else r for r in f.snapshot.resources]})
            service = next(s for s in updated.services if s.service_id == inputs.service_id)
            capacity = calculate_service_capacity(updated, service, inputs.requirement)
            if (row.resource_quantity, row.estimated_capacity, row.bottleneck_resource_ids,
                    row.required_service_places) != (
                    final, capacity.estimated_capacity, capacity.bottleneck_resource_ids,
                    constraint.required_service_places):
                problems.append(f"{row.facility_id} figures do not match the capacity engine.")
            floor = max(constraint.required_service_places,
                        constraint.minimum_retained_service_places)
            if moved and out and (capacity.estimated_capacity or 0) < floor:
                problems.append(f"{row.facility_id} donates below its protected capacity.")
    return problems


def create_run(db: Session, request: AllocationRunRequest, now: datetime) -> AllocationRun:
    try:
        scenario = scenarios.get_effective_scenario(db, request.simulation_run_id)
    except ScenarioError:
        raise AllocationError("simulation_run_not_found") from None
    errors = _validate_request(request, scenario)
    if errors:
        raise AllocationError("invalid_request", errors)

    inputs = _engine_input(request, scenario)
    optimize = getattr(allocation_engine, "optimize_allocation", None)
    if optimize is None:
        raise AllocationEngineError("engines.allocation.optimize_allocation is missing.")
    result = AllocationEngineResult.model_validate(optimize(inputs).model_dump())
    problems = check_plan(inputs, result)
    if problems:
        raise AllocationEngineError("Proposal failed independent validation: "
                                    + "; ".join(problems))

    run = AllocationRun(
        **result.model_dump(),
        allocation_run_id=f"ALLOC-{uuid.uuid4()}",
        simulation_run_id=scenario.run_id,
        incident_id=scenario.incident_id,
        revision_id=scenario.revision_id,
        baseline_id=scenario.baseline_id,
        created_at=now,
        schema_version=SCHEMA_VERSION,
        input=request,
        solver_settings=inputs.solver_settings,
    )
    repository.add(db, models.AllocationRun(
        allocation_run_id=run.allocation_run_id,
        simulation_run_id=run.simulation_run_id,
        created_at=now,
        engine_version=run.engine_version,
        solver_version=run.solver_version,
        schema_version=SCHEMA_VERSION,
        payload=run.model_dump(mode="json"),
    ))
    db.commit()
    return run


class NoProposedPlan(ValueError):
    """The saved allocation has no validated proposed summary to build on."""


def get_post_allocation_state(db: Session, allocation_run_id: str) -> PostAllocationState:
    """Public contract for investment planning. Rebuilds the frozen scenario, applies
    the saved transfers once and checks the result against the saved proposal."""
    run = get_run(db, allocation_run_id)  # raises allocation_run_not_found
    if run.proposed_summary is None or not run.validation_passed:
        raise NoProposedPlan(f"Allocation run {allocation_run_id} has no validated proposal.")
    scenario = scenarios.get_effective_scenario(db, run.simulation_run_id)
    profile = next(p for p in scenario.requirement_profiles if p.service_id == scenario.service_id)
    resource_id = run.input.resource_id
    delta: dict[str, int] = {}
    for transfer in run.transfers:
        source, target = transfer.from_facility_id, transfer.to_facility_id
        delta[source] = delta.get(source, 0) - transfer.quantity
        delta[target] = delta.get(target, 0) + transfer.quantity
    demand = {c.facility_id: c.required_service_places for c in run.input.facility_constraints}
    proposed = {row.facility_id: row for row in run.proposed_summary.rows}
    included = set(run.coverage.included_facility_ids)

    facilities = []
    for f in scenario.facilities:
        facility_id = f.snapshot.facility.facility_id
        snapshot = f.snapshot
        if delta.get(facility_id):
            snapshot = snapshot.model_copy(update={"resources": [
                r.model_copy(update={"available_quantity": r.available_quantity
                                     + delta[facility_id]})
                if r.resource_id == resource_id else r for r in snapshot.resources]})
        if facility_id in included:
            service = next(s for s in snapshot.services if s.service_id == scenario.service_id)
            capacity = calculate_service_capacity(snapshot, service, profile)
            quantity = next(r.available_quantity for r in snapshot.resources
                            if r.resource_id == resource_id)
            row = proposed[facility_id]
            if (capacity.estimated_capacity, quantity) != (row.estimated_capacity,
                                                           row.resource_quantity):
                raise RuntimeError(f"Allocation {allocation_run_id} does not match its frozen "
                                   f"inputs at {facility_id}.")
        facilities.append(PostAllocationFacility(
            snapshot=snapshot,
            required_service_places=demand.get(facility_id) if facility_id in included else None,
        ))
    return PostAllocationState(
        allocation_run_id=run.allocation_run_id,
        simulation_run_id=run.simulation_run_id,
        incident_id=run.incident_id,
        revision_id=run.revision_id,
        baseline_id=run.baseline_id,
        service_id=scenario.service_id,
        incident_starts_at=scenario.planning_starts_at,
        allocation_horizon_minutes=run.input.planning_horizon_minutes,
        requirement=profile,
        facilities=facilities,
        included_facility_ids=run.coverage.included_facility_ids,
        excluded_facilities=run.coverage.excluded,
        transfers=run.transfers,
    )


def get_run(db: Session, allocation_run_id: str) -> AllocationRun:
    row = repository.get(db, allocation_run_id)
    if row is None:
        raise AllocationError("allocation_run_not_found")
    return AllocationRun.model_validate(row.payload)
