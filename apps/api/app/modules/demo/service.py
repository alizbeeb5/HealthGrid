"""Reproducible Beirut exercise, isolated from ordinary operational databases.

The launcher and stage endpoint own an outer SQLite transaction. Domain services
keep their normal commit behavior inside savepoints, so a failed exercise step
cannot leave a half-applied stage.
"""

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.allocation import service as allocation
from app.modules.allocation.schemas import AllocationRunRequest
from app.modules.decisions import service as decisions
from app.modules.decisions.schemas import (
    DecisionCreateRequest,
    DecisionEventRequest,
    OutcomeReviewRequest,
)
from app.modules.demo.models import DemoExercise
from app.modules.demo.schemas import AdvanceExercise, ExerciseContext
from app.modules.facilities import models as fm
from app.modules.facilities import service as facilities
from app.modules.facilities.schemas import ObservationCreate
from app.modules.forecasting.models import DailyResourceRecord, DailyServiceDemand
from app.modules.investments import service as investments
from app.modules.investments.schemas import InvestmentRunRequest
from app.modules.scenarios import service as scenarios
from app.modules.scenarios.schemas import IncidentConfirmRequest, IncidentDraftInput

PACK = Path(__file__).resolve().parents[5] / "data/synthetic/beirut-explosion"
EXERCISE_ID = "beirut-v1"


def at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read(name: str):
    return json.loads((PACK / name).read_text())


def require_exercise(db: Session) -> DemoExercise:
    if get_settings().demo_scenario != "beirut" or db.get_bind().dialect.name != "sqlite":
        raise HTTPException(404, "No isolated exercise is active.")
    row = db.get(DemoExercise, EXERCISE_ID)
    if row is None:
        raise HTTPException(503, "Prepare the Beirut exercise with the demo launcher first.")
    return row


def context(db: Session) -> ExerciseContext:
    if get_settings().demo_scenario != "beirut":
        return ExerciseContext(enabled=False)
    row = require_exercise(db)
    return ExerciseContext(enabled=True, phase=row.phase, clock=row.clock, **row.manifest)


def report_snapshots(db: Session, snapshots: list, now: datetime) -> None:
    """Explicit synthetic report arrival. Action approval never calls this."""
    for snapshot in snapshots:
        fid = snapshot["facility"]["facility_id"]
        for resource in snapshot["resources"]:
            if resource["available_quantity"] is None:
                continue
            facilities.create_observation(
                db,
                fid,
                ObservationCreate(
                    resource_id=resource["resource_id"],
                    available_quantity=float(resource["available_quantity"]),
                    unit=resource["unit"],
                    observed_at=now,
                ),
                now,
            )
        for service in snapshot["services"]:
            db.get(fm.FacilityService, (fid, service["service_id"])).status = service["status"]
    db.commit()


def ensure_history(db: Session, now: datetime) -> None:
    """Append synthetic complete days through yesterday; never rewrite stored history.

    Before the event, ordinary demand is used. Post-event history reflects the
    transfer-stage resource state and a separately specified demand series. No
    future recovery benefit leaks into historical inputs. Unknown staffing stays
    missing. This also repairs older exercise files with only 35 seeded days.
    """
    phases = read("snapshots.json")
    before = {s["facility"]["facility_id"]: s for s in phases["before"]}
    response = copy.deepcopy(phases["incident"])
    # Follow-up daily inputs use the saved response quantities, not a second solver.
    exercise = db.get(DemoExercise, EXERCISE_ID)
    if exercise is not None:
        plan = allocation.get_run(db, exercise.manifest["investment_input"]["allocation_run_id"])
        for snapshot in response:
            fid = snapshot["facility"]["facility_id"]
            for transfer in plan.transfers:
                for resource in snapshot["resources"]:
                    if resource["resource_id"] != transfer.resource_id:
                        continue
                    if fid == transfer.to_facility_id:
                        resource["available_quantity"] += transfer.quantity
                    elif fid == transfer.from_facility_id:
                        resource["available_quantity"] -= transfer.quantity
    after = {s["facility"]["facility_id"]: s for s in response}
    event_day = at("2020-08-04T00:00:00Z").date()
    day = event_day - timedelta(days=63)
    resource_keys = set(
        db.execute(
            select(
                DailyResourceRecord.facility_id,
                DailyResourceRecord.resource_id,
                DailyResourceRecord.record_date,
            )
        ).all()
    )
    demand_keys = set(
        db.execute(
            select(
                DailyServiceDemand.facility_id,
                DailyServiceDemand.service_id,
                DailyServiceDemand.record_date,
            )
        ).all()
    )
    while day < now.date():
        post_event = day >= event_day
        for fid, snapshot in (after if post_event else before).items():
            source = (
                "Beirut exercise: synthetic daily follow-up"
                if post_event
                else "Beirut exercise: synthetic pre-event history"
            )
            for resource in snapshot["resources"]:
                key = (fid, resource["resource_id"], day)
                if key in resource_keys or resource["available_quantity"] is None:
                    continue
                db.add(
                    DailyResourceRecord(
                        facility_id=fid,
                        resource_id=resource["resource_id"],
                        record_date=day,
                        available_quantity=resource["available_quantity"],
                        unit=resource["unit"],
                        source=source,
                        data_quality="estimated",
                        imported_at=now,
                    )
                )
            key = (fid, "emergency-care", day)
            if key not in demand_keys:
                demand = (
                    {
                        "BEI-WEST": 20,
                        "BEI-EAST": 16,
                        "BEI-MOUNT": 12,
                        "BEI-PORT": 0,
                        "BEI-UNCONFIRMED": 10,
                    }[fid]
                    if post_event
                    else 8 + ((event_day - day).days % 4)
                )
                db.add(
                    DailyServiceDemand(
                        facility_id=fid,
                        service_id="emergency-care",
                        record_date=day,
                        peak_required_places=demand,
                        service_status=snapshot["services"][0]["status"],
                        source=source,
                        data_quality="estimated",
                        imported_at=now,
                    )
                )
        day += timedelta(days=1)
    db.commit()


def seed(db: Session) -> ExerciseContext:
    if get_settings().demo_scenario != "beirut" or db.get_bind().dialect.name != "sqlite":
        raise ValueError(
            "Beirut seeding requires explicit demo mode and an isolated SQLite database."
        )
    if existing := db.get(DemoExercise, EXERCISE_ID):
        ensure_history(db, existing.clock)
        return context(db)
    if db.scalar(select(fm.Facility.facility_id).limit(1)) is not None:
        raise ValueError(
            "Refusing to seed over an existing hospital dataset. Use a fresh demo file."
        )
    phases = read("snapshots.json")
    for resource in read("resource-definitions.json"):
        db.add(fm.ResourceDefinition(**resource))
    db.add(fm.Service(service_id="emergency-care", name="Emergency stabilization"))
    for snapshot in phases["before"]:
        f = snapshot["facility"]
        db.add(fm.Facility(**{k: v for k, v in f.items() if k != "last_reported_at"}))
    db.flush()
    for snapshot in phases["before"]:
        fid = snapshot["facility"]["facility_id"]
        db.add(fm.FacilityService(facility_id=fid, service_id="emergency-care", status="operating"))
        for r in snapshot["resources"]:
            db.add(fm.FacilityResource(facility_id=fid, resource_id=r["resource_id"]))
    db.commit()
    report_snapshots(db, phases["before"], at("2020-08-04T14:00:00Z"))
    ensure_history(db, at("2020-08-04T16:10:00Z"))
    before = {s["facility"]["facility_id"]: s for s in phases["before"]}
    overrides = []
    for s in phases["incident"]:
        fid = s["facility"]["facility_id"]
        old = {r["resource_id"]: r for r in before[fid]["resources"]}
        for r in s["resources"]:
            if (
                r["available_quantity"] is not None
                and r["available_quantity"] != old[r["resource_id"]]["available_quantity"]
            ):
                overrides.append(
                    dict(
                        facility_id=fid,
                        resource_id=r["resource_id"],
                        available_quantity=r["available_quantity"],
                        unit=r["unit"],
                    )
                )
    incident = IncidentDraftInput(
        title="Beirut explosion exercise: interrupted care and receiving-hospital pressure",
        report_text=(
            "Synthetic exercise inspired by 4 August 2020. Port-area hospital emergency "
            "service is unavailable. West Beirut receiver has 8 working monitors. "
            "East Beirut receiver has 4 nurses assigned to emergency care and 16 monitors. "
            "Mount Lebanon reserve can release 8 monitors while protecting its own planned "
            "demand. The unconfirmed facility has no reliable nurse count. Quantities, routes "
            "and identities are fictional; confirm before planning."
        ),
        service_id="emergency-care",
        starts_at=at("2020-08-04T16:00:00Z"),
        expected_ends_at=at("2020-08-12T16:00:00Z"),
        affected_facility_ids=["BEI-EAST", "BEI-PORT", "BEI-WEST"],
        service_overrides=[
            dict(
                facility_id="BEI-PORT",
                service_id="emergency-care",
                status="unavailable",
                restriction_note=(
                    "Simulated structural and infrastructure damage; "
                    "not reopened by equipment delivery."
                ),
            )
        ],
        resource_overrides=overrides,
        assumptions=[
            "All operational inputs are fictional exercise assumptions.",
            (
                "Demand of 48 simultaneous places is assigned across three operating receivers; "
                "it is not a casualty count."
            ),
            "Recovery assumes the same demand at the evaluation date, not a forecast.",
        ],
    )
    now = at("2020-08-04T16:10:00Z")
    draft = scenarios.create_draft(db, incident, now)
    confirmed = scenarios.confirm(
        db,
        draft.incident_id,
        IncidentConfirmRequest(
            draft_revision_id=draft.revision_id,
            input=incident.model_dump(),
            confirmed_by="Exercise planner",
        ),
        now,
    )
    run, _ = scenarios.simulate(db, draft.incident_id, confirmed.revision_id, now)
    ai = read("allocation.input.json")
    ar = AllocationRunRequest(
        simulation_run_id=run.run_id,
        resource_id=ai["resource_id"],
        planning_horizon_minutes=ai["planning_horizon_minutes"],
        budget_minor_units=ai["budget_minor_units"],
        currency="USD",
        facility_constraints=[f["constraint"] for f in ai["facilities"] if f["constraint"]],
        routes=ai["routes"],
        assumptions=incident.assumptions,
    )
    alloc = allocation.create_run(db, ar, now)
    ii = read("investment.input.json")
    ir = InvestmentRunRequest(
        allocation_run_id=alloc.allocation_run_id,
        planning_starts_at=ii["planning_starts_at"],
        evaluation_at=ii["evaluation_at"],
        operating_cost_months=ii["operating_cost_months"],
        budget_minor_units=ii["budget_minor_units"],
        currency="USD",
        catalog_version="demo-beirut-v1",
        candidates=ii["candidates"],
        assumptions=incident.assumptions,
    )
    inv = investments.create_run(db, ir, now)
    transfer = decisions.create(
        db,
        DecisionCreateRequest(
            source_type="allocation",
            source_run_id=alloc.allocation_run_id,
            title="Protect receiver capacity: move eight monitors",
            owner_name="Exercise logistics coordinator",
            rationale="Reduce the monitor bottleneck while protecting the reserve hospital.",
            target_completion_at=at("2020-08-04T17:00:00Z"),
            actor_name="Exercise planner",
            prerequisite_decision_id=None,
            supersedes_decision_id=None,
        ),
        now,
    )
    recovery = decisions.create(
        db,
        DecisionCreateRequest(
            source_type="investment",
            source_run_id=inv.investment_run_id,
            title="Restore monitors and staff the remaining treatment places",
            owner_name="Exercise recovery coordinator",
            rationale="Equipment alone cannot resolve the East receiver staffing bottleneck.",
            target_completion_at=at(ii["evaluation_at"]),
            actor_name="Exercise planner",
            prerequisite_decision_id=transfer.decision_id,
            supersedes_decision_id=None,
        ),
        now,
    )
    roles = {
        "BEI-PORT": (
            "Service interrupted",
            "Physical resources do not establish a functioning service.",
            "Keep excluded from receiving plans until service is restored.",
        ),
        "BEI-WEST": (
            "Equipment bottleneck",
            "30 treatment spaces, but only 8 monitors constrain the initial estimate.",
            "Review the protected monitor transfer.",
        ),
        "BEI-EAST": (
            "Staff bottleneck",
            "16 monitors are available, but 4 assigned nurses limit capacity to 8.",
            "Fund confirmed staff coverage; more monitors alone do not help.",
        ),
        "BEI-MOUNT": (
            "Protected reserve",
            "Resources may support a receiver while retaining local capacity.",
            "Check donor reserves and the reviewed route.",
        ),
        "BEI-UNCONFIRMED": (
            "Report needed",
            "Required nurse evidence is missing.",
            "Request a resource update; unknown is not zero.",
        ),
    }
    manifest = dict(
        links={
            "overview": "/overview",
            "facilities": "/facilities",
            "forecasts": "/forecasts?facility_id=BEI-WEST&service_id=emergency-care",
            "scenarios": f"/scenarios?run_id={run.run_id}",
            "allocation": f"/allocation?proposal_id={alloc.allocation_run_id}",
            "investments": f"/investments?proposal_id={inv.investment_run_id}",
            "decisions": f"/decisions?decision_id={transfer.decision_id}",
        },
        hospitals=[
            dict(
                facility_id=s["facility"]["facility_id"],
                name=s["facility"]["name"],
                role=roles[s["facility"]["facility_id"]][0],
                cause=roles[s["facility"]["facility_id"]][1],
                next_action=roles[s["facility"]["facility_id"]][2],
            )
            for s in phases["before"]
        ],
        resources=read("resource-definitions.json"),
        metrics=[
            dict(
                label="Incident / no response",
                covered=alloc.baseline_summary.covered_service_places,
                unmet=alloc.baseline_summary.unmet_service_places,
                cost_minor_units=0,
            ),
            dict(
                label="Proposed immediate response",
                covered=alloc.proposed_summary.covered_service_places,
                unmet=alloc.proposed_summary.unmet_service_places,
                cost_minor_units=alloc.total_cost_minor_units,
            ),
            dict(
                label="Proposed recovery / 11 August",
                covered=inv.proposed_summary.covered_service_places,
                unmet=inv.proposed_summary.unmet_service_places,
                cost_minor_units=inv.total_cost_minor_units,
            ),
        ],
        incident_input=incident.model_dump(mode="json"),
        allocation_input=ar.model_dump(mode="json"),
        investment_input=ir.model_dump(mode="json"),
        allocation_decision_id=transfer.decision_id,
        investment_decision_id=recovery.decision_id,
    )
    assert [m["covered"] for m in manifest["metrics"]] == [28, 36, 48]
    report_snapshots(db, phases["incident"], at("2020-08-04T16:05:00Z"))
    db.add(DemoExercise(exercise_id=EXERCISE_ID, phase="assessment", clock=now, manifest=manifest))
    db.commit()
    return context(db)


def complete_exercise_decision(db: Session, decision_id: str, now: datetime) -> None:
    """Presenter-controlled rehearsal of human actions, visibly recorded as synthetic."""
    record = decisions.get(db, decision_id)

    def event(kind, extra=None):
        nonlocal record
        record, _ = decisions.apply_event(
            db,
            decision_id,
            DecisionEventRequest(
                event_type=kind,
                expected_version=record.version,
                request_id=f"EX-{record.version}-{decision_id}",
                actor_name="Synthetic exercise operator",
                note="Simulated rehearsal action, not an actual approval or delivery.",
                payload=dict(event_type=kind, **(extra or {})),
            ),
            now,
        )

    if record.status == "draft":
        event("submit")
    if record.status == "pending_review":
        event("approve")
    if record.status == "approved":
        event("start", dict(occurred_at=now))
    if record.status == "in_progress":
        for action in record.actions:
            if action.status in ("pending", "blocked"):
                event(
                    "update_action",
                    dict(
                        action_id=action.action_id,
                        status="in_progress",
                        occurred_at=now,
                        evidence_note=None,
                        actual_cost_minor_units=None,
                        blocker_note=None,
                    ),
                )
            if action.status != "completed":
                event(
                    "update_action",
                    dict(
                        action_id=action.action_id,
                        status="completed",
                        occurred_at=now,
                        evidence_note="Synthetic exercise completion report.",
                        actual_cost_minor_units=None,
                        blocker_note=None,
                    ),
                )
        event("complete", dict(occurred_at=now))
    if record.status != "completed":
        raise HTTPException(
            409,
            "The exercise decision was cancelled or rejected. Start a fresh rehearsal to advance.",
        )


def advance(db: Session, request: AdvanceExercise) -> ExerciseContext:
    row = require_exercise(db)
    if row.phase == request.target_phase:
        return context(db)  # repeat does not duplicate observations/events
    if row.phase != request.expected_phase or (row.phase, request.target_phase) not in (
        ("assessment", "response"),
        ("response", "recovery"),
    ):
        raise HTTPException(409, "The exercise has moved. Refresh before advancing.")
    manifest = copy.deepcopy(row.manifest)
    snapshots = copy.deepcopy(read("snapshots.json")["incident"])
    alloc = allocation.get_run(db, manifest["investment_input"]["allocation_run_id"])
    for transfer in alloc.transfers:
        for s in snapshots:
            for r in s["resources"]:
                if r["resource_id"] == transfer.resource_id:
                    if s["facility"]["facility_id"] == transfer.from_facility_id:
                        r["available_quantity"] -= transfer.quantity
                    if s["facility"]["facility_id"] == transfer.to_facility_id:
                        r["available_quantity"] += transfer.quantity
    if request.target_phase == "response":
        now = at("2020-08-04T17:00:00Z")
        complete_exercise_decision(db, manifest["allocation_decision_id"], now)
        report_snapshots(db, snapshots, now)
        manifest["links"]["decisions"] = (
            f"/decisions?decision_id={manifest['investment_decision_id']}"
        )
    else:
        now = at("2020-08-11T17:05:00Z")
        complete_exercise_decision(db, manifest["investment_decision_id"], now)
        review_args = dict(
            actor_name="Synthetic exercise operator",
            note="Exercise follow-up, not a historical hospital report.",
            observation_window_starts_at=at("2020-08-11T17:00:00Z"),
        )
        missing, _ = decisions.create_review(
            db,
            manifest["investment_decision_id"],
            OutcomeReviewRequest(request_id="BEI-REVIEW-MISSING", **review_args),
            now,
        )
        inv_id = manifest["links"]["investments"].split("proposal_id=")[1]
        package = investments.get_run(db, inv_id)
        for project in package.selected_projects:
            for effect in project.resource_effects:
                for s in snapshots:
                    if s["facility"]["facility_id"] == project.facility_id:
                        next(r for r in s["resources"] if r["resource_id"] == effect.resource_id)[
                            "available_quantity"
                        ] += effect.quantity_delta
        report_snapshots(db, snapshots, now)
        supported, _ = decisions.create_review(
            db,
            manifest["investment_decision_id"],
            OutcomeReviewRequest(request_id="BEI-REVIEW-SUPPORTED", **review_args),
            now,
        )
        manifest.update(
            missing_review_id=missing.review_id, supported_review_id=supported.review_id
        )
        manifest["links"]["decisions"] = (
            f"/decisions?decision_id={manifest['investment_decision_id']}&review_id={supported.review_id}"
        )
    row = db.get(DemoExercise, EXERCISE_ID)
    ensure_history(db, now)
    row.phase = request.target_phase
    row.clock = now
    row.manifest = manifest
    db.commit()
    return context(db)
