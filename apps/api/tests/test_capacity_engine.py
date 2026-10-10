"""Pure Feature 2 tests; require teammate 2's agreed capacity schemas."""

import json
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from app.engines.capacity import calculate_service_capacity, validate_requirement_profiles
from app.modules.capacity.schemas import ServiceRequirement
from app.modules.facilities.schemas import FacilitySnapshotResponse, ResourceDefinition

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "contracts/examples"
RUNTIME = ROOT / "data/synthetic/feature-2/service-requirement.json"


def read(path):
    return json.loads(path.read_text())


class CapacityEngineTests(unittest.TestCase):
    def setUp(self):
        self.profile = ServiceRequirement.model_validate(read(RUNTIME))
        self.catalog = [ResourceDefinition.model_validate(row) for row in
                        read(EXAMPLES / "feature-1/resource-definitions.json")]
        self.snapshot = FacilitySnapshotResponse.model_validate(
            read(EXAMPLES / "feature-1/DEMO-B.snapshot.response.json")
        )
        validate_requirement_profiles([self.profile], self.catalog)

    def calculate(self):
        return calculate_service_capacity(self.snapshot, self.snapshot.services[0], self.profile)

    def resource(self, resource_id):
        return next(row for row in self.snapshot.resources if row.resource_id == resource_id)

    def assert_invalid_profile(self, payload):
        # Invalid structure can be rejected by Pydantic or startup validation.
        with self.assertRaises((ValueError, ValidationError)):
            profile = ServiceRequirement.model_validate(payload)
            validate_requirement_profiles([profile], self.catalog)

    def test_runtime_profile_matches_contract(self):
        self.assertEqual(RUNTIME.read_bytes(),
                         (EXAMPLES / "feature-2/service-requirement.json").read_bytes())

    def test_all_shared_demo_results(self):
        for letter in "ABC":
            with self.subTest(facility=letter):
                snapshot = FacilitySnapshotResponse.model_validate(
                    read(EXAMPLES / f"feature-1/DEMO-{letter}.snapshot.response.json")
                )
                result = calculate_service_capacity(snapshot, snapshot.services[0], self.profile)
                expected = read(EXAMPLES / f"feature-2/DEMO-{letter}.capacity.response.json")
                self.assertEqual(result.model_dump(mode="json"), expected["services"][0])

    def test_saved_monitor_change(self):
        self.assertEqual(self.calculate().estimated_capacity, 5)
        self.resource("working-monitors").available_quantity = 8.0
        self.resource("working-monitors").observation_id = "OBS-DEMO-B-UPDATE-1"
        self.resource("working-monitors").observed_at = datetime.fromisoformat(
            "2026-10-10T08:59:00Z"
        )
        result = self.calculate()
        self.assertEqual(result.estimated_capacity, 8)
        self.assertEqual(result.bottleneck_resource_ids, ["working-monitors"])
        monitor = result.resource_limits[-1]
        self.assertEqual(monitor.observation_id, "OBS-DEMO-B-UPDATE-1")
        self.assertEqual(monitor.observed_at, self.resource("working-monitors").observed_at)

    def test_known_zero(self):
        self.resource("working-monitors").available_quantity = 0.0
        result = self.calculate()
        self.assertEqual((result.status, result.estimated_capacity), ("calculated", 0))
        self.assertEqual(result.bottleneck_resource_ids, ["working-monitors"])
        self.assertEqual(result.reason_codes, [])

    def test_all_tied_bottlenecks_are_sorted(self):
        self.resource("working-monitors").available_quantity = 18.0
        self.snapshot.resources.reverse()
        result = self.calculate()
        self.assertEqual(result.estimated_capacity, 18)
        self.assertEqual(result.bottleneck_resource_ids,
                         ["available-beds", "nurses-on-duty", "working-monitors"])
        self.assertEqual([row.resource_id for row in result.resource_limits],
                         result.bottleneck_resource_ids)

    def test_missing_resource_and_missing_observation(self):
        for absent in (True, False):
            with self.subTest(absent=absent):
                snapshot = self.snapshot.model_copy(deep=True)
                if absent:
                    snapshot.resources = [r for r in snapshot.resources
                                          if r.resource_id != "working-monitors"]
                else:
                    monitor = snapshot.resources[-1]
                    monitor.available_quantity = None
                    monitor.observation_id = monitor.observed_at = monitor.recorded_at = None
                    monitor.data_status = "unknown"
                result = calculate_service_capacity(snapshot, snapshot.services[0], self.profile)
                self.assertEqual((result.status, result.estimated_capacity), ("unknown", None))
                self.assertEqual(result.reason_codes, ["missing_required_observation"])
                self.assertEqual(result.bottleneck_resource_ids, [])
                limit = result.resource_limits[-1]
                self.assertIsNone(limit.capacity_limit)
                self.assertIsNone(limit.available_quantity)
                self.assertIsNone(limit.observation_id)
                self.assertIsNone(limit.observed_at)
                self.assertEqual(limit.unit, "item")
                self.assertEqual(result.resource_limits[0].capacity_limit, 18)

    def test_stale_preserves_evidence(self):
        monitor = self.resource("working-monitors")
        monitor.data_status = "stale"
        monitor.observed_at = datetime.fromisoformat("2026-10-09T07:00:00Z")
        result = self.calculate()
        self.assertEqual((result.status, result.estimated_capacity), ("unknown", None))
        self.assertEqual(result.reason_codes, ["stale_required_observation"])
        limit = result.resource_limits[-1]
        self.assertEqual(limit.available_quantity, 5)
        self.assertEqual(limit.observation_id, monitor.observation_id)
        self.assertEqual(limit.observed_at, monitor.observed_at)
        self.assertIsNone(limit.capacity_limit)
        self.assertEqual(result.bottleneck_resource_ids, [])

    def test_all_reasons_retained(self):
        self.snapshot.services[0].status = "limited"
        self.resource("available-beds").data_status = "stale"
        self.snapshot.resources = [r for r in self.snapshot.resources
                                   if r.resource_id != "working-monitors"]
        result = self.calculate()
        self.assertEqual(result.reason_codes, ["missing_required_observation",
                                              "service_restriction_unquantified",
                                              "stale_required_observation"])
        self.assertIsNone(result.estimated_capacity)

    def test_service_status_and_profile_precedence(self):
        for status, has_profile, expected, estimate in (
            ("unavailable", True, "unavailable", 0),
            ("unavailable", False, "unavailable", 0),
            ("limited", True, "unknown", None),
            ("limited", False, "not_configured", None),
            ("operating", False, "not_configured", None),
        ):
            with self.subTest(status=status, has_profile=has_profile):
                service = self.snapshot.services[0].model_copy(update={"status": status})
                snapshot = self.snapshot.model_copy(update={"services": [service]})
                result = calculate_service_capacity(
                    snapshot, service, self.profile if has_profile else None
                )
                self.assertEqual((result.status, result.estimated_capacity), (expected, estimate))
                self.assertEqual(result.bottleneck_resource_ids, [])
                if not has_profile:
                    self.assertIsNone(result.profile_version)
                    self.assertEqual(result.resource_limits, [])
                    self.assertIn("requirements_not_configured", result.reason_codes)
                if status == "limited":
                    self.assertIn("service_restriction_unquantified", result.reason_codes)
                if status == "unavailable":
                    self.assertIn("service_unavailable", result.reason_codes)

    def test_decimal_floor_avoids_binary_rounding(self):
        payload = read(RUNTIME)
        payload["requirements"] = [{"resource_id": "oxygen-stock", "unit": "liter",
                                    "required_per_capacity_unit": 0.1}]
        self.profile = ServiceRequirement.model_validate(payload)
        for quantity, expected in ((0.3, 3), (0.29, 2), (0.0, 0)):
            with self.subTest(quantity=quantity):
                self.resource("oxygen-stock").available_quantity = quantity
                self.assertEqual(self.calculate().estimated_capacity, expected)

    def test_oxygen_is_not_required_in_demo(self):
        oxygen = self.resource("oxygen-stock")
        oxygen.available_quantity = None
        oxygen.observation_id = oxygen.observed_at = oxygen.recorded_at = None
        oxygen.data_status = "unknown"
        self.assertEqual(self.calculate().estimated_capacity, 5)
        self.assertEqual(self.calculate().reason_codes, [])

    def test_inputs_are_unchanged(self):
        before = deepcopy((self.snapshot.model_dump(), self.profile.model_dump()))
        self.calculate()
        self.assertEqual(before, (self.snapshot.model_dump(), self.profile.model_dump()))

    def test_reject_wrong_service_or_facility(self):
        for update in ({"facility_id": "DEMO-X"}, {"service_id": "other"}, {"status": "limited"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                calculate_service_capacity(self.snapshot,
                                           self.snapshot.services[0].model_copy(update=update),
                                           self.profile)
        with self.assertRaises(ValueError):
            calculate_service_capacity(self.snapshot, self.snapshot.services[0],
                                       self.profile.model_copy(update={"service_id": "other"}))

    def test_invalid_profile_configuration(self):
        for value in (0, -1, float("nan"), float("inf"), float("-inf"), True):
            with self.subTest(ratio=value):
                payload = read(RUNTIME)
                payload["requirements"][0]["required_per_capacity_unit"] = value
                self.assert_invalid_profile(payload)
        for version in ("", "   "):
            payload = read(RUNTIME)
            payload["profile_version"] = version
            self.assert_invalid_profile(payload)
        for requirements in ([], [read(RUNTIME)["requirements"][0]] * 2):
            payload = read(RUNTIME)
            payload["requirements"] = requirements
            self.assert_invalid_profile(payload)
        for field, value in (("resource_id", "unknown-resource"), ("unit", "liter")):
            payload = read(RUNTIME)
            payload["requirements"][0][field] = value
            self.assert_invalid_profile(payload)

    def test_duplicate_profiles_and_catalog(self):
        with self.assertRaises(ValueError):
            validate_requirement_profiles([self.profile, self.profile], self.catalog)
        with self.assertRaises(ValueError):
            validate_requirement_profiles([self.profile], self.catalog + self.catalog[:1])

    def test_reject_mismatched_snapshot_units(self):
        self.resource("working-monitors").unit = "liter"
        with self.assertRaises(ValueError):
            self.calculate()

    def test_invalid_profile_does_not_become_unavailable_zero(self):
        self.snapshot.services[0].status = "unavailable"
        self.profile = self.profile.model_copy(update={"requirements": []})
        with self.assertRaises(ValueError):
            self.calculate()


if __name__ == "__main__":
    unittest.main()
