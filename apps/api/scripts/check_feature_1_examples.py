"""Check shared fixtures for shape drift and snapshot semantics, without a database."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from pydantic import ValidationError  # noqa: E402

from app.modules.facilities.schemas import (  # noqa: E402
    ErrorResponse,
    FacilityListResponse,
    FacilitySnapshotResponse,
    ObservationCreate,
    ObservationResponse,
    ResourceDefinition,
)
from app.modules.ingestion.validation import validate_observation  # noqa: E402

fixtures = API_ROOT.parents[1] / "contracts" / "examples" / "feature-1"


def read(name: str):
    return json.loads((fixtures / name).read_text())


facilities = FacilityListResponse.model_validate(read("facilities.response.json"))
catalog = {
    row["resource_id"]: ResourceDefinition.model_validate(row)
    for row in read("resource-definitions.json")
}
for facility in facilities.items:
    snapshot = FacilitySnapshotResponse.model_validate(
        read(f"{facility.facility_id}.snapshot.response.json")
    )
    assert snapshot.facility == facility
    assert all(service.facility_id == facility.facility_id for service in snapshot.services)
    assert len({resource.resource_id for resource in snapshot.resources}) == len(snapshot.resources)
    for resource in snapshot.resources:
        definition = catalog[resource.resource_id]
        assert resource.unit == definition.unit
        assert resource.category == definition.category
        assert resource.allows_fractional == definition.allows_fractional
        if resource.available_quantity is None:
            assert resource.data_status == "unknown"
            assert resource.observation_id is resource.observed_at is resource.recorded_at is None
        else:
            assert resource.observation_id is not None
            assert resource.observed_at is not None and resource.recorded_at is not None
            if not resource.allows_fractional:
                assert resource.available_quantity.is_integer()
            age = snapshot.as_of - resource.observed_at
            expected = "stale" if age > timedelta(hours=snapshot.stale_after_hours) else "current"
            assert resource.data_status == expected

request = ObservationCreate.model_validate(read("observation.request.json"))
response = ObservationResponse.model_validate(read("observation.response.json"))
assert all(response.model_dump()[key] == value for key, value in request.model_dump().items())
for name in ("validation-error.response.json", "not-found.response.json"):
    ErrorResponse.model_validate(read(name))
for case in read("invalid-observations.json"):
    if case["validation_layer"] == "resource_lookup":
        assert case["request"]["resource_id"] not in catalog
        continue  # Backend owner maps failed resource lookup to a field-level 422.
    if case["validation_layer"] == "catalog":
        observation = ObservationCreate.model_validate(case["request"])
        errors = validate_observation(
            observation, catalog[observation.resource_id],
            datetime.fromisoformat(case["server_now"]),
        )
        assert any(error.field == case["expected_field"] for error in errors), case["case"]
        continue
    assert case["validation_layer"] == "shape"
    try:
        ObservationCreate.model_validate(case["request"])
    except ValidationError as error:
        assert any(issue["loc"][0] == case["expected_field"] for issue in error.errors())
    else:
        raise AssertionError(f"Invalid shape was accepted: {case['case']}")
for case in read("valid-observations.json"):
    observation = ObservationCreate.model_validate(case["request"])
    assert not validate_observation(
        observation, catalog[observation.resource_id], datetime.fromisoformat(case["server_now"])
    ), case["case"]
assert not validate_observation(
    request, catalog[request.resource_id], response.recorded_at
)
print("Shared examples passed shape, snapshot, catalog and timestamp checks.")
print("HTTP errors, resource applicability and persistence require backend integration tests.")
