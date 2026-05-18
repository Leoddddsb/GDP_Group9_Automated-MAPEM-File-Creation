import json
import unittest
from pathlib import Path

from mapemgen.generators.asn1_mapem import generate_asn1_mapem
from mapemgen.generators.json_mapem import generate_json_mapem
from mapemgen.models import SiteModel


def load_example() -> SiteModel:
    raw = json.loads(Path("examples/site_model.example.json").read_text(encoding="utf-8"))
    return SiteModel.from_dict(raw)


class GenerationTest(unittest.TestCase):
    def test_json_generator_contains_lane_set(self):
        output = generate_json_mapem(load_example())
        lane_set = output["mapData"]["intersections"][0]["laneSet"]
        self.assertEqual(len(lane_set), 2)
        self.assertEqual(lane_set[0]["laneID"], 1)

    def test_json_generator_uses_mapem_connection_level_signal_group(self):
        output = generate_json_mapem(load_example())
        lane = output["mapData"]["intersections"][0]["laneSet"][0]
        connection = lane["connectsTo"][0]

        self.assertNotIn("signalGroup", lane)
        self.assertEqual(connection["connectingLane"]["lane"], 2)
        self.assertEqual(connection["connectingLane"]["maneuver"], "straight")
        self.assertEqual(connection["signalGroup"], 1)

    def test_asn1_generator_contains_map_data(self):
        output = generate_asn1_mapem(load_example())
        self.assertIn("MapData ::= {", output)
        self.assertIn("laneID 1", output)
        self.assertIn("signalGroup 1", output)


if __name__ == "__main__":
    unittest.main()
