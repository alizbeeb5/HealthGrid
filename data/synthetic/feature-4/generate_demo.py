"""Rebuild fictional histories from agreed fixtures; never accesses a database."""

import json
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent
EXAMPLES = ROOT / "contracts/examples/feature-1"
START = date(2026, 8, 15)


def generate():
    for letter in "ABC":
        template = json.loads((EXAMPLES / f"DEMO-{letter}.snapshot.response.json").read_text())
        records = []
        for index in range(56):
            day = START + timedelta(days=index)
            week = index // 7
            weekday = (day.weekday() + 1) % 7
            snapshot = deepcopy(template)
            snapshot["as_of"] = f"{day}T23:59:00Z"
            snapshot["facility"]["last_reported_at"] = f"{day}T08:35:00Z"
            snapshot["services"][0]["status"] = (
                "limited"
                if letter == "A" and week == 7
                else "unavailable"
                if letter == "C" and week >= 6
                else "operating"
            )
            for resource in snapshot["resources"]:
                rid = resource["resource_id"]
                quantities = {
                    "available-beds": 18 if letter == "B" else 12,
                    "nurses-on-duty": 9 if letter == "B" else 6,
                    "oxygen-stock": 800.5,
                    "working-monitors": [5, 5, 6, 5, 5, 6, 4, 5][week] if letter == "B" else 4,
                }
                resource.update(
                    available_quantity=quantities[rid],
                    observation_id=f"HIST-{letter}-{day}-{rid}",
                    observed_at=f"{day}T08:30:00Z",
                    recorded_at=f"{day}T08:35:00Z",
                    data_status="current",
                )
                if letter == "A" and rid == "working-monitors" and week >= 6:
                    resource.update(
                        available_quantity=None,
                        observation_id=None,
                        observed_at=None,
                        recorded_at=None,
                        data_status="unknown",
                    )
            demand = (
                ([5, 8, 7, 6, 5, 5, 4][weekday] + [0, 1, 0, -1, 0, 1, -1, 0][week])
                if letter == "B"
                else (
                    [3, 4, 3, 2, 3, 2, 2][weekday]
                    if letter == "C"
                    else [4, 5, 4, 3, 4, 3, 3][weekday]
                )
            )
            records.append(
                {
                    "date": str(day),
                    "snapshot": snapshot,
                    "demand": demand,
                    "source": "fictional-weekly-demo-v1",
                    "data_quality": "synthetic",
                    "capacity_unit": "simultaneous_service_place",
                    "profile_version": "demo-v1",
                }
            )
        (OUTPUT / f"DEMO-{letter}.history.json").write_text(json.dumps(records, indent=2) + "\n")


def export_integrated_examples():
    import sys
    from dataclasses import asdict
    from datetime import datetime

    sys.path.insert(0, str(ROOT / "apps/api"))
    from app.engines.forecasting import (
        DailyHistoryRecord,
        forecast_daily_history,
        forecast_service_capacity,
    )
    from app.modules.capacity.schemas import ServiceRequirement
    from app.modules.facilities.schemas import FacilitySnapshotResponse
    from app.modules.forecasting.schemas import DailyHistoryImport, ForecastInput

    profile = ServiceRequirement.model_validate_json(
        (ROOT / "data/synthetic/feature-2/service-requirement.json").read_text()
    )
    payload = {"resource_records": [], "demand_records": []}
    all_histories = {}
    for letter in "ABC":
        rows = json.loads((OUTPUT / f"DEMO-{letter}.history.json").read_text())
        all_histories[letter] = rows
        for row in rows:
            fid = row["snapshot"]["facility"]["facility_id"]
            common = {
                "facility_id": fid,
                "date": row["date"],
                "source": row["source"],
                "data_quality": "estimated",
            }
            for resource in row["snapshot"]["resources"]:
                if resource["available_quantity"] is not None:
                    payload["resource_records"].append(
                        {
                            **common,
                            "resource_id": resource["resource_id"],
                            "unit": resource["unit"],
                            "available_quantity": resource["available_quantity"],
                        }
                    )
            payload["demand_records"].append(
                {
                    **common,
                    "service_id": profile.service_id,
                    "peak_required_places": row["demand"],
                    "service_status": row["snapshot"]["services"][0]["status"],
                }
            )
    imported = DailyHistoryImport.model_validate(payload)
    (OUTPUT / "daily-history.json").write_text(imported.model_dump_json(indent=2) + "\n")
    for letter in "BC":
        records = [
            DailyHistoryRecord(
                date=date.fromisoformat(r["date"]),
                snapshot=FacilitySnapshotResponse.model_validate(r["snapshot"]),
                demand=r["demand"],
                source=r["source"],
                data_quality=r["data_quality"],
                capacity_unit=r["capacity_unit"],
                profile_version=r["profile_version"],
            )
            for r in all_histories[letter]
        ]
        result = forecast_daily_history(
            records, profile, datetime.fromisoformat("2026-10-10T23:59:59Z")
        )
        (OUTPUT / f"DEMO-{letter}.expected-engine-result.json").write_text(
            json.dumps(asdict(result), default=lambda v: v.isoformat(), indent=2) + "\n"
        )
    for letter, filename in [
        ("B", "DEMO-B.forecast.response.json"),
        ("A", "insufficient-history.forecast.response.json"),
    ]:
        fid = f"DEMO-{letter}"
        inputs = ForecastInput(
            facility_id=fid,
            service_id=profile.service_id,
            service_status="operating",
            requirement=profile,
            resource_records=[r for r in imported.resource_records if r.facility_id == fid],
            demand_records=[r for r in imported.demand_records if r.facility_id == fid],
            generated_at=datetime.fromisoformat("2026-10-10T09:00:00Z"),
        )
        result = forecast_service_capacity(inputs)
        (ROOT / "contracts/examples/feature-4" / filename).write_text(
            result.model_dump_json(indent=2) + "\n"
        )


if __name__ == "__main__":
    generate()
    export_integrated_examples()
