"""Investment runs: frozen post-allocation state -> validated candidates -> engine ->
independently checked, saved funding proposal."""

import json
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.engines import investments as investments_engine
from app.engines.capacity import calculate_service_capacity
from app.modules.allocation import service as allocation
from app.modules.allocation.errors import AllocationError
from app.modules.allocation.schemas import DEFAULT_SOLVER_SETTINGS, PostAllocationState
from app.modules.facilities.schemas import FieldError
from app.modules.investments import models, repository
from app.modules.investments.errors import InvestmentError
from app.modules.investments.schemas import (
    SCHEMA_VERSION,
    InvestmentCandidate,
    InvestmentCatalog,
    InvestmentEngineInput,
    InvestmentEngineResult,
    InvestmentRun,
    InvestmentRunRequest,
    InvestmentSummary,
)

CATALOG_PATH = Path(__file__).with_name("starter_catalog.json")


class InvestmentEngineError(RuntimeError):
    """Engine missing, or its package failed independent validation. HTTP 500; the
    proposal is never published or saved."""


@lru_cache
def get_catalog() -> InvestmentCatalog:
    return InvestmentCatalog.model_validate(json.loads(CATALOG_PATH.read_text("utf-8")))


# Request validation.


def _cycle(candidates: list[InvestmentCandidate]) -> list[str]:
    """Candidate IDs on a dependency cycle (empty when acyclic)."""
    requires = {c.candidate_id: c.requires_candidate_ids for c in candidates}
    state: dict[str, int] = {}  # 1 visiting, 2 done
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        state[node] = 1
        stack.append(node)
        for nxt in requires.get(node, []):
            if state.get(nxt) == 1:
                return stack[stack.index(nxt):]
            if nxt in requires and nxt not in state and (found := visit(nxt)):
                return found
        stack.pop()
        state[node] = 2
        return []

    for node in requires:
        if node not in state and (found := visit(node)):
            return found
    return []


def _validate(request: InvestmentRunRequest, state: PostAllocationState) -> list[FieldError]:
    errors: list[FieldError] = []

    def error(field: str, message: str) -> None:
        errors.append(FieldError(field=field, message=message))

    limit = investments_engine.MAX_INTEGER
    for field in ("budget_minor_units", "operating_cost_months"):
        if getattr(request, field) > limit:
            error(field, f"Must be at most {limit} for the investment solver.")
    if len(request.candidates) > investments_engine.MAX_CANDIDATES:
        error("candidates", f"Supply at most {investments_engine.MAX_CANDIDATES} projects.")
    for field in ("planning_starts_at", "evaluation_at"):
        if getattr(request, field).utcoffset() != timedelta(0):
            error(field, "Use an explicit UTC timestamp.")

    earliest = state.incident_starts_at + timedelta(minutes=state.allocation_horizon_minutes)
    if request.planning_starts_at < earliest:
        error("planning_starts_at", "Planning cannot start before the incident start plus the "
              f"allocation horizon ({earliest.isoformat().replace('+00:00', 'Z')}).")
    if request.evaluation_at <= request.planning_starts_at:
        error("evaluation_at", "evaluation_at must be after planning_starts_at.")

    facility_ids = {f.snapshot.facility.facility_id for f in state.facilities}
    units = {r.resource_id: r.unit for r in state.requirement.requirements}
    known = {c.candidate_id for c in request.candidates}
    for i, candidate in enumerate(request.candidates):
        path = f"candidates.{i}"
        if not candidate.name.strip():
            error(f"{path}.name", "Enter a project name.")
        for field in ("capital_cost_minor_units", "monthly_operating_cost_minor_units",
                      "implementation_days"):
            if getattr(candidate, field) > limit:
                error(f"{path}.{field}", f"Must be at most {limit} for the investment solver.")
        if candidate.confirmed_at and candidate.confirmed_at.utcoffset() != timedelta(0):
            error(f"{path}.confirmed_at", "Use an explicit UTC timestamp.")
        if candidate.service_id != state.service_id:
            error(f"{path}.service_id", f"Candidates must be for {state.service_id}.")
        if candidate.facility_id not in facility_ids:
            error(f"{path}.facility_id",
                  f"{candidate.facility_id} is not in the source allocation scenario.")
        for j, effect in enumerate(candidate.resource_effects):
            if effect.quantity_delta > limit:
                error(f"{path}.resource_effects.{j}.quantity_delta",
                      f"Must be at most {limit} for the investment solver.")
            if effect.resource_id not in units:
                error(f"{path}.resource_effects.{j}.resource_id",
                      f"{effect.resource_id} is not in the {state.service_id} profile.")
            elif effect.unit != units[effect.resource_id]:
                error(f"{path}.resource_effects.{j}.unit",
                      f"Expected {units[effect.resource_id].value} for {effect.resource_id}.")
        for prerequisite in candidate.requires_candidate_ids:
            if prerequisite not in known:
                error(f"{path}.requires_candidate_ids",
                      f"Unknown prerequisite {prerequisite}.")
    if len(request.candidates) <= investments_engine.MAX_CANDIDATES and (
        cycle := _cycle(request.candidates)
    ):
        error("candidates", f"Dependency cycle: {' -> '.join(cycle)}.")
    if not errors:
        costs = sum(c.capital_cost_minor_units + c.monthly_operating_cost_minor_units *
                    request.operating_cost_months for c in request.candidates)
        if costs >= 2**60:
            error("candidates", "Combined cost bounds exceed safe solver arithmetic.")
        try:
            ready_dates(_engine_input(request, state))
        except OverflowError:
            error("candidates", "Project implementation dates exceed the supported calendar.")
    return errors


def _engine_input(request: InvestmentRunRequest, state: PostAllocationState
                  ) -> InvestmentEngineInput:
    return InvestmentEngineInput(
        service_id=state.service_id,
        capacity_unit="simultaneous_service_place",
        requirement=state.requirement,
        facilities=state.facilities,
        included_facility_ids=state.included_facility_ids,
        excluded_facilities=state.excluded_facilities,
        candidates=request.candidates,
        planning_starts_at=request.planning_starts_at,
        evaluation_at=request.evaluation_at,
        operating_cost_months=request.operating_cost_months,
        budget_minor_units=request.budget_minor_units,
        currency=request.currency,
        solver_settings=DEFAULT_SOLVER_SETTINGS,
    )


# Independent package check.


def ready_dates(inputs: InvestmentEngineInput) -> dict[str, datetime]:
    """ready_at = max(planning start, prerequisite ready dates) + implementation_days."""
    by_id = {c.candidate_id: c for c in inputs.candidates}
    ready: dict[str, datetime] = {}

    def resolve(candidate_id: str) -> datetime:
        if candidate_id not in ready:
            candidate = by_id[candidate_id]
            start = max([inputs.planning_starts_at,
                         *(resolve(p) for p in candidate.requires_candidate_ids)])
            ready[candidate_id] = start + timedelta(days=candidate.implementation_days)
        return ready[candidate_id]

    for candidate_id in by_id:
        resolve(candidate_id)
    return ready


def _check_summary(inputs: InvestmentEngineInput, summary: InvestmentSummary,
                   added: dict[str, dict[str, int]]) -> list[str]:
    problems = []
    facilities = {f.snapshot.facility.facility_id: f for f in inputs.facilities}
    profile_ids = sorted(r.resource_id for r in inputs.requirement.requirements)
    for row in summary.rows:
        f = facilities[row.facility_id]
        effects = added.get(row.facility_id, {})
        snapshot = f.snapshot.model_copy(update={"resources": [
            r.model_copy(update={"available_quantity": r.available_quantity
                                 + effects.get(r.resource_id, 0)})
            if r.available_quantity is not None else r for r in f.snapshot.resources]})
        service = next(s for s in snapshot.services if s.service_id == inputs.service_id)
        capacity = calculate_service_capacity(snapshot, service, inputs.requirement)
        quantities = [(r.resource_id, r.available_quantity) for r in snapshot.resources
                      if r.resource_id in profile_ids]
        if (row.estimated_capacity, row.bottleneck_resource_ids, row.required_service_places,
                [(q.resource_id, q.quantity) for q in row.resource_quantities],
                row.service_status) != (
                capacity.estimated_capacity, capacity.bottleneck_resource_ids,
                f.required_service_places, sorted(quantities), service.status):
            problems.append(f"{row.facility_id} figures do not match the capacity engine.")
    return problems


def check_package(inputs: InvestmentEngineInput, result: InvestmentEngineResult) -> list[str]:
    """Verify coverage, eligibility, dependencies, exclusivity, timing, costs, resource
    effects and capacities. Empty means valid."""
    problems: list[str] = []
    coverage = result.coverage
    if coverage.included_facility_ids != inputs.included_facility_ids or (
        coverage.excluded_facilities != inputs.excluded_facilities
    ):
        problems.append("Facility coverage differs from the source allocation.")
    by_id = {c.candidate_id: c for c in inputs.candidates}
    ready = ready_dates(inputs)
    selected = {p.candidate_id for p in result.selected_projects}
    groups: dict[str, int] = {}
    added: dict[str, dict[str, int]] = {}
    for project in result.selected_projects:
        candidate = by_id.get(project.candidate_id)
        if candidate is None:
            problems.append(f"{project.candidate_id} is not a supplied candidate.")
            continue
        name = candidate.candidate_id
        if candidate.source_note is None or candidate.confirmed_at is None:
            problems.append(f"{name} is selected without confirmation.")
        if candidate.facility_id not in inputs.included_facility_ids:
            problems.append(f"{name} is selected for an excluded facility.")
        if not set(candidate.requires_candidate_ids) <= selected:
            problems.append(f"{name} is selected without its prerequisites.")
        if candidate.exclusive_group_id:
            groups[candidate.exclusive_group_id] = groups.get(candidate.exclusive_group_id, 0) + 1
        if project.ready_at != ready[name] or ready[name] > inputs.evaluation_at:
            problems.append(f"{name} is not ready by evaluation_at.")
        expected_operating = candidate.monthly_operating_cost_minor_units * (
            inputs.operating_cost_months)
        if (project.facility_id, project.requires_candidate_ids, project.resource_effects,
                project.capital_cost_minor_units, project.operating_cost_minor_units) != (
                candidate.facility_id, candidate.requires_candidate_ids,
                candidate.resource_effects, candidate.capital_cost_minor_units,
                expected_operating):
            problems.append(f"{name} does not match its supplied candidate.")
        for effect in candidate.resource_effects:
            facility = added.setdefault(candidate.facility_id, {})
            facility[effect.resource_id] = facility.get(effect.resource_id, 0) + (
                effect.quantity_delta)
    problems += [f"More than one project selected in group {g}." for g, n in groups.items()
                 if n > 1]
    if result.total_cost_minor_units > inputs.budget_minor_units:
        problems.append("Total cost exceeds the budget.")
    if result.remaining_budget_minor_units != (
        inputs.budget_minor_units - result.total_cost_minor_units
    ) and result.total_cost_minor_units <= inputs.budget_minor_units:
        problems.append("remaining_budget_minor_units is wrong.")
    problems += _check_summary(inputs, result.baseline_summary, {})
    if result.proposed_summary is not None:
        problems += _check_summary(inputs, result.proposed_summary, added)
    return problems


# Runs.


def create_run(db: Session, request: InvestmentRunRequest, now: datetime) -> InvestmentRun:
    try:
        state = allocation.get_post_allocation_state(db, request.allocation_run_id)
    except AllocationError:
        raise InvestmentError("allocation_run_not_found") from None
    except allocation.NoProposedPlan as exc:
        raise InvestmentError("invalid_request", [
            FieldError(field="allocation_run_id", message=str(exc))]) from None
    errors = _validate(request, state)
    if errors:
        raise InvestmentError("invalid_request", errors)

    inputs = _engine_input(request, state)
    optimize = getattr(investments_engine, "optimize_investments", None)
    if optimize is None:
        raise InvestmentEngineError("engines.investments.optimize_investments is missing.")
    result = InvestmentEngineResult.model_validate(optimize(inputs).model_dump())
    problems = check_package(inputs, result)
    if problems:
        raise InvestmentEngineError("Package failed independent validation: "
                                    + "; ".join(problems))

    run = InvestmentRun(
        **result.model_dump(),
        investment_run_id=f"INVRUN-{uuid.uuid4()}",
        allocation_run_id=state.allocation_run_id,
        simulation_run_id=state.simulation_run_id,
        incident_id=state.incident_id,
        revision_id=state.revision_id,
        baseline_id=state.baseline_id,
        created_at=now,
        schema_version=SCHEMA_VERSION,
        input=request,
        solver_settings=inputs.solver_settings,
        assumed_transfers=state.transfers,
    )
    repository.add(db, models.InvestmentRun(
        investment_run_id=run.investment_run_id,
        allocation_run_id=run.allocation_run_id,
        created_at=now,
        catalog_version=request.catalog_version,
        engine_version=run.engine_version,
        solver_version=run.solver_version,
        schema_version=SCHEMA_VERSION,
        payload=run.model_dump(mode="json"),
    ))
    db.commit()
    return run


def get_run(db: Session, investment_run_id: str) -> InvestmentRun:
    row = repository.get(db, investment_run_id)
    if row is None:
        raise InvestmentError("investment_run_not_found")
    return InvestmentRun.model_validate(row.payload)
