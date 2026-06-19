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
        self.assertEqual(connection["connectingLane"]["maneuver"], "100000000000")
        self.assertEqual(connection["signalGroup"], 1)

    def test_json_generator_preserves_header_and_encodes_mapem_lane_fields(self):
        raw = {
            "header": {"protocolVersion": 2, "messageID": 5, "stationID": 100},
            "mapData": {
                "msgIssueRevision": 1,
                "dataParameters": {
                    "processMethod": "Manual transcription from 397L DXF and UTMC specification PDF",
                    "processAgency": "Imperial GDP Group 9",
                    "lastCheckedDate": "2026-06-17",
                    "geoidUsed": "EPSG:27700 source drawing transformed to WGS84",
                },
                "intersections": [
                    {
                        "id": {"region": 50050, "id": 397},
                        "revision": 1,
                        "refPoint": {"lat": 538124601, "long": -15637669},
                        "laneSet": [
                            {
                                "laneID": 1,
                                "name": "A Hyde Park Road northbound ingress",
                                "ingressApproach": 1,
                                "laneAttributes": {
                                    "laneType": "vehicle",
                                    "directionalUse": "10",
                                    "sharedWith": [],
                                },
                                "nodeList": {"nodes": [{"x": -29.6, "y": -55.2}]},
                                "connectsTo": [
                                    {
                                        "connectingLane": {"lane": 2, "maneuver": "straight"},
                                        "signalGroup": 1,
                                        "connectionID": 1,
                                    }
                                ],
                            },
                            {
                                "laneID": 2,
                                "name": "A Hyde Park Road northbound egress",
                                "egressApproach": 1,
                                "laneAttributes": {
                                    "laneType": "crosswalk",
                                    "directionalUse": "01",
                                    "sharedWith": ["pedestrian", "cycle"],
                                },
                                "nodeList": {"nodes": [{"x": -4.0, "y": -6.0}]},
                                "connectsTo": None,
                            },
                        ],
                        "signalHeadLocations": [
                            {"nodeXY": {"x": -5.0, "y": -0.8}, "signalGroupID": 1}
                        ],
                    }
                ],
            },
        }

        output = generate_json_mapem(SiteModel.from_dict(raw))
        lanes = output["mapData"]["intersections"][0]["laneSet"]

        self.assertEqual(output["header"], raw["header"])
        self.assertEqual(
            lanes[0]["laneAttributes"]["laneType"],
            {"choice": "vehicle", "attributes": "0000000000000000"},
        )
        self.assertEqual(lanes[0]["laneAttributes"]["sharedWith"], "0000000000")
        self.assertEqual(
            lanes[1]["laneAttributes"]["laneType"],
            {"choice": "crosswalkLane", "attributes": "0000000000000000"},
        )
        self.assertEqual(lanes[1]["laneAttributes"]["sharedWith"], "0000001100")
        self.assertEqual(lanes[0]["connectsTo"][0]["connectionID"], 1)
        self.assertEqual(
            lanes[0]["connectsTo"][0]["connectingLane"]["maneuver"],
            "100000000000",
        )
        self.assertEqual(
            output["mapData"]["dataParameters"],
            raw["mapData"]["dataParameters"],
        )

    def test_json_generator_encodes_toucan_crosswalk_lane_type_and_shared_with(self):
        raw = {
            "mapData": {
                "msgIssueRevision": 1,
                "intersections": [
                    {
                        "id": {"region": 50050, "id": 397},
                        "revision": 1,
                        "refPoint": {"lat": 538124601, "long": -15637669},
                        "laneSet": [
                            {
                                "laneID": 5,
                                "name": "C Toucan crossing west-side ingress",
                                "ingressApproach": 3,
                                "laneAttributes": {
                                    "directionalUse": "ingress",
                                    "sharedWith": ["pedestriansTraffic", "cyclistVehicleTraffic"],
                                    "laneType": "crosswalk",
                                },
                                "nodeList": {"nodes": [{"x": -4.0, "y": -6.0}]},
                                "connectsTo": [
                                    {
                                        "connectingLane": {"lane": 6, "maneuver": "crossing"},
                                        "signalGroup": 3,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        }

        lane = generate_json_mapem(SiteModel.from_dict(raw))["mapData"]["intersections"][0]["laneSet"][0]

        self.assertEqual(
            lane["laneAttributes"]["laneType"],
            {"choice": "crosswalkLane", "attributes": "0000000000000000"},
        )
        self.assertEqual(lane["laneAttributes"]["sharedWith"], "0000001100")
        self.assertEqual(lane["laneAttributes"]["directionalUse"], "10")
        self.assertEqual(lane["connectsTo"][0]["connectingLane"]["maneuver"], "100000000000")
        self.assertEqual(lane["connectsTo"][0]["connectionID"], 1)

    def test_site_model_accepts_mapem_long_ref_point(self):
        raw = json.loads(Path("examples/site_model.example.json").read_text(encoding="utf-8"))
        ref_point = raw["mapData"]["intersections"][0]["refPoint"]
        ref_point["long"] = ref_point.pop("lon")

        site = SiteModel.from_dict(raw)

        self.assertEqual(site.primary_intersection.ref_point.lon, ref_point["long"])

    def test_site_model_treats_null_connects_to_as_empty(self):
        raw = json.loads(Path("examples/site_model.example.json").read_text(encoding="utf-8"))
        raw["mapData"]["intersections"][1 - 1]["laneSet"][1]["connectsTo"] = None

        site = SiteModel.from_dict(raw)

        self.assertEqual(site.primary_intersection.lane_set[1].connects_to, [])

    def test_site_model_skips_signal_head_with_null_node_xy(self):
        raw = json.loads(Path("examples/site_model.example.json").read_text(encoding="utf-8"))
        raw["mapData"]["intersections"][0]["signalHeadLocations"] = [
            {"nodeXY": None},
            {"nodeXY": "node-LatLon"},
        ]

        site = SiteModel.from_dict(raw)

        self.assertEqual(site.primary_intersection.signal_head_locations, [])

    def test_asn1_generator_contains_map_data(self):
        output = generate_asn1_mapem(load_example())
        self.assertIn("MapData ::= {", output)
        self.assertIn("laneID 1", output)
        self.assertIn("signalGroup 1", output)


if __name__ == "__main__":
    unittest.main()
