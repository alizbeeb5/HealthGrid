"""Internal numerical fixtures, never imported by production or used as wire schemas."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.modules.capacity.schemas import ServiceRequirement
from app.modules.facilities.schemas import FacilitySnapshotResponse

FIXTURES = Path(__file__).resolve().parents[3] / "data/synthetic/feature-8"


@dataclass(frozen=True)
class Expectation:
    facility_id: str
    expected_capacity: int | None
    required_service_places: int | None


@dataclass(frozen=True)
class Problem:
    service_id: str
    capacity_unit: str
    expected_profile_version: str
    requirement: ServiceRequirement | None
    baseline_captured_at: datetime
    expected_at: datetime
    captured_at: datetime
    observation_window_starts_at: datetime
    expectations: tuple[Expectation, ...]
    snapshots: tuple[FacilitySnapshotResponse, ...]


def load_case(name="supported"):
    payload = json.loads((FIXTURES / f"{name}.input.json").read_text())
    payload.pop("synthetic")
    for field in (
        "baseline_captured_at",
        "expected_at",
        "captured_at",
        "observation_window_starts_at",
    ):
        payload[field] = datetime.fromisoformat(payload[field])
    payload["requirement"] = ServiceRequirement.model_validate(payload["requirement"])
    payload["expectations"] = tuple(Expectation(**row) for row in payload["expectations"])
    payload["snapshots"] = tuple(
        FacilitySnapshotResponse.model_validate(row) for row in payload["snapshots"]
    )
    return Problem(**payload)
