"""Pure numerical tests; fixture records stand in for pending backend engine types."""

import itertools
import json
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

import pytest
from allocation_fixture_types import (
    AllocationEngineInput,
    ApprovedRoute,
    FacilityConstraint,
    SolverSettings,
)
from ortools.sat.python import cp_model

from app.engines import allocation
from app.modules.capacity.schemas import ServiceRequirement
from app.modules.facilities.schemas import FacilitySnapshotResponse

ROOT = Path(__file__).resolve().parents[3] / "data/synthetic/feature-6"


def fixture_input():
    planning = json.loads((ROOT / "planning-constraints.json").read_text())
    constraints = tuple(
        FacilityConstraint(
            **{
                **row,
                "confirmed_at": datetime.fromisoformat(row["confirmed_at"].replace("Z", "+00:00")),
            }
        )
        for row in planning.pop("facility_constraints")
    )
    routes = tuple(
        ApprovedRoute(
            **{
                **row,
                "confirmed_at": datetime.fromisoformat(row["confirmed_at"].replace("Z", "+00:00")),
            }
        )
        for row in planning.pop("routes")
    )
    return AllocationEngineInput(
        **planning,
        facility_constraints=constraints,
        routes=routes,
        snapshots=tuple(
            FacilitySnapshotResponse.model_validate(row)
            for row in json.loads((ROOT / "effective-snapshots.json").read_text())
        ),
        requirement_profiles=(
            ServiceRequirement.model_validate(
                json.loads((ROOT / "requirement-profile.json").read_text())
            ),
        ),
    )


def solve(data):
    return allocation._optimize_allocation(data)


def change_constraint(data, fid, **updates):
    return replace(
        data,
        facility_constraints=tuple(
            replace(c, **updates) if c.facility_id == fid else c for c in data.facility_constraints
        ),
    )


def change_resource(data, fid, rid, **updates):
    return replace(
        data,
        snapshots=tuple(
            s.model_copy(
                update={
                    "resources": [
                        r.model_copy(update=updates) if r.resource_id == rid else r
                        for r in s.resources
                    ]
                }
            )
            if s.facility.facility_id == fid
            else s
            for s in data.snapshots
        ),
    )


def change_service(data, fid, status):
    return replace(
        data,
        snapshots=tuple(
            s.model_copy(
                update={"services": [v.model_copy(update={"status": status}) for v in s.services]}
            )
            if s.facility.facility_id == fid
            else s
            for s in data.snapshots
        ),
    )


def test_one_monitor_demo_matches_capacity_and_coverage_without_mutation():
    data = fixture_input()
    before = deepcopy(data)
    result = solve(data)
    assert result.solver_status == "optimal" and result.plan_outcome == "improved"
    assert result.baseline_summary.covered_service_places == 5
    assert result.baseline_summary.unmet_service_places == 6
    assert result.proposed_summary.covered_service_places == 6
    assert result.proposed_summary.unmet_service_places == 5
    assert [
        (row.facility_id, row.estimated_capacity) for row in result.proposed_summary.facilities
    ] == [("DEMO-A", 3), ("DEMO-B", 3)]
    assert result.transfers[0].quantity == 1 and result.total_cost_minor_units == 10000
    assert result.validation_passed and result.review_required
    assert result.coverage.included_facility_ids == ("DEMO-A", "DEMO-B")
    assert result.coverage.excluded_facilities[0].facility_id == "DEMO-C"
    assert "service_unavailable" in result.coverage.excluded_facilities[0].reason_codes
    assert result.objectives_proven == ("unmet_service_places", "transfer_cost", "moved_items")
    assert allocation.validate_transfer_plan(data, result.transfers) == result.proposed_summary
    assert data == before


@pytest.mark.parametrize(
    "constraint,value",
    [
        ("transferable_quantity", 0),
        ("minimum_retained_service_places", 4),
        ("minimum_retained_resource_quantity", 4),
        ("required_service_places", 5),
    ],
)
def test_donor_protection_prevents_withdrawal(constraint, value):
    data = change_constraint(fixture_input(), "DEMO-A", **{constraint: value})
    result = solve(data)
    assert result.transfers == () and result.plan_outcome == "no_improvement"
    assert result.solver_status == "optimal"


@pytest.mark.parametrize("case", ["budget", "deadline", "receiving", "route", "beds", "nurses"])
def test_binding_limits_and_other_resources_prevent_beneficial_transfer(case):
    data = fixture_input()
    if case == "budget":
        data = replace(data, budget_minor_units=9999)
    elif case == "deadline":
        data = replace(data, planning_horizon_minutes=29)
    elif case == "receiving":
        data = change_constraint(data, "DEMO-B", maximum_inbound_quantity=0)
    elif case == "route":
        data = replace(data, routes=(replace(data.routes[0], maximum_quantity=0),))
    else:
        rid, quantity = ("available-beds", 2.0) if case == "beds" else ("nurses-on-duty", 1.0)
        data = change_resource(data, "DEMO-B", rid, available_quantity=quantity)
    result = solve(data)
    assert result.plan_outcome == "no_improvement" and result.transfers == ()
    assert result.validation_passed


@pytest.mark.parametrize("status", ["unavailable", "limited"])
def test_monitors_cannot_reopen_closed_or_unquantified_service(status):
    result = solve(change_service(fixture_input(), "DEMO-B", status))
    assert result.coverage.included_facility_ids == ("DEMO-A",)
    assert result.transfers == ()
    assert any(row.facility_id == "DEMO-B" for row in result.coverage.excluded_facilities)


@pytest.mark.parametrize("kind", ["stale", "unknown", "planning", "profile"])
def test_missing_inputs_exclude_facility_without_counting_its_demand_as_zero(kind):
    data = fixture_input()
    if kind in ("stale", "unknown"):
        data = change_resource(
            data,
            "DEMO-B",
            "nurses-on-duty",
            data_status=kind,
            available_quantity=None if kind == "unknown" else 9.0,
        )
    elif kind == "planning":
        data = change_constraint(data, "DEMO-B", required_service_places=None)
    elif kind == "profile":
        data = replace(data, requirement_profiles=())
    else:
        data = change_constraint(data, "DEMO-B", minimum_retained_resource_quantity=99)
    result = solve(data)
    assert "DEMO-B" not in result.coverage.included_facility_ids
    assert "incomplete_network_coverage" in result.remaining_gap_reasons
    assert result.baseline_summary.unmet_service_places == 0
    if kind == "profile":
        assert result.plan_outcome == "needs_inputs" and result.solver_status == "not_run"
        assert result.proposed_summary is None and not result.validation_passed


def test_fractional_profile_scaled_exactly_and_recomputed_with_capacity_engine():
    data = fixture_input()
    profile = data.requirement_profiles[0]
    profile = profile.model_copy(
        update={
            "requirements": [
                r.model_copy(update={"required_per_capacity_unit": 1.5})
                if r.resource_id == "working-monitors"
                else r
                for r in profile.requirements
            ]
        }
    )
    data = change_constraint(
        data,
        "DEMO-A",
        required_service_places=1,
        minimum_retained_service_places=1,
        minimum_retained_resource_quantity=1,
    )
    result = solve(replace(data, requirement_profiles=(profile,)))
    assert result.proposed_summary.covered_service_places == 3
    assert result.baseline_summary.covered_service_places == 2
    assert result.transfers[0].quantity == 1


def test_combined_withdrawals_protect_donor_across_multiple_routes():
    data = fixture_input()
    data = change_service(data, "DEMO-C", "operating")
    data = change_resource(
        data, "DEMO-C", "available-beds", available_quantity=12.0, data_status="current"
    )
    data = change_resource(
        data, "DEMO-C", "nurses-on-duty", available_quantity=6.0, data_status="current"
    )
    data = change_resource(
        data, "DEMO-C", "working-monitors", available_quantity=0.0, data_status="current"
    )
    extra = replace(
        data.facility_constraints[1],
        facility_id="DEMO-C",
        required_service_places=8,
        minimum_retained_resource_quantity=0,
    )
    data = replace(
        data,
        facility_constraints=(*data.facility_constraints, extra),
        routes=(*data.routes, replace(data.routes[0], route_id="A-TO-C", to_facility_id="DEMO-C")),
        budget_minor_units=20000,
    )
    data = change_constraint(data, "DEMO-A", transferable_quantity=4)
    result = solve(data)
    assert sum(t.quantity for t in result.transfers) == 1
    assert (
        next(
            row for row in result.proposed_summary.facilities if row.facility_id == "DEMO-A"
        ).estimated_capacity
        == 3
    )


def test_original_inventory_cannot_be_reexported():
    data = change_service(fixture_input(), "DEMO-C", "operating")
    data = change_resource(
        data, "DEMO-C", "available-beds", available_quantity=12.0, data_status="current"
    )
    data = change_resource(
        data, "DEMO-C", "nurses-on-duty", available_quantity=6.0, data_status="current"
    )
    data = change_resource(
        data, "DEMO-C", "working-monitors", available_quantity=0.0, data_status="current"
    )
    data = change_resource(data, "DEMO-B", "working-monitors", available_quantity=0.0)
    extra = replace(
        data.facility_constraints[1],
        facility_id="DEMO-C",
        required_service_places=8,
        minimum_retained_resource_quantity=0,
    )
    data = replace(
        data,
        facility_constraints=(*data.facility_constraints, extra),
        routes=(
            data.routes[0],
            replace(
                data.routes[0],
                route_id="B-TO-C",
                from_facility_id="DEMO-B",
                to_facility_id="DEMO-C",
            ),
        ),
        budget_minor_units=20000,
    )
    data = change_constraint(
        data,
        "DEMO-B",
        required_service_places=0,
        transferable_quantity=10,
        minimum_retained_resource_quantity=0,
    )
    result = solve(data)
    assert result.transfers == ()  # A->B has no benefit; B has no original equipment to export.


def three_operating(data):
    data = change_service(data, "DEMO-C", "operating")
    data = change_resource(
        data, "DEMO-C", "available-beds", available_quantity=12.0, data_status="current"
    )
    data = change_resource(
        data, "DEMO-C", "nurses-on-duty", available_quantity=6.0, data_status="current"
    )
    data = change_resource(
        data, "DEMO-C", "working-monitors", available_quantity=4.0, data_status="current"
    )
    third = replace(data.facility_constraints[0], facility_id="DEMO-C")
    return replace(data, facility_constraints=(*data.facility_constraints, third))


def test_equal_coverage_prefers_cheaper_approved_route():
    data = three_operating(fixture_input())
    cheap = replace(
        data.routes[0], route_id="C-TO-B", from_facility_id="DEMO-C", cost_per_unit_minor_units=1
    )
    data = replace(data, routes=(*data.routes, cheap))
    result = solve(data)
    assert result.proposed_summary.covered_service_places == 9
    assert [t.route_id for t in result.transfers] == ["C-TO-B"]
    assert result.total_cost_minor_units == 1


def test_final_tiebreaker_removes_free_unnecessary_moves_and_cycles():
    data = three_operating(fixture_input())
    data = change_constraint(data, "DEMO-A", maximum_inbound_quantity=1)
    data = change_constraint(data, "DEMO-C", maximum_inbound_quantity=1)
    zero = replace(data.routes[0], cost_per_unit_minor_units=0)
    data = replace(
        data,
        routes=(
            zero,
            replace(zero, route_id="C-TO-B", from_facility_id="DEMO-C"),
            replace(zero, route_id="A-TO-C", to_facility_id="DEMO-C"),
            replace(zero, route_id="C-TO-A", from_facility_id="DEMO-C", to_facility_id="DEMO-A"),
        ),
    )
    result = solve(data)
    assert sum(t.quantity for t in result.transfers) == 1
    assert result.total_cost_minor_units == 0
    assert len(result.objectives_proven) == 3


def test_aggregated_receipts_obey_one_shared_receiving_limit():
    data = three_operating(fixture_input())
    data = replace(
        data,
        budget_minor_units=20000,
        routes=(
            *data.routes,
            replace(data.routes[0], route_id="C-TO-B", from_facility_id="DEMO-C"),
        ),
    )
    result = solve(data)
    assert sum(t.quantity for t in result.transfers) == 1


def test_total_solver_budget_is_shared_across_lexicographic_stages(monkeypatch):
    times = iter([0.0, 0.0, 6.0, 6.0])
    monkeypatch.setattr(allocation, "monotonic", lambda: next(times))
    result = solve(fixture_input())
    assert result.solver_status == "feasible"
    assert result.objectives_proven == ("unmet_service_places",)
    assert result.validation_passed and result.solve_duration_ms == 6000


def test_submicrosecond_budget_reports_unknown_without_manufacturing_plan():
    result = solve(
        replace(fixture_input(), solver_settings=SolverSettings(time_limit_seconds=1e-12))
    )
    assert result.solver_status == "unknown" and result.plan_outcome == "no_solution"
    assert result.proposed_summary is None and result.transfers == ()


@pytest.mark.parametrize(
    "case", json.loads((ROOT / "engine-cases.json").read_text()), ids=lambda case: case["case"]
)
def test_published_numerical_examples_match_exactly(case):
    raw = deepcopy(case["input"])
    raw["snapshots"] = tuple(FacilitySnapshotResponse.model_validate(s) for s in raw["snapshots"])
    raw["requirement_profiles"] = tuple(
        ServiceRequirement.model_validate(p) for p in raw["requirement_profiles"]
    )
    for key, cls in (("facility_constraints", FacilityConstraint), ("routes", ApprovedRoute)):
        raw[key] = tuple(
            cls(
                **{
                    **row,
                    "confirmed_at": datetime.fromisoformat(
                        row["confirmed_at"].replace("Z", "+00:00")
                    ),
                }
            )
            for row in raw[key]
        )
    raw["solver_settings"] = SolverSettings(**raw["solver_settings"])
    result = asdict(solve(AllocationEngineInput(**raw)))
    for key in ("solve_duration_ms", "solver_version"):
        result.pop(key)
    # JSON normalizes tuple collections; duration/version are runtime metadata.
    assert json.loads(json.dumps(result)) == case["expected"]


def test_independent_validator_rejects_tampered_quantities_units_cost_and_unapproved_routes():
    data = fixture_input()
    transfer = solve(data).transfers[0]
    for update in (
        {"quantity": 2, "cost_minor_units": 20000},
        {"unit": "bed"},
        {"cost_minor_units": 0},
        {"route_id": "UNAPPROVED"},
        {"quantity": True},
    ):
        with pytest.raises(allocation.AllocationValidationError):
            allocation.validate_transfer_plan(data, (replace(transfer, **update),))
    with pytest.raises(allocation.AllocationValidationError):
        allocation.validate_transfer_plan(data, (transfer, transfer))


@pytest.mark.parametrize("status", [cp_model.UNKNOWN, cp_model.INFEASIBLE, cp_model.MODEL_INVALID])
def test_no_incumbent_and_invalid_model_statuses_are_distinct(monkeypatch, status):
    real = cp_model.CpSolver

    class FakeSolver:
        def __init__(self):
            self.parameters = real().parameters

        def solve(self, model):
            return status

    monkeypatch.setattr(cp_model, "CpSolver", FakeSolver)
    if status == cp_model.MODEL_INVALID:
        with pytest.raises(allocation.AllocationSolverError):
            solve(fixture_input())
    else:
        result = solve(fixture_input())
        assert result.solver_status == ("unknown" if status == cp_model.UNKNOWN else "infeasible")
        assert result.plan_outcome == "no_solution" and result.proposed_summary is None
        assert result.transfers == () and not result.validation_passed


def test_feasible_incumbent_not_called_optimal_and_not_frozen(monkeypatch):
    real, calls = cp_model.CpSolver, []

    class FeasibleSolver:
        def __init__(self):
            self.real = real()
            self.parameters = self.real.parameters

        def solve(self, model):
            calls.append(model)
            self.real.solve(model)
            return cp_model.FEASIBLE

        def value(self, expression):
            return self.real.value(expression)

    monkeypatch.setattr(cp_model, "CpSolver", FeasibleSolver)
    result = solve(fixture_input())
    assert len(calls) == 1 and result.objectives_proven == ()
    assert result.solver_status == "feasible" and result.validation_passed


def test_later_timeout_keeps_verified_incumbent_with_proof_scope(monkeypatch):
    real, calls = cp_model.CpSolver, []

    class LaterTimeout:
        def __init__(self):
            self.real = real()
            self.parameters = self.real.parameters

        def solve(self, model):
            calls.append(model)
            return self.real.solve(model) if len(calls) == 1 else cp_model.UNKNOWN

        def value(self, expression):
            return self.real.value(expression)

    monkeypatch.setattr(cp_model, "CpSolver", LaterTimeout)
    result = solve(fixture_input())
    assert len(calls) == 2
    assert result.solver_status == "feasible" and result.validation_passed
    assert result.objectives_proven == ("unmet_service_places",)
    assert result.proposed_summary.unmet_service_places == 5


def test_tiny_network_objectives_match_exhaustive_enumeration():
    for quantity, demand, budget, reserve in itertools.product(
        range(2, 6), (0, 2, 5), (0, 10000, 20000), (0, 1)
    ):
        data = fixture_input()
        data = change_resource(
            data, "DEMO-A", "working-monitors", available_quantity=float(quantity)
        )
        data = change_constraint(
            data,
            "DEMO-A",
            required_service_places=1,
            minimum_retained_service_places=1,
            minimum_retained_resource_quantity=reserve,
            transferable_quantity=quantity,
        )
        data = change_constraint(
            data, "DEMO-B", required_service_places=demand, maximum_inbound_quantity=2
        )
        data = replace(
            data, budget_minor_units=budget, routes=(replace(data.routes[0], maximum_quantity=2),)
        )
        expected = min(
            (max(0, demand - (2 + moved)), moved * 10000, moved)
            for moved in range(3)
            if quantity - moved >= max(1, reserve) and moved * 10000 <= budget
        )
        result = solve(data)
        assert (
            result.proposed_summary.unmet_service_places,
            result.total_cost_minor_units,
            sum(t.quantity for t in result.transfers),
        ) == expected


@pytest.mark.parametrize("bad", ["negative", "boolean", "duplicate", "self_route", "unit", "time"])
def test_malformed_numerical_inputs_rejected(bad):
    data = fixture_input()
    if bad == "negative":
        data = replace(data, budget_minor_units=-1)
    elif bad == "boolean":
        data = change_constraint(data, "DEMO-A", transferable_quantity=True)
    elif bad == "duplicate":
        data = replace(data, routes=(data.routes[0], data.routes[0]))
    elif bad == "self_route":
        data = replace(data, routes=(replace(data.routes[0], to_facility_id="DEMO-A"),))
    elif bad == "unit":
        data = change_resource(data, "DEMO-A", "working-monitors", unit="bed")
    else:
        data = replace(data, solver_settings=SolverSettings(time_limit_seconds=61))
    with pytest.raises(ValueError):
        solve(data)
