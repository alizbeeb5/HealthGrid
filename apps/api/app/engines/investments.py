"""Pure CP-SAT investment engine using the backend-owned contracts.

Frozen post-allocation quantities are supplied, never reconstructed here. No HTTP,
database or AI calls. A monotonic clock measures the single shared solver budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from math import isfinite
from time import monotonic
from typing import Protocol, Sequence

import ortools
from ortools.sat.python import cp_model

from app.engines.capacity import calculate_service_capacity
from app.modules.capacity.schemas import ServiceRequirement
from app.modules.facilities.schemas import FacilitySnapshotResponse
from app.modules.investments.schemas import InvestmentEngineInput, InvestmentEngineResult

ENGINE_VERSION = "investment-cpsat-v1"
OBJECTIVE = "Minimize unmet modeled places, then total investment cost, then project count."
MAX_INTEGER = 1_000_000_000
MAX_CANDIDATES = 200


class _EffectInput(Protocol):
    resource_id: str
    quantity_delta: int
    unit: str


class _CandidateInput(Protocol):
    candidate_id: str
    name: str
    facility_id: str
    service_id: str
    capital_cost_minor_units: int
    monthly_operating_cost_minor_units: int
    implementation_days: int
    resource_effects: Sequence[_EffectInput]
    requires_candidate_ids: Sequence[str]
    exclusive_group_id: str | None
    source_note: str | None
    confirmed_at: datetime | None


class _ExclusionInput(Protocol):
    facility_id: str
    reasons: Sequence[str]


class _SolverInput(Protocol):
    time_limit_seconds: float
    random_seed: int
    num_search_workers: int


class _Problem(Protocol):
    """Private structural kernel input, not an independently published wire schema."""

    service_id: str
    capacity_unit: str
    currency: str
    snapshots: Sequence[FacilitySnapshotResponse]
    requirement_profiles: Sequence[ServiceRequirement]
    required_service_places: dict[str, int | None]
    included_facility_ids: Sequence[str]
    excluded_facilities: Sequence[_ExclusionInput]
    candidates: Sequence[_CandidateInput]
    planning_starts_at: datetime
    evaluation_at: datetime
    operating_cost_months: int
    budget_minor_units: int
    solver_settings: _SolverInput


class InvestmentValidationError(ValueError):
    """Invalid numerical input or independently invalid selected package."""


class InvestmentSolverError(RuntimeError):
    """Invalid model or inconsistent solver output; no proposal may be published."""


@dataclass(frozen=True)
class _Exclusion:
    identifier: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class _Coverage:
    included_facility_ids: tuple[str, ...]
    excluded_facilities: tuple[_Exclusion, ...]
    excluded_candidates: tuple[_Exclusion, ...]


@dataclass(frozen=True)
class _Row:
    facility_id: str
    service_status: str
    required_service_places: int
    estimated_capacity: int
    covered_service_places: int
    unmet_service_places: int
    bottleneck_resource_ids: tuple[str, ...]
    resource_quantities: dict[str, float]


@dataclass(frozen=True)
class _Summary:
    included_facility_ids: tuple[str, ...]
    required_service_places: int
    covered_service_places: int
    unmet_service_places: int
    rows: tuple[_Row, ...]


@dataclass(frozen=True)
class _SelectedProject:
    candidate_id: str
    ready_at: datetime
    resource_effects: tuple[_EffectInput, ...]
    capital_cost_minor_units: int
    operating_cost_minor_units: int
    total_cost_minor_units: int


@dataclass(frozen=True)
class _KernelResult:
    solver_status: str
    plan_outcome: str
    coverage: _Coverage
    baseline_summary: _Summary
    proposed_summary: _Summary | None
    selected_projects: tuple[_SelectedProject, ...]
    total_capital_cost_minor_units: int
    total_operating_cost_minor_units: int
    total_cost_minor_units: int
    remaining_budget_minor_units: int
    remaining_gap_reasons: tuple[str, ...]
    validation_passed: bool
    review_required: bool
    engine_version: str
    solver_version: str
    objective_description: str
    objectives_proven: tuple[str, ...]
    solve_duration_ms: int


def _integer(value, field, *, positive=False):
    if type(value) is not int or not (1 if positive else 0) <= value <= MAX_INTEGER:
        raise InvestmentValidationError(f"{field}: enter a bounded nonnegative whole number.")


def _utc(value, field):
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise InvestmentValidationError(f"{field}: an aware UTC timestamp is required.")


def _prepare(data: _Problem):
    if data.currency != "USD" or data.capacity_unit != "simultaneous_service_place":
        raise InvestmentValidationError("Use USD and simultaneous_service_place units.")
    _utc(data.planning_starts_at, "planning_starts_at")
    _utc(data.evaluation_at, "evaluation_at")
    if data.evaluation_at < data.planning_starts_at:
        raise InvestmentValidationError("evaluation_at must not precede planning_starts_at.")
    _integer(data.operating_cost_months, "operating_cost_months", positive=True)
    _integer(data.budget_minor_units, "budget_minor_units")
    settings = data.solver_settings
    if (
        isinstance(settings.time_limit_seconds, bool)
        or not isfinite(settings.time_limit_seconds)
        or not 0 < settings.time_limit_seconds <= 5
    ):
        raise InvestmentValidationError("Solver total time limit must be > 0 and <= 5 seconds.")
    if type(settings.num_search_workers) is not int or settings.num_search_workers != 1:
        raise InvestmentValidationError("Use one deterministic solver worker.")
    _integer(settings.random_seed, "random_seed")
    snapshots = {s.facility.facility_id: s for s in data.snapshots}
    profiles = {p.service_id: p for p in data.requirement_profiles}
    if len(snapshots) != len(data.snapshots) or len(profiles) != len(data.requirement_profiles):
        raise InvestmentValidationError("Snapshots and service profiles must be unique.")
    included_ids = set(data.included_facility_ids)
    inherited = {e.facility_id: tuple(e.reasons) for e in data.excluded_facilities}
    if (
        len(included_ids) != len(data.included_facility_ids)
        or len(inherited) != len(data.excluded_facilities)
        or included_ids & inherited.keys()
        or included_ids | inherited.keys() != snapshots.keys()
    ):
        raise InvestmentValidationError("Inherited coverage must partition frozen facilities.")
    if not data.required_service_places.keys() <= snapshots.keys():
        raise InvestmentValidationError("Demand references an unknown facility.")
    for fid, demand in data.required_service_places.items():
        if demand is not None:
            _integer(demand, f"required_service_places.{fid}")
    nodes, excluded = {}, dict(inherited)
    profile = profiles.get(data.service_id)
    for fid in sorted(included_ids):
        snapshot = snapshots[fid]
        service = next((s for s in snapshot.services if s.service_id == data.service_id), None)
        demand = data.required_service_places.get(fid)
        reasons = []
        if demand is None:
            reasons.append("missing_required_demand")
        if service is None:
            reasons.append("service_not_offered")
        elif service.status != "operating":
            reasons.append(
                "service_unavailable" if service.status == "unavailable" else "service_limited"
            )
        if profile is None:
            reasons.append("requirements_not_configured")
        elif service is not None:
            baseline = calculate_service_capacity(snapshot, service, profile)
            if baseline.estimated_capacity is None:
                reasons.extend(str(reason) for reason in baseline.reason_codes)
        if reasons:
            excluded[fid] = tuple(sorted(set(reasons)))
        else:
            nodes[fid] = (snapshot, service, demand, baseline)
    candidates = {c.candidate_id: c for c in data.candidates}
    if len(candidates) != len(data.candidates) or len(candidates) > MAX_CANDIDATES:
        raise InvestmentValidationError("Candidate IDs must be unique; at most 200 projects.")
    for cid, candidate in candidates.items():
        if not cid or not candidate.name.strip():
            raise InvestmentValidationError("Candidate IDs and names must not be blank.")
        if candidate.facility_id not in snapshots or candidate.service_id != data.service_id:
            raise InvestmentValidationError(f"{cid}: unknown facility or incompatible service.")
        for field in (
            "capital_cost_minor_units",
            "monthly_operating_cost_minor_units",
            "implementation_days",
        ):
            _integer(getattr(candidate, field), f"{cid}.{field}")
        dependencies = candidate.requires_candidate_ids
        if (
            len(set(dependencies)) != len(dependencies)
            or cid in dependencies
            or not set(dependencies) <= candidates.keys()
        ):
            raise InvestmentValidationError(f"{cid}: unknown, duplicate or self dependency.")
        if candidate.confirmed_at is not None:
            _utc(candidate.confirmed_at, f"{cid}.confirmed_at")
        if candidate.exclusive_group_id is not None and not candidate.exclusive_group_id.strip():
            raise InvestmentValidationError(f"{cid}: exclusive group must be null or nonblank.")
        resources = {r.resource_id: r for r in snapshots[candidate.facility_id].resources}
        rules = {r.resource_id: r for r in profile.requirements} if profile else {}
        seen = set()
        for effect in candidate.resource_effects:
            _integer(effect.quantity_delta, f"{cid}.{effect.resource_id}.quantity_delta")
            if effect.resource_id in seen:
                raise InvestmentValidationError(f"{cid}: duplicate resource effect.")
            seen.add(effect.resource_id)
            resource = resources.get(effect.resource_id)
            if effect.resource_id not in rules and profile is not None:
                raise InvestmentValidationError(f"{cid}: resource is not in the frozen profile.")
            rule = rules.get(effect.resource_id)
            if resource is None and rule is None:
                raise InvestmentValidationError(f"{cid}: unknown resource ID.")
            if (rule is not None and effect.unit != rule.unit) or (
                resource is not None and effect.unit != resource.unit
            ):
                raise InvestmentValidationError(f"{cid}: resource effect unit mismatch.")
            if (resource is not None and resource.allows_fractional) or effect.unit == "liter":
                raise InvestmentValidationError(f"{cid}: only integer resource effects supported.")
    # Topological earliest completion includes every prerequisite, charged only once.
    ready, order = {}, []
    pending = set(candidates)
    while pending:
        available = sorted(
            cid for cid in pending if set(candidates[cid].requires_candidate_ids) <= ready.keys()
        )
        if not available:
            raise InvestmentValidationError("Candidate dependency graph contains a cycle.")
        for cid in available:
            candidate = candidates[cid]
            begins = max(
                [data.planning_starts_at, *(ready[dep] for dep in candidate.requires_candidate_ids)]
            )
            try:
                ready[cid] = begins + timedelta(days=candidate.implementation_days)
            except OverflowError:
                raise InvestmentValidationError(
                    f"{cid}: implementation date is out of range."
                ) from None
            order.append(cid)
            pending.remove(cid)
    ineligible = {}
    for cid in order:
        candidate = candidates[cid]
        reasons = []
        if candidate.facility_id not in nodes:
            reasons.append("facility_excluded")
        if (
            not candidate.source_note
            or not candidate.source_note.strip()
            or candidate.confirmed_at is None
        ):
            reasons.append("missing_candidate_confirmation")
        if ready[cid] > data.evaluation_at:
            reasons.append("ready_after_evaluation")
        if any(dep in ineligible for dep in candidate.requires_candidate_ids):
            reasons.append("prerequisite_ineligible")
        if reasons:
            ineligible[cid] = tuple(sorted(set(reasons)))
    coverage = _Coverage(
        tuple(nodes),
        tuple(_Exclusion(fid, excluded[fid]) for fid in sorted(excluded)),
        tuple(_Exclusion(cid, ineligible[cid]) for cid in sorted(ineligible)),
    )
    return nodes, candidates, ready, ineligible, coverage, profile


def _summary(nodes, profile, candidates=(), selected=()):
    effects = {}
    for cid in selected:
        candidate = candidates[cid]
        for effect in candidate.resource_effects:
            key = candidate.facility_id, effect.resource_id
            effects[key] = effects.get(key, 0) + effect.quantity_delta
    rows = []
    for fid, (snapshot, service, demand, baseline) in nodes.items():
        resources = []
        for resource in snapshot.resources:
            key = fid, resource.resource_id
            if key in effects:
                resource = resource.model_copy(
                    update={
                        "available_quantity": resource.available_quantity + effects[key],
                        "observation_id": None,
                        "observed_at": None,
                        "recorded_at": None,
                    }
                )
            resources.append(resource)
        updated = snapshot.model_copy(update={"resources": resources})
        capacity = calculate_service_capacity(updated, service, profile)
        if capacity.estimated_capacity is None:
            raise InvestmentValidationError("Selected package has unknown recomputed capacity.")
        covered = min(demand, capacity.estimated_capacity)
        rows.append(
            _Row(
                fid,
                str(service.status),
                demand,
                capacity.estimated_capacity,
                covered,
                demand - covered,
                tuple(capacity.bottleneck_resource_ids),
                {
                    r.resource_id: r.available_quantity
                    for r in resources
                    if r.resource_id in {rule.resource_id for rule in profile.requirements}
                },
            )
        )
    return _Summary(
        tuple(nodes),
        sum(r.required_service_places for r in rows),
        sum(r.covered_service_places for r in rows),
        sum(r.unmet_service_places for r in rows),
        tuple(rows),
    )


def _validate_selected_package(data: _Problem, selected_ids: Sequence[str]):
    """Independently verify selected IDs, graph, times, costs, effects and capacity."""
    nodes, candidates, ready, ineligible, _, profile = _prepare(data)
    selected = set(selected_ids)
    if len(selected) != len(selected_ids) or not selected <= candidates.keys():
        raise InvestmentValidationError("Selected projects contain duplicate or unknown IDs.")
    if selected & ineligible.keys():
        raise InvestmentValidationError("Selected project lacks usable evidence or is not ready.")
    groups, projects = set(), []
    for cid in sorted(selected):
        candidate = candidates[cid]
        if not set(candidate.requires_candidate_ids) <= selected:
            raise InvestmentValidationError("Selected package is missing a prerequisite.")
        if candidate.exclusive_group_id is not None:
            if candidate.exclusive_group_id in groups:
                raise InvestmentValidationError("Selected package duplicates an exclusive asset.")
            groups.add(candidate.exclusive_group_id)
        operating = candidate.monthly_operating_cost_minor_units * data.operating_cost_months
        cost = candidate.capital_cost_minor_units + operating
        projects.append(
            _SelectedProject(
                cid,
                ready[cid],
                tuple(candidate.resource_effects),
                candidate.capital_cost_minor_units,
                operating,
                cost,
            )
        )
    if sum(p.total_cost_minor_units for p in projects) > data.budget_minor_units:
        raise InvestmentValidationError("Investment package exceeds the full-cost budget.")
    return _summary(nodes, profile, candidates, selected), tuple(projects)


def _optimize_investments(data: _Problem, *, require_confirmed_candidates=False) -> _KernelResult:
    """Internal numerical entry; backend supplies the public engine types separately."""
    start = monotonic()
    nodes, candidates, ready, ineligible, coverage, profile = _prepare(data)
    baseline = _summary(nodes, profile)

    def result(status, proposed=None, projects=(), proven=()):
        capital = sum(p.capital_cost_minor_units for p in projects)
        operating = sum(p.operating_cost_minor_units for p in projects)
        outcome = (
            "needs_inputs"
            if status == "not_run"
            else "no_solution"
            if proposed is None
            else "improved"
            if proposed.unmet_service_places < baseline.unmet_service_places
            else "no_improvement"
        )
        reasons = []
        if coverage.excluded_facilities:
            reasons.append("incomplete_facility_coverage")
        if coverage.excluded_candidates:
            reasons.append("some_candidates_ineligible")
        if status == "not_run":
            reasons.append("no_usable_source_coverage")
        elif proposed is None:
            reasons.append("no_solver_incumbent")
        elif proposed.unmet_service_places:
            reasons.append("remaining_demand_unmet_under_supplied_projects_and_constraints")
        return _KernelResult(
            status,
            outcome,
            coverage,
            baseline,
            proposed,
            projects,
            capital,
            operating,
            capital + operating,
            data.budget_minor_units - capital - operating,
            tuple(reasons),
            proposed is not None,
            True,
            ENGINE_VERSION,
            ortools.__version__,
            OBJECTIVE,
            proven,
            max(0, round((monotonic() - start) * 1000)),
        )

    if not nodes or (
        require_confirmed_candidates
        and data.candidates
        and all(not c.source_note or c.confirmed_at is None for c in data.candidates)
    ):
        return result("not_run")
    model = cp_model.CpModel()
    chosen = {cid: model.new_bool_var(cid) for cid in sorted(candidates)}
    costs = {}
    groups = {}
    for cid, candidate in candidates.items():
        costs[cid] = (
            candidate.capital_cost_minor_units
            + candidate.monthly_operating_cost_minor_units * data.operating_cost_months
        )
        if cid in ineligible:
            model.add(chosen[cid] == 0)
        for dependency in candidate.requires_candidate_ids:
            model.add(chosen[cid] <= chosen[dependency])
        if candidate.exclusive_group_id is not None:
            groups.setdefault(candidate.exclusive_group_id, []).append(chosen[cid])
    if sum(costs.values()) >= 2**60:
        raise InvestmentValidationError("Project cost bounds exceed safe CP-SAT arithmetic.")
    for variables in groups.values():
        model.add(sum(variables) <= 1)
    total_cost = sum(chosen[cid] * costs[cid] for cid in candidates)
    model.add(total_cost <= data.budget_minor_units)
    unmet = []
    for fid, (snapshot, service, demand, baseline_capacity) in nodes.items():
        covered = model.new_int_var(0, demand, f"covered:{fid}")
        resources = {r.resource_id: r for r in snapshot.resources}
        for rule in profile.requirements:
            ratio = Fraction(Decimal(str(rule.required_per_capacity_unit)))
            quantity = Fraction(Decimal(str(resources[rule.resource_id].available_quantity)))
            delta = sum(
                chosen[cid] * effect.quantity_delta
                for cid, candidate in candidates.items()
                if candidate.facility_id == fid
                for effect in candidate.resource_effects
                if effect.resource_id == rule.resource_id
            )
            left = ratio.numerator * quantity.denominator
            right_constant = ratio.denominator * quantity.numerator
            right_delta = ratio.denominator * quantity.denominator
            if max(left, right_constant, right_delta) > MAX_INTEGER:
                raise InvestmentValidationError("Resource precision exceeds safe exact scaling.")
            maximum_delta = sum(
                effect.quantity_delta
                for candidate in candidates.values()
                if candidate.facility_id == fid
                for effect in candidate.resource_effects
                if effect.resource_id == rule.resource_id
            )
            if max(left * demand, right_constant + right_delta * maximum_delta) >= 2**60:
                raise InvestmentValidationError("Resource bounds exceed safe CP-SAT arithmetic.")
            model.add(left * covered <= right_constant + right_delta * delta)
        unmet.append(demand - covered)
    objectives = (
        ("unmet_service_places", sum(unmet)),
        ("total_investment_cost", total_cost),
        ("project_count", sum(chosen.values())),
    )
    best, best_summary, best_rank, proven = None, None, None, []
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
            raise InvestmentSolverError("CP-SAT rejected investment model: " + model.validate())
        if status == cp_model.INFEASIBLE:
            if best is not None:
                raise InvestmentSolverError(
                    "A frozen proven objective invalidated a feasible model."
                )
            return result("infeasible")
        if status == cp_model.UNKNOWN:
            break
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise InvestmentSolverError("Unexpected CP-SAT status.")
        selected = tuple(cid for cid in sorted(candidates) if solver.value(chosen[cid]))
        proposed, projects = _validate_selected_package(data, selected)
        rank = (
            proposed.unmet_service_places,
            sum(p.total_cost_minor_units for p in projects),
            len(projects),
        )
        if best_rank is None or rank < best_rank:
            best, best_summary, best_rank = projects, proposed, rank
        if status != cp_model.OPTIMAL:
            break
        optimum = solver.value(objective)
        if name == "unmet_service_places" and optimum != proposed.unmet_service_places:
            raise InvestmentSolverError("Solver coverage differs from recomputed capacity.")
        proven.append(name)
        model.add(objective == optimum)
    if best is None:
        return result("unknown")
    return result("optimal" if len(proven) == 3 else "feasible", best_summary, best, tuple(proven))


def optimize_investments(data: InvestmentEngineInput) -> InvestmentEngineResult:
    """Calculate a funding proposal from frozen, backend-validated source data."""
    from dataclasses import asdict
    from types import SimpleNamespace

    problem = SimpleNamespace(
        service_id=data.service_id,
        capacity_unit=data.capacity_unit,
        currency=data.currency,
        snapshots=[f.snapshot for f in data.facilities],
        requirement_profiles=[data.requirement],
        required_service_places={
            f.snapshot.facility.facility_id: f.required_service_places for f in data.facilities
        },
        included_facility_ids=data.included_facility_ids,
        excluded_facilities=data.excluded_facilities,
        candidates=data.candidates,
        planning_starts_at=data.planning_starts_at,
        evaluation_at=data.evaluation_at,
        operating_cost_months=data.operating_cost_months,
        budget_minor_units=data.budget_minor_units,
        solver_settings=SimpleNamespace(
            time_limit_seconds=data.solver_settings.time_limit_seconds,
            num_search_workers=1,
            random_seed=0,
        ),
    )
    result = _optimize_investments(problem, require_confirmed_candidates=True)
    payload = asdict(result)
    payload.pop("objectives_proven")
    payload["solver_version"] = "ortools-cp-sat-" + ortools.__version__
    payload["objective_description"] = (
        "Minimize unmet modeled service places across included facilities at evaluation_at, "
        "then total cost (capital plus operating allowance), then the number of projects."
    )
    payload["coverage"] = {
        "included_facility_ids": list(result.coverage.included_facility_ids),
        "excluded_facilities": [
            {"facility_id": e.identifier, "reasons": list(e.reasons)}
            for e in result.coverage.excluded_facilities
        ],
        "excluded_candidates": [
            {
                "candidate_id": e.identifier,
                "reasons": [
                    {
                        "missing_candidate_confirmation": "missing_confirmation",
                        "ready_after_evaluation": "not_ready_by_evaluation",
                    }.get(reason, reason)
                    for reason in e.reasons
                ],
            }
            for e in result.coverage.excluded_candidates
        ],
    }
    for key in ("baseline_summary", "proposed_summary"):
        if payload[key] is not None:
            for row in payload[key]["rows"]:
                row["resource_quantities"] = [
                    {"resource_id": rid, "quantity": quantity}
                    for rid, quantity in sorted(row["resource_quantities"].items())
                ]
    candidates = {c.candidate_id: c for c in data.candidates}
    for project in payload["selected_projects"]:
        candidate = candidates[project["candidate_id"]]
        project["facility_id"] = candidate.facility_id
        project["requires_candidate_ids"] = candidate.requires_candidate_ids
    reasons = []
    if result.solver_status == "not_run":
        reasons.append(
            "Confirm candidate evidence (source_note and confirmed_at) "
            "before a package can be calculated."
            if result.coverage.included_facility_ids
            else "No usable source facilities are included; excluded demand remains unknown."
        )
    elif result.proposed_summary is None:
        reasons.append(
            f"No package was found within the {data.solver_settings.time_limit_seconds:g}-second "
            "limit; this is not proof that none exists."
            if result.solver_status == "unknown"
            else "No feasible package satisfies the supplied constraints."
        )
    else:
        if result.proposed_summary.unmet_service_places:
            reasons.append(
                f"{result.proposed_summary.unmet_service_places} modeled places remain unmet "
                "across included facilities; no eligible, affordable package "
                "closes more by evaluation_at."
                if result.solver_status == "optimal"
                else f"{result.proposed_summary.unmet_service_places} modeled places remain unmet; "
                "this feasible package is not proven optimal."
            )
        reasons.extend(
            f"{e['candidate_id']} is not eligible ({', '.join(e['reasons'])})."
            for e in payload["coverage"]["excluded_candidates"]
        )
        reasons.extend(
            f"{e.identifier} is excluded ({', '.join(e.reasons)}); its demand is not counted."
            for e in result.coverage.excluded_facilities
        )
    payload["remaining_gap_reasons"] = reasons
    return InvestmentEngineResult.model_validate(payload)
