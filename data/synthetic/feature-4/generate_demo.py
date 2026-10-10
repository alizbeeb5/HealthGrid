"""Rebuild fictional histories from agreed fixtures; never accesses a database."""

import json
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent
EXAMPLES = ROOT / "contracts/examples/feature-1"
START = date(2026, 8, 16)


def generate():
    for letter in "ABC":
        template = json.loads((EXAMPLES / f"DEMO-{letter}.snapshot.response.json").read_text())
        records = []
        for index in range(56):
            day = START + timedelta(days=index)
            week = index // 7
            weekday = day.weekday()
            snapshot = deepcopy(template)
            snapshot["as_of"] = f"{day}T23:59:00Z"
            snapshot["facility"]["last_reported_at"] = f"{day}T08:35:00Z"
            snapshot["services"][0]["status"] = (
                "limited" if letter == "A" and week == 7 else
                "unavailable" if letter == "C" and week >= 6 else "operating"
            )
            for resource in snapshot["resources"]:
                rid = resource["resource_id"]
                quantities = {"available-beds": 18 if letter == "B" else 12,
                              "nurses-on-duty": 9 if letter == "B" else 6,
                              "oxygen-stock": 800.5,
                              "working-monitors": [5, 5, 6, 5, 5, 6, 4, 5][week]
                              if letter == "B" else 4}
                resource.update(
                    available_quantity=quantities[rid],
                    observation_id=f"HIST-{letter}-{day}-{rid}",
                    observed_at=f"{day}T08:30:00Z",
                    recorded_at=f"{day}T08:35:00Z",
                    data_status="current",
                )
                if letter == "A" and rid == "working-monitors" and week >= 6:
                    resource.update(available_quantity=None, observation_id=None,
                                    observed_at=None, recorded_at=None, data_status="unknown")
            demand = ([5, 8, 7, 6, 5, 5, 4][weekday]
                      + [0, 1, 0, -1, 0, 1, -1, 0][week]) if letter == "B" else (
                [3, 4, 3, 2, 3, 2, 2][weekday] if letter == "C" else
                [4, 5, 4, 3, 4, 3, 3][weekday]
            )
            records.append({"date": str(day), "snapshot": snapshot, "demand": demand,
                            "source": "fictional-weekly-demo-v1", "data_quality": "synthetic",
                            "capacity_unit": "simultaneous_service_place",
                            "profile_version": "demo-v1"})
        (OUTPUT / f"DEMO-{letter}.history.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    generate()
