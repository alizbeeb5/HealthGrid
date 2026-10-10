"""Feature 1 reports feeding immutable numerical follow-up captures.

Saved decision-review persistence is covered by test_decisions_api.py.
"""

from dataclasses import asdict, replace
from datetime import timedelta

from outcome_fixture_types import load_case

from app.engines.outcomes import _evaluate_outcome
from app.modules.facilities.schemas import FacilitySnapshotResponse


def capture(client, data, now):
    snapshots = []
    for expected in data.expectations:
        response = client.get(f"/api/v1/facilities/{expected.facility_id}/snapshot")
        assert response.status_code == 200, response.text
        snapshots.append(FacilitySnapshotResponse.model_validate(response.json()))
    return replace(data, captured_at=now, snapshots=tuple(snapshots))


def test_appended_reports_change_only_a_new_followup_capture(client, clock):
    data = load_case()
    clock.now = data.captured_at
    initial = capture(client, data, clock.now)
    initial_snapshot_json = [s.model_dump(mode="json") for s in initial.snapshots]
    initial_result = _evaluate_outcome(initial)
    initial_frozen_result = asdict(initial_result)
    assert initial_result.rows[1].status == "insufficient_evidence"
    assert initial_result.rows[1].observed_capacity is None

    quantities = {
        "DEMO-A": {
            "available-beds": (12, "bed"),
            "nurses-on-duty": (6, "person"),
            "working-monitors": (3, "item"),
        },
        "DEMO-B": {
            "available-beds": (18, "bed"),
            "nurses-on-duty": (9, "person"),
            "working-monitors": (8, "item"),
        },
    }
    for fid, resources in quantities.items():
        for rid, (quantity, unit) in resources.items():
            response = client.post(
                f"/api/v1/facilities/{fid}/observations",
                json={
                    "resource_id": rid,
                    "available_quantity": quantity,
                    "unit": unit,
                    "observed_at": (clock.now - timedelta(minutes=2)).isoformat(),
                },
            )
            assert response.status_code == 201, response.text
    supported = capture(client, data, clock.now)
    supported_result = _evaluate_outcome(supported)
    supported_frozen_result = asdict(supported_result)
    supported_snapshot_json = [s.model_dump(mode="json") for s in supported.snapshots]
    assert supported_result.rows[1].observed_capacity == 8
    assert supported_result.rows[1].capacity_difference == 0
    # Demo A remains reported limited in Feature 1; resource updates do not reopen it.
    assert supported_result.coverage.comparable_facility_ids == ("DEMO-B",)
    assert supported_result.rows[0].status == "insufficient_evidence"
    assert "service_restriction_unquantified" in supported_result.rows[0].reason_codes

    clock.now += timedelta(minutes=5)
    response = client.post(
        "/api/v1/facilities/DEMO-B/observations",
        json={
            "resource_id": "working-monitors",
            "available_quantity": 6,
            "unit": "item",
            "observed_at": (clock.now - timedelta(minutes=1)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    shortfall = _evaluate_outcome(capture(client, data, clock.now))
    assert shortfall.rows[1].observed_capacity == 6
    assert shortfall.rows[1].capacity_difference == -2
    # No live reports are retained by the kernel; earlier captures remain unchanged.
    assert asdict(initial_result) == initial_frozen_result
    assert asdict(supported_result) == supported_frozen_result
    assert [s.model_dump(mode="json") for s in initial.snapshots] == initial_snapshot_json
    assert [s.model_dump(mode="json") for s in supported.snapshots] == supported_snapshot_json
    assert _evaluate_outcome(supported) == supported_result
