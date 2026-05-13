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


if __name__ == "__main__":
    unittest.main()
