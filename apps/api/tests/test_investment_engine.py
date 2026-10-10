"""Pure numerical checks. No API, database, AI or production observations."""

import itertools
import json
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from investment_fixture_types import Candidate, Effect, Exclusion, Problem, SolverSettings
from ortools.sat.python import cp_model

from app.engines import investments
from app.engines.investments import (
    InvestmentSolverError,
    InvestmentValidationError,
)
from app.engines.investments import (
    _optimize_investments as solve,
)
from app.engines.investments import (
    _validate_selected_package as check,
)
from app.modules.capacity.schemas import ServiceRequirement
from app.modules.facilities.schemas import FacilitySnapshotResponse

FIXTURES = Path(__file__).resolve().parents[3] / "data/synthetic/feature-7"


def read(name):
    return json.loads((FIXTURES / name).read_text())


def problem():
    planning = read("planning-inputs.json")
    planning.pop("assumptions")
    for field in ("planning_starts_at", "evaluation_at"):
        planning[field] = datetime.fromisoformat(planning[field])
    planning["included_facility_ids"] = tuple(planning["included_facility_ids"])
    planning["excluded_facilities"] = tuple(
        Exclusion(row["facility_id"], tuple(row["reasons"]))
        for row in planning["excluded_facilities"]
    )
    planning["solver_settings"] = SolverSettings(**planning["solver_settings"])
    candidates = []
    for raw in read("catalog.json")["candidates"]:
        row = dict(raw)
        row["confirmed_at"] = datetime.fromisoformat(row["confirmed_at"])
        row["resource_effects"] = tuple(Effect(**effect) for effect in row["resource_effects"])
        row["requires_candidate_ids"] = tuple(row["requires_candidate_ids"])
        candidates.append(Candidate(**row))
    order = [
        "INV-B-BUY-5-MONITORS",
        "INV-B-BUY-1-MONITOR",
        "INV-B-REPAIR-5-IDLE",
        "INV-B-COMMISSION-5-REPAIRED",
    ]
    candidates.sort(key=lambda c: order.index(c.candidate_id))
    return Problem(
        **planning,
        candidates=tuple(candidates),
        snapshots=tuple(
            FacilitySnapshotResponse.model_validate(row)
            for row in read("post-allocation-snapshots.json")
        ),
        requirement_profiles=(ServiceRequirement.model_validate(read("requirement-profile.json")),),
    )


def candidate(data, cid, **changes):
    return replace(
        data,
        candidates=tuple(
            replace(c, **changes) if c.candidate_id == cid else c for c in data.candidates
        ),
    )


def resource(data, fid, rid, **changes):
    snapshots = tuple(
        s.model_copy(
            update={
                "resources": [
                    r.model_copy(update=changes) if r.resource_id == rid else r for r in s.resources
                ]
            }
        )
        if s.facility.facility_id == fid
        else s
        for s in data.snapshots
    )
    return replace(data, snapshots=snapshots)


def ids(result):
    return {p.candidate_id for p in result.selected_projects}


def test_shared_demo_repairs_and_commissions_for_2400_without_mutating_source():
    data = problem()
    original = [s.model_dump() for s in data.snapshots]
    result = solve(data)
    assert result.solver_status == "optimal" and result.plan_outcome == "improved"
    assert ids(result) == {"INV-B-REPAIR-5-IDLE", "INV-B-COMMISSION-5-REPAIRED"}
    assert (
        result.total_capital_cost_minor_units,
        result.total_operating_cost_minor_units,
        result.total_cost_minor_units,
        result.remaining_budget_minor_units,
    ) == (150000, 90000, 240000, 60000)
    assert (
        result.baseline_summary.covered_service_places,
        result.proposed_summary.covered_service_places,
        result.proposed_summary.unmet_service_places,
    ) == (6, 11, 0)
    rows = {r.facility_id: r for r in result.proposed_summary.rows}
    assert rows["DEMO-A"].estimated_capacity == 3
    assert rows["DEMO-B"].estimated_capacity == 8
    commissioned = next(
        p
        for p in result.selected_projects
        if p.candidate_id.startswith("INV-B-COMMISSION-5-REPAIRED")
    )
    assert commissioned.ready_at == data.planning_starts_at + timedelta(days=10)
    assert result.validation_passed and result.review_required
    assert len(result.objectives_proven) == 3
    assert [s.model_dump() for s in data.snapshots] == original
    assert result.coverage.excluded_facilities[0].identifier == "DEMO-C"


@pytest.mark.parametrize(
    "budget,expected,gap",
    [
        (0, set(), 5),
        (117999, set(), 5),
        (118000, {"INV-B-BUY-1-MONITOR"}, 4),
        (239999, {"INV-B-BUY-1-MONITOR"}, 4),
        (240000, {"INV-B-REPAIR-5-IDLE", "INV-B-COMMISSION-5-REPAIRED"}, 0),
    ],
)
def test_budget_includes_full_operating_allowance(budget, expected, gap):
    result = solve(replace(problem(), budget_minor_units=budget))
    assert result.solver_status == "optimal" and ids(result) == expected
    assert result.proposed_summary.unmet_service_places == gap


@pytest.mark.parametrize(
    "days,expected",
    [
        (6, set()),
        (7, set()),
        (9, set()),
        (10, {"INV-B-REPAIR-5-IDLE", "INV-B-COMMISSION-5-REPAIRED"}),
    ],
)
def test_only_fully_commissioned_projects_contribute_by_exact_deadline(days, expected):
    data = problem()
    result = solve(replace(data, evaluation_at=data.planning_starts_at + timedelta(days=days)))
    assert ids(result) == expected
    if days < 10:
        assert result.plan_outcome == "no_improvement"
        excluded = {e.identifier: e.reasons for e in result.coverage.excluded_candidates}
        assert "ready_after_evaluation" in excluded["INV-B-COMMISSION-5-REPAIRED"]


def test_repair_only_has_no_capacity_effect_and_is_not_bought():
    data = replace(problem(), candidates=(problem().candidates[2],))
    result = solve(data)
    assert ids(result) == set() and result.plan_outcome == "no_improvement"
    assert result.total_cost_minor_units == 0


def test_more_operating_months_changes_recommendation():
    result = solve(replace(problem(), operating_cost_months=6))
    assert ids(result) == {"INV-B-BUY-1-MONITOR"}
    assert result.total_cost_minor_units == 136000


@pytest.mark.parametrize("rid,quantity", [("available-beds", 3.0), ("nurses-on-duty", 1.5)])
def test_non_target_bottlenecks_prevent_false_monitor_benefits(rid, quantity):
    data = resource(problem(), "DEMO-B", rid, available_quantity=quantity)
    result = solve(data)
    assert result.solver_status == "optimal" and result.plan_outcome == "no_improvement"
    assert not result.selected_projects


def test_jointly_useful_bundles_overcome_two_bottlenecks():
    data = resource(problem(), "DEMO-B", "nurses-on-duty", available_quantity=1.0)
    monitor = replace(
        data.candidates[1],
        capital_cost_minor_units=100,
        monthly_operating_cost_minor_units=0,
        implementation_days=0,
        exclusive_group_id=None,
        resource_effects=(Effect("working-monitors", 5, "item"),),
    )
    nurses = replace(
        monitor,
        candidate_id="ADD-NURSES",
        resource_effects=(Effect("nurses-on-duty", 3, "person"),),
    )
    data = replace(data, candidates=(monitor, nurses), budget_minor_units=200)
    assert ids(solve(data)) == {monitor.candidate_id, nurses.candidate_id}
    assert solve(data).proposed_summary.covered_service_places == 11
    for project in (monitor, nurses):
        assert (
            solve(replace(data, candidates=(project,))).proposed_summary.covered_service_places < 11
        )


def test_shared_prerequisite_is_charged_once_and_latest_dependency_sets_readiness():
    data = problem()
    repair = data.candidates[2]
    first = replace(
        data.candidates[3],
        candidate_id="INV-B-COMMISSION-5-REPAIRED-THREE",
        exclusive_group_id=None,
        resource_effects=(Effect("working-monitors", 3, "item"),),
        capital_cost_minor_units=100,
        monthly_operating_cost_minor_units=0,
    )
    second = replace(
        first,
        candidate_id="INV-B-COMMISSION-5-REPAIRED-TWO",
        implementation_days=4,
        resource_effects=(Effect("working-monitors", 2, "item"),),
    )
    result = solve(replace(data, candidates=(repair, first, second)))
    assert ids(result) == {repair.candidate_id, first.candidate_id, second.candidate_id}
    assert result.total_cost_minor_units == 100200
    assert next(
        p for p in result.selected_projects if p.candidate_id == second.candidate_id
    ).ready_at == (data.planning_starts_at + timedelta(days=11))


def test_exclusive_asset_alternatives_cannot_double_count_same_idle_monitors():
    data = problem()
    commission = replace(data.candidates[3], exclusive_group_id="DEMO-B-IDLE-MONITORS")
    alternative = replace(
        commission,
        candidate_id="OTHER-INV-B-COMMISSION-5-REPAIRED",
        capital_cost_minor_units=1,
        monthly_operating_cost_minor_units=0,
    )
    data = replace(
        data,
        candidates=(replace(data.candidates[2], exclusive_group_id=None), commission, alternative),
        required_service_places={"DEMO-A": 3, "DEMO-B": 15},
        budget_minor_units=1000000,
    )
    result = solve(data)
    assert ids(result) == {"INV-B-REPAIR-5-IDLE", "OTHER-INV-B-COMMISSION-5-REPAIRED"}
    assert result.proposed_summary.rows[1].estimated_capacity == 8


@pytest.mark.parametrize(
    "field,value", [("source_note", None), ("source_note", "  "), ("confirmed_at", None)]
)
def test_missing_confirmation_excludes_project_and_dependents(field, value):
    data = candidate(problem(), "INV-B-REPAIR-5-IDLE", **{field: value})
    result = solve(data)
    assert ids(result) == {"INV-B-BUY-1-MONITOR"}
    excluded = {e.identifier: e.reasons for e in result.coverage.excluded_candidates}
    assert "missing_candidate_confirmation" in excluded["INV-B-REPAIR-5-IDLE"]
    assert "prerequisite_ineligible" in excluded["INV-B-COMMISSION-5-REPAIRED"]


@pytest.mark.parametrize("kind", ["stale", "unknown", "closed", "limited", "demand", "profile"])
def test_missing_or_excluded_evidence_is_never_fixed_by_purchasing_equipment(kind):
    data = problem()
    if kind in ("stale", "unknown"):
        data = resource(
            data,
            "DEMO-B",
            "working-monitors",
            data_status=kind,
            available_quantity=None if kind == "unknown" else 3.0,
        )
    elif kind in ("closed", "limited"):
        snapshot = data.snapshots[1]
        snapshot = snapshot.model_copy(
            update={
                "services": [
                    s.model_copy(
                        update={"status": "unavailable" if kind == "closed" else "limited"}
                    )
                    for s in snapshot.services
                ]
            }
        )
        data = replace(data, snapshots=(data.snapshots[0], snapshot, data.snapshots[2]))
    elif kind == "demand":
        data = replace(data, required_service_places={"DEMO-A": 3, "DEMO-B": None})
    else:
        data = replace(data, requirement_profiles=())
    result = solve(data)
    assert "DEMO-B" not in result.coverage.included_facility_ids
    assert not result.selected_projects
    if kind == "profile":
        assert result.solver_status == "not_run" and result.plan_outcome == "needs_inputs"
        assert result.proposed_summary is None
    else:
        assert result.baseline_summary.required_service_places == 3  # excludes B's unknown demand


def test_empty_and_zero_benefit_catalog_produces_valid_do_nothing_plan():
    data = problem()
    for candidates in ((), (replace(data.candidates[1], resource_effects=()),)):
        result = solve(replace(data, candidates=candidates))
        assert result.solver_status == "optimal" and result.plan_outcome == "no_improvement"
        assert not result.selected_projects and result.validation_passed


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "unknown",
        "self",
        "cycle",
        "unit",
        "resource",
        "duplicate_effect",
        "negative",
        "fraction",
        "bool",
        "service",
        "facility",
        "time",
    ],
)
def test_invalid_project_inputs_are_rejected(fault):
    data = problem()
    cid = data.candidates[0].candidate_id
    changes = {}
    if fault == "duplicate":
        data = replace(data, candidates=(*data.candidates, data.candidates[0]))
    elif fault in ("unknown", "self", "cycle"):
        dep = "UNKNOWN" if fault == "unknown" else cid if fault == "self" else "INV-B-BUY-1-MONITOR"
        changes["requires_candidate_ids"] = (dep,)
        if fault == "cycle":
            data = candidate(data, "INV-B-BUY-1-MONITOR", requires_candidate_ids=(cid,))
    elif fault in ("unit", "resource", "duplicate_effect", "negative", "fraction", "bool"):
        effect = Effect(
            "UNKNOWN" if fault == "resource" else "working-monitors",
            -1
            if fault == "negative"
            else 1.5
            if fault == "fraction"
            else True
            if fault == "bool"
            else 5,
            "bed" if fault == "unit" else "item",
        )
        changes["resource_effects"] = (effect, effect) if fault == "duplicate_effect" else (effect,)
    elif fault == "service":
        changes["service_id"] = "OTHER-SERVICE"
    elif fault == "facility":
        changes["facility_id"] = "UNKNOWN"
    else:
        changes["confirmed_at"] = data.planning_starts_at.replace(tzinfo=None)
    data = candidate(data, cid, **changes)
    with pytest.raises(InvestmentValidationError):
        solve(data)


@pytest.mark.parametrize(
    "changes",
    [
        {"budget_minor_units": -1},
        {"budget_minor_units": True},
        {"operating_cost_months": 0},
        {"operating_cost_months": 1.5},
        {"currency": "EUR"},
        {"capacity_unit": "patient"},
        {"included_facility_ids": ("DEMO-A", "UNKNOWN")},
        {"solver_settings": SolverSettings(time_limit_seconds=6)},
        {"solver_settings": SolverSettings(time_limit_seconds=float("nan"))},
        {"solver_settings": SolverSettings(num_search_workers=2)},
    ],
)
def test_invalid_global_constraints_are_rejected(changes):
    with pytest.raises(InvestmentValidationError):
        solve(replace(problem(), **changes))


@pytest.mark.parametrize(
    "selected,changes",
    [
        (("INV-B-COMMISSION-5-REPAIRED",), {}),
        (("UNKNOWN",), {}),
        (("INV-B-BUY-1-MONITOR", "INV-B-BUY-1-MONITOR"), {}),
        (("INV-B-BUY-5-MONITORS", "INV-B-BUY-1-MONITOR"), {"budget_minor_units": 1000000}),
        (("INV-B-BUY-5-MONITORS",), {}),
    ],
)
def test_independent_checker_rejects_invalid_selections(selected, changes):
    data = problem()
    if selected == ("INV-B-BUY-5-MONITORS", "INV-B-BUY-1-MONITOR"):
        data = candidate(data, "INV-B-BUY-5-MONITORS", exclusive_group_id="PURCHASE-ALTERNATIVE")
        data = candidate(data, "INV-B-BUY-1-MONITOR", exclusive_group_id="PURCHASE-ALTERNATIVE")
    with pytest.raises(InvestmentValidationError):
        check(replace(data, **changes), selected)


def test_datetime_ordering_and_missing_source_coverage():
    data = problem()
    with pytest.raises(InvestmentValidationError):
        solve(replace(data, evaluation_at=data.planning_starts_at - timedelta(seconds=1)))
    with pytest.raises(InvestmentValidationError):
        solve(replace(data, planning_starts_at=data.planning_starts_at.replace(tzinfo=None)))
    empty = replace(
        data,
        included_facility_ids=(),
        excluded_facilities=(
            Exclusion("DEMO-A", ("missing_required_evidence",)),
            Exclusion("DEMO-B", ("missing_required_evidence",)),
            *data.excluded_facilities,
        ),
    )
    result = solve(empty)
    assert result.plan_outcome == "needs_inputs" and result.proposed_summary is None


@pytest.mark.parametrize(
    "status,expected", [(cp_model.UNKNOWN, "unknown"), (cp_model.INFEASIBLE, "infeasible")]
)
def test_no_incumbent_is_not_published(monkeypatch, status, expected):
    monkeypatch.setattr(cp_model.CpSolver, "solve", lambda self, model: status)
    result = solve(problem())
    assert result.solver_status == expected and result.plan_outcome == "no_solution"
    assert result.proposed_summary is None and not result.selected_projects
    assert not result.validation_passed


def test_model_invalid_is_internal_failure(monkeypatch):
    monkeypatch.setattr(cp_model.CpSolver, "solve", lambda self, model: cp_model.MODEL_INVALID)
    with pytest.raises(InvestmentSolverError):
        solve(problem())


def test_feasible_incumbent_does_not_claim_or_freeze_optimal_objective(monkeypatch):
    real = cp_model.CpSolver.solve
    calls = []

    def feasible(self, model):
        calls.append(model)
        real(self, model)
        return cp_model.FEASIBLE

    monkeypatch.setattr(cp_model.CpSolver, "solve", feasible)
    result = solve(problem())
    assert result.solver_status == "feasible" and result.validation_passed
    assert not result.objectives_proven and len(calls) == 1


def test_secondary_timeout_keeps_valid_primary_incumbent(monkeypatch):
    real = cp_model.CpSolver.solve
    count = 0

    def timeout(self, model):
        nonlocal count
        count += 1
        return real(self, model) if count == 1 else cp_model.UNKNOWN

    monkeypatch.setattr(cp_model.CpSolver, "solve", timeout)
    result = solve(problem())
    assert result.solver_status == "feasible" and result.validation_passed
    assert result.objectives_proven == ("unmet_service_places",)


def test_sequential_solves_share_one_total_budget(monkeypatch):
    times = iter([0.0, 0.0, 6.0, 6.0])
    monkeypatch.setattr(investments, "monotonic", lambda: next(times))
    result = solve(problem())
    assert result.solver_status == "feasible" and result.solve_duration_ms == 6000
    assert result.objectives_proven == ("unmet_service_places",)


def test_solver_matches_exhaustive_tiny_package_search_across_budgets_and_deadlines():
    data = problem()
    for budget, days in itertools.product(
        (0, 100000, 118000, 239999, 240000, 300000, 1000000), (0, 7, 9, 10, 14, 30)
    ):
        inputs = replace(
            data,
            budget_minor_units=budget,
            evaluation_at=data.planning_starts_at + timedelta(days=days),
        )
        ranks = []
        for bits in itertools.product((False, True), repeat=len(data.candidates)):
            chosen = tuple(c.candidate_id for c, take in zip(data.candidates, bits) if take)
            try:
                summary, projects = check(inputs, chosen)
                ranks.append(
                    (
                        summary.unmet_service_places,
                        sum(p.total_cost_minor_units for p in projects),
                        len(projects),
                    )
                )
            except InvestmentValidationError:
                pass
        result = solve(inputs)
        assert result.solver_status == "optimal"
        assert (
            result.proposed_summary.unmet_service_places,
            result.total_cost_minor_units,
            len(result.selected_projects),
        ) == min(ranks)


def test_fixture_expectations_match_numeric_result():
    expected = read("demo-expectations.json")
    result = solve(problem())
    assert sorted(ids(result)) == expected["selected_candidate_ids"]
    assert result.total_cost_minor_units == expected["total_cost_minor_units"]
    assert result.proposed_summary.unmet_service_places == expected["unmet_service_places"]
    assert asdict(result.baseline_summary) == asdict(check(problem(), ())[0])


def test_cost_tie_prefers_fewer_projects_and_free_irrelevant_work_is_omitted():
    data = problem()
    data = candidate(
        data,
        "INV-B-BUY-5-MONITORS",
        capital_cost_minor_units=240000,
        monthly_operating_cost_minor_units=0,
    )
    free = replace(
        data.candidates[2], candidate_id="IRRELEVANT-FREE-WORK", capital_cost_minor_units=0
    )
    result = solve(replace(data, candidates=(*data.candidates, free)))
    assert ids(result) == {"INV-B-BUY-5-MONITORS"}
    assert result.total_cost_minor_units == 240000


def test_latest_of_multiple_prerequisites_controls_commissioning_date():
    data = problem()
    enabling = replace(
        data.candidates[2],
        candidate_id="ENABLE-SITE",
        implementation_days=10,
        capital_cost_minor_units=0,
        exclusive_group_id=None,
    )
    commission = replace(
        data.candidates[3], requires_candidate_ids=("INV-B-REPAIR-5-IDLE", "ENABLE-SITE")
    )
    data = replace(data, candidates=(data.candidates[2], enabling, commission))
    early = solve(replace(data, evaluation_at=data.planning_starts_at + timedelta(days=12)))
    assert not early.selected_projects and early.plan_outcome == "no_improvement"
    timely = solve(replace(data, evaluation_at=data.planning_starts_at + timedelta(days=13)))
    assert ids(timely) == {"INV-B-REPAIR-5-IDLE", "ENABLE-SITE", "INV-B-COMMISSION-5-REPAIRED"}
    assert next(
        p for p in timely.selected_projects if p.candidate_id == commission.candidate_id
    ).ready_at == (data.planning_starts_at + timedelta(days=13))


def test_single_bundle_applies_all_effects_once_and_verifies_capacity():
    data = resource(problem(), "DEMO-B", "nurses-on-duty", available_quantity=1.0)
    bundle = replace(
        data.candidates[1],
        resource_effects=(
            Effect("working-monitors", 5, "item"),
            Effect("nurses-on-duty", 3, "person"),
        ),
    )
    result = solve(replace(data, candidates=(bundle,)))
    assert result.proposed_summary.rows[1].estimated_capacity == 8
    assert result.proposed_summary.rows[1].resource_quantities["nurses-on-duty"] == 4
    assert result.proposed_summary.rows[1].resource_quantities["working-monitors"] == 8
    assert result.total_cost_minor_units == 118000


def test_zero_availability_stays_known_and_can_be_improved_by_confirmed_project():
    data = resource(problem(), "DEMO-B", "working-monitors", available_quantity=0.0)
    result = solve(data)
    assert result.baseline_summary.rows[1].estimated_capacity == 0
    assert "DEMO-B" in result.coverage.included_facility_ids
    assert result.proposed_summary.rows[1].estimated_capacity == 5


def test_exact_fractional_profile_is_scaled_and_verified_independently():
    data = problem()
    profile = data.requirement_profiles[0]
    profile = profile.model_copy(
        update={
            "requirements": [
                rule.model_copy(update={"required_per_capacity_unit": 1.5})
                if rule.resource_id == "working-monitors"
                else rule
                for rule in profile.requirements
            ]
        }
    )
    result = solve(replace(data, requirement_profiles=(profile,)))
    assert result.baseline_summary.rows[1].estimated_capacity == 2
    assert result.proposed_summary.rows[1].estimated_capacity == 5  # floor(8 / 1.5)


def test_inherited_exclusion_stays_excluded_even_if_snapshot_is_known():
    data = problem()
    project = replace(data.candidates[1], candidate_id="BUY-FOR-A", facility_id="DEMO-A")
    data = replace(
        data,
        candidates=(project,),
        included_facility_ids=("DEMO-B",),
        excluded_facilities=(Exclusion("DEMO-A", ("source_excluded",)), *data.excluded_facilities),
    )
    result = solve(data)
    assert result.coverage.included_facility_ids == ("DEMO-B",)
    assert not result.selected_projects
    assert "facility_excluded" in result.coverage.excluded_candidates[0].reasons


def test_very_small_time_budget_is_unknown_not_an_invented_proposal():
    result = solve(replace(problem(), solver_settings=SolverSettings(time_limit_seconds=1e-12)))
    assert result.solver_status == "unknown" and result.plan_outcome == "no_solution"
    assert result.proposed_summary is None and not result.validation_passed


def test_frontend_display_uses_same_catalog_and_numeric_expectations():
    root = FIXTURES.parents[2]
    preview = json.loads((root / "apps/web/src/features/investments/demo-display.json").read_text())
    inputs = preview["input"]
    for row, shared in zip(inputs["candidates"], read("catalog.json")["candidates"], strict=True):
        normalized = dict(row)
        for field in (
            "capital_cost_minor_units",
            "monthly_operating_cost_minor_units",
            "implementation_days",
        ):
            normalized[field] = int(normalized[field])
        normalized["resource_effects"] = [
            {**effect, "quantity_delta": int(effect["quantity_delta"])}
            for effect in normalized["resource_effects"]
        ]
        assert normalized == shared
    result = solve(problem())
    assert sorted(ids(result)) == sorted(p["candidate_id"] for p in preview["selected_projects"])
    assert result.total_cost_minor_units == preview["total_cost_minor_units"]
    assert (
        result.proposed_summary.covered_service_places
        == preview["proposed"]["covered_service_places"]
    )
    assert (
        result.proposed_summary.unmet_service_places == preview["proposed"]["unmet_service_places"]
    )
    assert {
        p.candidate_id: p.ready_at.isoformat().replace("+00:00", "Z")
        for p in result.selected_projects
    } == {p["candidate_id"]: p["ready_at"] for p in preview["selected_projects"]}
