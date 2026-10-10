"""Exercise integration through real domain services and transactional route handlers."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.allocation import service as allocation
from app.modules.decisions import service as decisions
from app.modules.decisions.models import DecisionEvent
from app.modules.demo import service
from app.modules.demo.router import advance
from app.modules.demo.schemas import AdvanceExercise
from app.modules.facilities import service as facilities
from app.modules.facilities.models import ResourceObservation
from app.modules.facilities.router import server_now
from app.modules.forecasting import service as forecasts
from app.modules.forecasting.models import DailyResourceRecord, DailyServiceDemand


@pytest.fixture
def exercise(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_scenario", "beirut")
    url = f"sqlite:///{tmp_path}/exercise.sqlite"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
            service.seed(db)
        conn.commit()
    yield engine
    engine.dispose()


def move(engine, before, after):
    with Session(engine) as db:
        return advance(AdvanceExercise(expected_phase=before, target_phase=after), db)


def test_complete_exercise(exercise):
    with Session(exercise) as db:
        ctx = service.context(db)
        assert ctx.phase == "assessment"
        assert [m.covered for m in ctx.metrics] == [28, 36, 48]
        assert len(ctx.resources) == 19
        source = ctx.investment_input.allocation_run_id
        frozen = allocation.get_run(db, source).model_dump()
        assert frozen["proposed_summary"]["unmet_service_places"] == 12
        now = server_now(db)
        assert now.isoformat().startswith("2020-08-04T16:10")
        snap = facilities.get_snapshot(db, "BEI-WEST", now)
        assert all(r.data_status == "current" for r in snap.resources)
        forecast = forecasts.get_facility_forecast(db, "BEI-WEST", "emergency-care", now)
        assert "insufficient_history" not in forecast.model_dump_json()
    with pytest.raises(HTTPException) as conflict:
        move(exercise, "assessment", "recovery")
    assert conflict.value.status_code == 409
    move(exercise, "assessment", "response")
    with Session(exercise) as db:
        count = db.scalar(select(func.count()).select_from(ResourceObservation))
    move(exercise, "assessment", "response")
    with Session(exercise) as db:
        assert db.scalar(select(func.count()).select_from(ResourceObservation)) == count
    result = move(exercise, "response", "recovery")
    with Session(exercise) as db:
        assert decisions.get(db, result.investment_decision_id).status == "completed"
        missing = decisions.get_review(db, result.investment_decision_id, result.missing_review_id)
        supported = decisions.get_review(
            db, result.investment_decision_id, result.supported_review_id
        )
        assert "insufficient_evidence" in missing.model_dump_json()
        assert "at_or_above_expected" in supported.model_dump_json()
        assert "below_expected" not in supported.model_dump_json()
        assert allocation.get_run(db, source).model_dump() == frozen
        assert server_now(db).isoformat().startswith("2020-08-11T17:05")
        # Recovery still has complete history, without tomorrow's funded resources leaking in.
        for fid in ("BEI-WEST", "BEI-EAST", "BEI-MOUNT"):
            forecast = forecasts.get_facility_forecast(db, fid, "emergency-care", server_now(db))
            assert forecast.status == "forecasted"
            assert len(forecast.forecast) == 7
        last = db.get(
            DailyResourceRecord,
            ("BEI-EAST", "nurses-on-duty", service.at("2020-08-10T00:00:00Z").date()),
        )
        assert last.available_quantity == 4  # Funded staffing is only reported on August 11.
        count = db.scalar(select(func.count()).select_from(DailyServiceDemand))
        service.seed(db)  # Resuming is insert-only and idempotent.
        assert db.scalar(select(func.count()).select_from(DailyServiceDemand)) == count


def test_failed_stage_rolls_back_decisions_and_reports(exercise, monkeypatch):
    with Session(exercise) as db:
        initial = service.context(db)
        before = db.scalar(select(func.count()).select_from(DecisionEvent))

    def fail(*args):
        raise RuntimeError("simulated report import failure")

    monkeypatch.setattr(service, "report_snapshots", fail)
    with pytest.raises(RuntimeError, match="simulated report"):
        move(exercise, "assessment", "response")
    with Session(exercise) as db:
        assert service.context(db) == initial
        assert db.scalar(select(func.count()).select_from(DecisionEvent)) == before


def test_exercise_controls_disabled_by_default(exercise, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_scenario", None)
    with Session(exercise) as db:
        assert service.context(db).enabled is False
        with pytest.raises(HTTPException) as error:
            service.require_exercise(db)
        assert error.value.status_code == 404


@pytest.mark.parametrize("case", service.read("counterfactuals.json")["cases"])
def test_wrong_resource_does_not_resolve_bottleneck(case):
    from app.engines.capacity import calculate_service_capacity
    from app.modules.capacity.schemas import ServiceRequirement
    from app.modules.facilities.schemas import FacilitySnapshotResponse

    raw = next(
        row
        for row in service.read("snapshots.json")["incident"]
        if row["facility"]["facility_id"] == case["facility_id"]
    )
    snapshot = FacilitySnapshotResponse.model_validate(raw)
    profile = ServiceRequirement.model_validate(service.read("service-requirement.json"))
    baseline = calculate_service_capacity(snapshot, snapshot.services[0], profile)
    assumed = snapshot.model_copy(deep=True)
    resource = next(row for row in assumed.resources if row.resource_id == case["resource_id"])
    resource.available_quantity += case["assumed_quantity_added"]
    alternative = calculate_service_capacity(assumed, assumed.services[0], profile)
    assert baseline.estimated_capacity == case["capacity_before"]
    assert alternative.estimated_capacity == case["capacity_after"]
    assert alternative.estimated_capacity == baseline.estimated_capacity


def test_resume_repairs_legacy_short_history_without_rewriting_reports(exercise):
    with Session(exercise) as db:
        cutoff = service.at("2020-07-01T00:00:00Z").date()
        db.execute(delete(DailyResourceRecord).where(DailyResourceRecord.record_date < cutoff))
        db.execute(delete(DailyServiceDemand).where(DailyServiceDemand.record_date < cutoff))
        db.commit()
        reports_before = db.scalar(select(func.count()).select_from(ResourceObservation))
        latest = db.get(
            DailyServiceDemand,
            ("BEI-WEST", "emergency-care", service.at("2020-08-03T00:00:00Z").date()),
        )
        latest.peak_required_places = 15  # Existing user-supplied history must be retained.
        db.commit()
        service.seed(db)
        forecast = forecasts.get_facility_forecast(db, "BEI-WEST", "emergency-care", server_now(db))
        assert forecast.status == "forecasted"
        assert latest.peak_required_places == 15
        assert db.scalar(select(func.count()).select_from(ResourceObservation)) == reports_before
