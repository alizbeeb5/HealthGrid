"""Contract and catalog rules, exercised without a database or HTTP server."""

import json
import runpy
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from app.modules.facilities.schemas import (
    ErrorDetail,
    ErrorResponse,
    ObservationCreate,
    ResourceDefinition,
)
from app.modules.ingestion.validation import validate_observation

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "contracts/examples/feature-1"


def read(name):
    return json.loads((EXAMPLES / name).read_text())


class ObservationValidationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {
            row["resource_id"]: ResourceDefinition.model_validate(row)
            for row in read("resource-definitions.json")
        }
        self.payload = read("observation.request.json")
        self.now = datetime.fromisoformat("2026-10-10T09:00:00Z")

    def validate(self, payload):
        observation = ObservationCreate.model_validate(payload)
        return validate_observation(observation, self.catalog[observation.resource_id], self.now)

    def test_valid_examples(self):
        for case in read("valid-observations.json"):
            with self.subTest(case=case["case"]):
                observation = ObservationCreate.model_validate(case["request"])
                self.assertEqual(validate_observation(
                    observation, self.catalog[observation.resource_id],
                    datetime.fromisoformat(case["server_now"]),
                ), [])

    def test_invalid_examples_report_expected_fields(self):
        for case in read("invalid-observations.json"):
            with self.subTest(case=case["case"]):
                if case["validation_layer"] == "shape":
                    with self.assertRaises(ValidationError) as caught:
                        ObservationCreate.model_validate(case["request"])
                    self.assertIn(case["expected_field"],
                                  [e["loc"][0] for e in caught.exception.errors()])
                elif case["validation_layer"] == "catalog":
                    errors = self.validate(case["request"])
                    self.assertIn(case["expected_field"], [e.field for e in errors])
                    self.assertTrue(all(e.message for e in errors))
                else:
                    # Lookup and HTTP mapping belong to the backend owner.
                    self.assertEqual(case["validation_layer"], "resource_lookup")
                    self.assertNotIn(case["request"]["resource_id"], self.catalog)

    def test_nonfinite_and_non_numeric_quantities(self):
        for value in (float("nan"), float("inf"), float("-inf"), True, "10", None, -0.1):
            with self.subTest(value=value), self.assertRaises(ValidationError) as caught:
                ObservationCreate.model_validate({**self.payload, "available_quantity": value})
            self.assertEqual(caught.exception.errors()[0]["loc"], ("available_quantity",))

    def test_required_fields(self):
        for field in self.payload:
            with self.subTest(field=field), self.assertRaises(ValidationError) as caught:
                payload = {k: v for k, v in self.payload.items() if k != field}
                ObservationCreate.model_validate(payload)
            self.assertEqual(caught.exception.errors()[0]["loc"], (field,))

    def test_just_beyond_future_tolerance(self):
        time = self.now + timedelta(minutes=5, microseconds=1)
        errors = self.validate({**self.payload, "observed_at": time.isoformat()})
        self.assertEqual([e.field for e in errors], ["observed_at"])

    def test_multiple_errors_and_error_envelope(self):
        errors = self.validate({**self.payload, "available_quantity": 1.5,
                                "unit": "liter", "observed_at": "2026-10-10T09:06:00Z"})
        self.assertEqual(
            [e.field for e in errors], ["unit", "available_quantity", "observed_at"]
        )
        response = ErrorResponse(error=ErrorDetail(
            code="invalid_observation", message="The observation could not be saved.", fields=errors,
        ))
        self.assertEqual(len(json.loads(response.model_dump_json())["error"]["fields"]), 3)
        unit_errors = self.validate({**self.payload, "unit": "liter"})
        self.assertEqual(unit_errors[0].model_dump(),
                         read("validation-error.response.json")["error"]["fields"][0])

    def test_wrong_catalog_entry(self):
        errors = validate_observation(ObservationCreate.model_validate(self.payload),
                                      self.catalog["oxygen-stock"], self.now)
        self.assertEqual([e.field for e in errors], ["resource_id"])

    def test_server_time_requires_timezone(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            validate_observation(ObservationCreate.model_validate(self.payload),
                                 self.catalog["available-beds"], self.now.replace(tzinfo=None))

    def test_validation_does_not_mutate_inputs(self):
        observation = ObservationCreate.model_validate(self.payload)
        resource = self.catalog[observation.resource_id]
        before = (observation.model_dump(), resource.model_dump())
        validate_observation(observation, resource, self.now)
        self.assertEqual(before, (observation.model_dump(), resource.model_dump()))

    def test_shared_examples(self):
        runpy.run_path(str(ROOT / "apps/api/scripts/check_feature_1_examples.py"))


if __name__ == "__main__":
    unittest.main()
