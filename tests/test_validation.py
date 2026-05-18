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


if __name__ == "__main__":
    unittest.main()
