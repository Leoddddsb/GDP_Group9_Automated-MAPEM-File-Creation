import json
import unittest
from pathlib import Path

from mapemgen.models import SiteModel
from mapemgen.validation.report import validate_site_model


class ValidationTest(unittest.TestCase):
    def test_example_site_model_is_usable(self):
        raw = json.loads(Path("examples/site_model.example.json").read_text(encoding="utf-8"))
        report = validate_site_model(SiteModel.from_dict(raw))
        self.assertTrue(report.is_usable)
        self.assertEqual(report.metrics["lane_count"], 2)

    def test_missing_connection_signal_group_is_an_error(self):
        raw = json.loads(Path("examples/site_model.example.json").read_text(encoding="utf-8"))
        raw["mapData"]["intersections"][0]["laneSet"][0]["connectsTo"][0].pop("signalGroup")

        report = validate_site_model(SiteModel.from_dict(raw))

        self.assertFalse(report.is_usable)
        self.assertIn("Lane 1 connection to lane 2 has no signalGroup", report.errors)

    def test_encoded_directional_use_is_standard(self):
        raw = json.loads(Path("examples/site_model.example.json").read_text(encoding="utf-8"))
        raw["mapData"]["intersections"][0]["laneSet"][0]["laneAttributes"]["directionalUse"] = "10"
        raw["mapData"]["intersections"][0]["laneSet"][1]["laneAttributes"]["directionalUse"] = "01"

        report = validate_site_model(SiteModel.from_dict(raw))

        self.assertNotIn("Lane 1 has non-standard directionalUse '10'", report.warnings)
        self.assertNotIn("Lane 2 has non-standard directionalUse '01'", report.warnings)

    def test_ingress_lane_with_connection_maneuver_does_not_need_lane_level_maneuvers(self):
        raw = json.loads(Path("examples/site_model.example.json").read_text(encoding="utf-8"))
        lane = raw["mapData"]["intersections"][0]["laneSet"][0]
        lane["laneAttributes"]["directionalUse"] = "10"
        lane.pop("maneuvers", None)
        lane["connectsTo"][0]["connectingLane"]["maneuver"] = "100000000000"

        report = validate_site_model(SiteModel.from_dict(raw))

        self.assertNotIn("Ingress lane 1 has no maneuvers", report.warnings)


if __name__ == "__main__":
    unittest.main()
