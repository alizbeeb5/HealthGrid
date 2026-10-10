"""Pure monitor allocation with CP-SAT and independent capacity/constraint verification.

No database, HTTP, live observations, wall-clock dates or AI calls. The monotonic
clock measures the one shared solver budget; timestamps come from supplied inputs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from fractions import Fraction
from math import isfinite
from time import monotonic
from types import SimpleNamespace
from typing import TYPE_CHECKING

import ortools
from ortools.sat.python import cp_model

from app.engines.capacity import calculate_service_capacity

if TYPE_CHECKING:
    from app.modules.allocation.schemas import AllocationEngineInput, AllocationEngineResult


@dataclass(frozen=True)
class _ExcludedFacility:
    facility_id: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class _Coverage:
    included_facility_ids: tuple[str, ...]
    excluded_facilities: tuple[_ExcludedFacility, ...]


@dataclass(frozen=True)
class _FacilityRow:
    facility_id: str
    required_service_places: int
    estimated_capacity: int
    covered_service_places: int
    unmet_service_places: int
    bottleneck_resource_ids: tuple[str, ...]


@dataclass(frozen=True)
class _Summary:
    covered_service_places: int
    unmet_service_places: int
    facilities: tuple[_FacilityRow, ...]


@dataclass(frozen=True)
class _Transfer:
    route_id: str
    from_facility_id: str
    to_facility_id: str
    resource_id: str
    quantity: int
    unit: str
    lead_time_minutes: int
    cost_minor_units: int


@dataclass(frozen=True)
class _KernelResult:
    solver_status: str
    plan_outcome: str
    coverage: _Coverage
    baseline_summary: _Summary
    proposed_summary: _Summary | None
    transfers: tuple[_Transfer, ...]
    total_cost_minor_units: int | None
    remaining_gap_reasons: tuple[str, ...]
    validation_passed: bool
    review_required: bool
    engine_version: str
    solver_version: str
    objective_description: str
    objectives_proven: tuple[str, ...]
    solve_duration_ms: int
    solver_settings: object


ENGINE_VERSION = "monitor-allocation-v1"
OBJECTIVE = "Minimize unmet places, then cost, then moved items; freeze only proven optima."
MAX_INTEGER = 1_000_000_000


class AllocationValidationError(ValueError):
    """Malformed numerical input or independently invalid proposed transfer plan."""


class AllocationSolverError(RuntimeError):
    """Invalid CP-SAT model or inconsistent solver result; never a published plan."""


def _integer(value, field, *, positive=False):
    if type(value) is not int or not (1 if positive else 0) <= value <= MAX_INTEGER:
        raise AllocationValidationError(f"{field} must be a bounded nonnegative integer.")


def _provenance(row):
    if not row.source_note.strip() or row.confirmed_at.tzinfo is None:
        raise AllocationValidationError(
            "Planning inputs need a source note and aware confirmation."
        )


def _prepare(data):
    if data.resource_id != "working-monitors" or data.currency != "USD":
        raise AllocationValidationError("Only working-monitors (item) and USD are supported.")
    _integer(data.planning_horizon_minutes, "planning_horizon_minutes", positive=True)
    _integer(data.budget_minor_units, "budget_minor_units")
    settings = data.solver_settings
    if (
        isinstance(settings.time_limit_seconds, bool)
        or not isfinite(settings.time_limit_seconds)
        or not 0 < settings.time_limit_seconds <= 60
    ):
        raise AllocationValidationError("Solver time limit must be > 0 and <= 60 seconds.")
    if type(settings.num_search_workers) is not int or settings.num_search_workers != 1:
        raise AllocationValidationError("Use one deterministic solver worker.")
    _integer(settings.random_seed, "random_seed")
    snapshots = {s.facility.facility_id: s for s in data.snapshots}
    constraints = {c.facility_id: c for c in data.facility_constraints}
    profiles = {p.service_id: p for p in data.requirement_profiles}
    if len(snapshots) != len(data.snapshots) or len(constraints) != len(data.facility_constraints):
        raise AllocationValidationError("Duplicate facility snapshots or constraints.")
    if len(profiles) != len(data.requirement_profiles):
        raise AllocationValidationError("Duplicate service profiles.")
    if not constraints.keys() <= snapshots.keys():
        raise AllocationValidationError("Constraints reference an unknown facility.")
    for constraint in constraints.values():
        _provenance(constraint)
        for field in (
            "required_service_places",
            "minimum_retained_service_places",
            "minimum_retained_resource_quantity",
            "transferable_quantity",
            "maximum_inbound_quantity",
        ):
            value = getattr(constraint, field)
            if value is not None:
                _integer(value, f"{constraint.facility_id}.{field}")
    ids, pairs = set(), set()
    for route in data.routes:
        pair = route.from_facility_id, route.to_facility_id
        if (
            not route.route_id
            or route.route_id in ids
            or pair in pairs
            or pair[0] == pair[1]
            or not set(pair) <= snapshots.keys()
        ):
            raise AllocationValidationError(
                "Routes must have unique IDs/pairs and known endpoints."
            )
        ids.add(route.route_id)
        pairs.add(pair)
        _provenance(route)
        for field in ("lead_time_minutes", "cost_per_unit_minor_units", "maximum_quantity"):
            _integer(getattr(route, field), f"{route.route_id}.{field}")
    profile = profiles.get(data.service_id)
    included, excluded = {}, []
    for fid, snapshot in sorted(snapshots.items()):
        reasons = []
        service = next((s for s in snapshot.services if s.service_id == data.service_id), None)
        constraint = constraints.get(fid)
        if service is None:
            reasons.append("service_not_offered")
        elif service.status != "operating":
            reasons.append(
                "service_unavailable"
                if service.status == "unavailable"
                else "service_restriction_unquantified"
            )
        if constraint is None or any(
            getattr(constraint, f) is None
            for f in (
                "required_service_places",
                "minimum_retained_service_places",
                "minimum_retained_resource_quantity",
                "transferable_quantity",
                "maximum_inbound_quantity",
            )
        ):
            reasons.append("missing_planning_inputs")
        if profile is None:
            reasons.append("requirements_not_configured")
        elif service is not None:
            capacity = calculate_service_capacity(snapshot, service, profile)
            if capacity.estimated_capacity is None:
                reasons.extend(str(reason) for reason in capacity.reason_codes)
        resource = next((r for r in snapshot.resources if r.resource_id == data.resource_id), None)
        if (
            resource is None
            or resource.available_quantity is None
            or resource.data_status != "current"
        ):
            reasons.append("unusable_transfer_resource_evidence")
        elif (
            resource.unit != "item"
            or resource.allows_fractional
            or (resource.available_quantity != int(resource.available_quantity))
        ):
            raise AllocationValidationError(
                "Movable monitors must be whole items with matching units."
            )
        if profile is not None and not any(
            r.resource_id == data.resource_id for r in profile.requirements
        ):
            reasons.append("transfer_resource_not_in_profile")
        if not reasons:
            quantity = int(resource.available_quantity)
            _integer(quantity, f"{fid}.available_quantity")
            included[fid] = (snapshot, service, constraint, capacity, quantity)
        if reasons:
            excluded.append(_ExcludedFacility(fid, tuple(sorted(set(reasons)))))
    coverage = _Coverage(tuple(included), tuple(excluded))
    return included, coverage, profile


def _summary(nodes, profile, final_quantities=None):
    rows = []
    for fid, (snapshot, service, constraint, original_capacity, quantity) in nodes.items():
        capacity = original_capacity
        if final_quantities is not None:
            resources = [
                r.model_copy(
                    update={
                        "available_quantity": float(final_quantities[fid]),
                        "observation_id": None,
                        "observed_at": None,
                        "recorded_at": None,
                    }
                )
                if r.resource_id == "working-monitors"
                else r
                for r in snapshot.resources
            ]
            after = snapshot.model_copy(update={"resources": resources})
            capacity = calculate_service_capacity(after, service, profile)
        estimate = capacity.estimated_capacity
        if estimate is None:
            raise AllocationValidationError(
                "Included facilities must have known recomputed capacity."
            )
        covered = min(constraint.required_service_places, estimate)
        rows.append(
            _FacilityRow(
                fid,
                constraint.required_service_places,
                estimate,
                covered,
                constraint.required_service_places - covered,
                tuple(capacity.bottleneck_resource_ids),
            )
        )
    return _Summary(
        sum(r.covered_service_places for r in rows),
        sum(r.unmet_service_places for r in rows),
        tuple(rows),
    )


def validate_transfer_plan(
    data: AllocationEngineInput, transfers: tuple[_Transfer, ...]
) -> _Summary:
    """Independent of solver variables: reconstruct all totals and reuse capacity engine."""
    nodes, _, profile = _prepare(data)
    routes = {r.route_id: r for r in data.routes}
    inbound, outbound = dict.fromkeys(nodes, 0), dict.fromkeys(nodes, 0)
    seen, total_cost = set(), 0
    for transfer in transfers:
        route = routes.get(transfer.route_id)
        if route is None or route.route_id in seen:
            raise AllocationValidationError("Unknown or duplicate transfer route.")
        seen.add(route.route_id)
        _integer(transfer.quantity, "quantity", positive=True)
        _integer(transfer.cost_minor_units, "cost_minor_units")
        _integer(transfer.lead_time_minutes, "lead_time_minutes")
        if (transfer.from_facility_id, transfer.to_facility_id) != (
            route.from_facility_id,
            route.to_facility_id,
        ):
            raise AllocationValidationError("Transfer endpoints differ from approved route.")
        if (
            transfer.resource_id != data.resource_id
            or transfer.unit != "item"
            or transfer.lead_time_minutes != route.lead_time_minutes
            or transfer.cost_minor_units != transfer.quantity * route.cost_per_unit_minor_units
            or transfer.quantity > route.maximum_quantity
            or route.lead_time_minutes > data.planning_horizon_minutes
            or not {route.from_facility_id, route.to_facility_id} <= nodes.keys()
        ):
            raise AllocationValidationError(
                "Transfer violates eligibility, quantity, cost or deadline."
            )
        outbound[route.from_facility_id] += transfer.quantity
        inbound[route.to_facility_id] += transfer.quantity
        total_cost += transfer.cost_minor_units
    if total_cost > data.budget_minor_units:
        raise AllocationValidationError("Plan exceeds budget.")
    final = {}
    for fid, (_, _, constraint, capacity, quantity) in nodes.items():
        if outbound[fid] > min(constraint.transferable_quantity, quantity):
            raise AllocationValidationError(
                "Combined withdrawals exceed original approved inventory."
            )
        if inbound[fid] > constraint.maximum_inbound_quantity:
            raise AllocationValidationError("Combined receipts exceed receiving limit.")
        if inbound[fid] and outbound[fid]:
            raise AllocationValidationError("Receiving facilities cannot re-export inventory.")
        final[fid] = quantity + inbound[fid] - outbound[fid]
        if final[fid] < constraint.minimum_retained_resource_quantity:
            raise AllocationValidationError("Plan violates retained resource reserve.")
        if outbound[fid] and capacity.estimated_capacity < max(
            constraint.required_service_places, constraint.minimum_retained_service_places
        ):
            raise AllocationValidationError(
                "A facility below its protected capacity cannot donate."
            )
    if sum(final.values()) != sum(row[4] for row in nodes.values()):
        raise AllocationValidationError("Plan does not conserve inventory.")
    proposed = _summary(nodes, profile, final)
    for row in proposed.facilities:
        constraint = nodes[row.facility_id][2]
        if outbound[row.facility_id] and row.estimated_capacity < max(
            constraint.required_service_places, constraint.minimum_retained_service_places
        ):
            raise AllocationValidationError("Plan violates donor service capacity floor.")
    return proposed


def _optimize_allocation(data: AllocationEngineInput) -> _KernelResult:
    start = monotonic()
    nodes, coverage, profile = _prepare(data)
    baseline = _summary(nodes, profile)

    def result(status, proposed=None, transfers=(), cost=None, proven=()):
        outcome = (
            "needs_inputs"
            if status == "not_run"
            else (
                "no_solution"
                if proposed is None
                else "improved"
                if proposed.unmet_service_places < baseline.unmet_service_places
                else "no_improvement"
            )
        )
        reasons = []
        if coverage.excluded_facilities:
            reasons.append("incomplete_network_coverage")
        if proposed is None and status != "not_run":
            reasons.append("no_solver_incumbent")
        elif proposed is not None and proposed.unmet_service_places:
            reasons.append("remaining_demand_unmet_under_supplied_constraints")
        return _KernelResult(
            status,
            outcome,
            coverage,
            baseline,
            proposed,
            transfers,
            cost,
            tuple(reasons),
            proposed is not None,
            True,
            ENGINE_VERSION,
            ortools.__version__,
            OBJECTIVE,
            proven,
            max(0, round((monotonic() - start) * 1000)),
            data.solver_settings,
        )

    if not nodes:
        return result("not_run")
    rule = next(r for r in profile.requirements if r.resource_id == data.resource_id)
    ratio = Fraction(Decimal(str(rule.required_per_capacity_unit)))
    numerator, denominator = ratio.numerator, ratio.denominator
    if max(numerator, denominator) > MAX_INTEGER:
        raise AllocationValidationError("Requirement precision exceeds safe exact CP-SAT scaling.")
    model = cp_model.CpModel()
    route_vars = {}
    for route in sorted(data.routes, key=lambda r: r.route_id):
        cap = route.maximum_quantity
        if (
            route.lead_time_minutes > data.planning_horizon_minutes
            or route.from_facility_id not in nodes
            or route.to_facility_id not in nodes
        ):
            cap = 0
        else:
            source = nodes[route.from_facility_id]
            cap = min(
                cap,
                source[2].transferable_quantity,
                source[4],
                nodes[route.to_facility_id][2].maximum_inbound_quantity,
            )
        route_vars[route.route_id] = model.new_int_var(0, cap, route.route_id)
    costs = sum(route_vars[r.route_id] * r.cost_per_unit_minor_units for r in data.routes)
    if (
        sum(
            route_vars[r.route_id].proto.domain[-1] * r.cost_per_unit_minor_units
            for r in data.routes
        )
        >= 2**60
    ):
        raise AllocationValidationError("Route cost bounds exceed safe CP-SAT arithmetic.")
    model.add(costs <= data.budget_minor_units)
    unmet_terms = []
    for fid, (_, _, constraint, capacity, quantity) in nodes.items():
        incoming = sum(route_vars[r.route_id] for r in data.routes if r.to_facility_id == fid)
        outgoing = sum(route_vars[r.route_id] for r in data.routes if r.from_facility_id == fid)
        model.add(incoming <= constraint.maximum_inbound_quantity)
        model.add(outgoing <= min(constraint.transferable_quantity, quantity))
        receiving = model.new_bool_var(f"receiving:{fid}")
        model.add(incoming == 0).only_enforce_if(receiving.Not())
        model.add(outgoing == 0).only_enforce_if(receiving)
        final = model.new_int_var(0, quantity + constraint.maximum_inbound_quantity, f"final:{fid}")
        model.add(final == quantity + incoming - outgoing)
        model.add(final >= constraint.minimum_retained_resource_quantity)
        floor = max(constraint.required_service_places, constraint.minimum_retained_service_places)
        if capacity.estimated_capacity < floor:
            model.add(outgoing == 0)
        else:
            # Any original donor remains above its floor after combined transfers.
            donor = model.new_bool_var(f"donor:{fid}")
            model.add(outgoing >= 1).only_enforce_if(donor)
            model.add(outgoing == 0).only_enforce_if(donor.Not())
            model.add(denominator * final >= numerator * floor).only_enforce_if(donor)
        fixed_limits = [
            limit.capacity_limit
            for limit in capacity.resource_limits
            if limit.resource_id != data.resource_id
        ]
        upper = min([constraint.required_service_places, *fixed_limits])
        covered = model.new_int_var(0, upper, f"covered:{fid}")
        model.add(numerator * covered <= denominator * final)
        unmet_terms.append(constraint.required_service_places - covered)
    objectives = (
        ("unmet_service_places", sum(unmet_terms)),
        ("transfer_cost", costs),
        ("moved_items", sum(route_vars.values())),
    )
    best, best_cost, best_summary, proven = None, None, None, []
    for name, objective in objectives:
        remaining = data.solver_settings.time_limit_seconds - (monotonic() - start)
        if remaining <= 0:
            break
        model.minimize(objective)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = remaining
        solver.parameters.num_search_workers = data.solver_settings.num_search_workers
        solver.parameters.random_seed = data.solver_settings.random_seed
        status = solver.solve(model)
        if status == cp_model.MODEL_INVALID:
            raise AllocationSolverError("CP-SAT rejected allocation model: " + model.validate())
        if status == cp_model.INFEASIBLE:
            if best is not None:
                raise AllocationSolverError(
                    "A frozen proven objective made a feasible model infeasible."
                )
            return result("infeasible")
        if status == cp_model.UNKNOWN:
            break
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise AllocationSolverError("Unexpected CP-SAT status.")
        transfers = tuple(
            _Transfer(
                route.route_id,
                route.from_facility_id,
                route.to_facility_id,
                data.resource_id,
                solver.value(route_vars[route.route_id]),
                "item",
                route.lead_time_minutes,
                solver.value(route_vars[route.route_id]) * route.cost_per_unit_minor_units,
            )
            for route in sorted(data.routes, key=lambda r: r.route_id)
            if solver.value(route_vars[route.route_id]) > 0
        )
        proposed = validate_transfer_plan(data, transfers)
        cost = sum(t.cost_minor_units for t in transfers)
        rank = proposed.unmet_service_places, cost, sum(t.quantity for t in transfers)
        previous = (
            None
            if best is None
            else (best_summary.unmet_service_places, best_cost, sum(t.quantity for t in best))
        )
        if previous is None or rank < previous:
            best, best_cost, best_summary = transfers, cost, proposed
        if status != cp_model.OPTIMAL:
            break
        optimum = solver.value(objective)
        if name == "unmet_service_places" and optimum != proposed.unmet_service_places:
            raise AllocationSolverError(
                "Primary optimum differs from independently recomputed capacity."
            )
        proven.append(name)
        model.add(objective == optimum)
    if best is None:
        return result("unknown")
    return result(
        "optimal" if len(proven) == 3 else "feasible", best_summary, best, best_cost, tuple(proven)
    )


def optimize_allocation(input: AllocationEngineInput) -> AllocationEngineResult:
    """Adapt backend-owned frozen inputs to the kernel and publish checked typed output."""
    from app.modules.allocation.schemas import AllocationEngineResult

    if input.unit != "item" or input.capacity_unit != "simultaneous_service_place":
        raise AllocationValidationError(
            "Allocation requires items and simultaneous service places."
        )
    if input.solver_settings.objective_order != [
        "minimize_unmet_demand",
        "minimize_transfer_cost",
        "minimize_moved_items",
    ]:
        raise AllocationValidationError("Unsupported allocation objective order.")
    data = SimpleNamespace(
        service_id=input.service_id,
        resource_id=input.resource_id,
        snapshots=[f.snapshot for f in input.facilities],
        facility_constraints=[f.constraint for f in input.facilities if f.constraint is not None],
        requirement_profiles=[input.requirement] if input.requirement else [],
        routes=input.routes,
        planning_horizon_minutes=input.planning_horizon_minutes,
        budget_minor_units=input.budget_minor_units,
        currency=input.currency,
        solver_settings=SimpleNamespace(
            time_limit_seconds=input.solver_settings.time_limit_seconds,
            num_search_workers=1,
            random_seed=0,
        ),
    )
    result = _optimize_allocation(data)
    reasons_map = {
        "missing_planning_inputs": "no_planning_constraints",
        "service_restriction_unquantified": "service_limited",
        "service_not_offered": "missing_required_evidence",
        "requirements_not_configured": "requirements_not_configured",
        "transfer_resource_not_in_profile": "requirements_not_configured",
        "service_unavailable": "service_unavailable",
        "stale_required_observation": "stale_required_evidence",
    }
    excluded = []
    for item in result.coverage.excluded_facilities:
        facility = next(
            f for f in input.facilities if f.snapshot.facility.facility_id == item.facility_id
        )
        movable = next(
            (r for r in facility.snapshot.resources if r.resource_id == input.resource_id), None
        )
        codes = {
            reasons_map.get(code, "missing_required_evidence")
            for code in item.reason_codes
            if not (
                code == "unusable_transfer_resource_evidence"
                and movable is not None
                and movable.data_status == "stale"
            )
        }
        # Unavailable services still expose freshness of required resource evidence.
        if input.requirement:
            required = {r.resource_id for r in input.requirement.requirements}
            resources = {r.resource_id: r for r in facility.snapshot.resources}
            if any(r in resources and resources[r].data_status == "stale" for r in required):
                codes.add("stale_required_evidence")
            if any(r not in resources or resources[r].data_status == "unknown" for r in required):
                codes.add("missing_required_evidence")
        excluded.append({"facility_id": item.facility_id, "reasons": sorted(codes)})
    quantities = {
        f.snapshot.facility.facility_id: next(
            (
                r.available_quantity
                for r in f.snapshot.resources
                if r.resource_id == input.resource_id
            ),
            None,
        )
        for f in input.facilities
    }
    for transfer in result.transfers:
        quantities[transfer.from_facility_id] -= transfer.quantity
        quantities[transfer.to_facility_id] += transfer.quantity

    def summary(value, proposed=False):
        if value is None:
            return None
        rows = []
        for row in value.facilities:
            facility = next(
                f for f in input.facilities if f.snapshot.facility.facility_id == row.facility_id
            )
            original = next(
                r.available_quantity
                for r in facility.snapshot.resources
                if r.resource_id == input.resource_id
            )
            rows.append(
                {
                    **asdict(row),
                    "service_status": "operating",
                    "resource_quantity": int(quantities[row.facility_id] if proposed else original),
                }
            )
        return {
            "included_facility_ids": list(result.coverage.included_facility_ids),
            "required_service_places": sum(r.required_service_places for r in value.facilities),
            "covered_service_places": value.covered_service_places,
            "unmet_service_places": value.unmet_service_places,
            "rows": rows,
        }

    messages = []
    if result.solver_status == "not_run":
        messages.append(
            "No facility has complete planning constraints and usable evidence; "
            "enter constraints to compute a proposal."
        )
    elif result.solver_status == "infeasible":
        messages.append(
            "The confirmed constraints cannot all hold, even with no transfers; "
            "check retained quantities against current inventory."
        )
    elif result.proposed_summary is None:
        messages.append(
            "No solution or infeasibility proof was found within the solver time limit."
        )
    else:
        if result.proposed_summary.unmet_service_places:
            suffix = (
                "no further approved, affordable, in-time transfer improves coverage."
                if "unmet_service_places" in result.objectives_proven
                else "optimal coverage has not been proven within the time limit."
            )
            messages.append(
                f"{result.proposed_summary.unmet_service_places} modeled places remain unmet "
                f"across included facilities; {suffix}"
            )
        messages.extend(
            f"{e['facility_id']} is excluded ({', '.join(e['reasons'])}); "
            "its demand is not counted."
            for e in excluded
        )
    return AllocationEngineResult(
        engine_version="allocation-cpsat-v1",
        solver_version=f"ortools-cp-sat-{ortools.__version__}",
        solver_status=result.solver_status,
        plan_outcome=result.plan_outcome,
        coverage={
            "included_facility_ids": list(result.coverage.included_facility_ids),
            "excluded": excluded,
        },
        baseline_summary=summary(result.baseline_summary),
        proposed_summary=summary(result.proposed_summary, True),
        transfers=[asdict(t) for t in result.transfers],
        total_cost_minor_units=result.total_cost_minor_units or 0,
        remaining_gap_reasons=messages,
        validation_passed=result.validation_passed,
        review_required=True,
        objective_description=(
            "Minimize unmet modeled service places across included facilities, "
            "then total transfer cost, then the number of moved items."
        ),
        solve_duration_ms=result.solve_duration_ms,
    )
