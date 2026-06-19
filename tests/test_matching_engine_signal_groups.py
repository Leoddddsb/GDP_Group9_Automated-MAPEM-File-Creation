import unittest

from mapemgen.matching.matching_engine import Fact, MatchingEngine


class _LaneTypeTransforms:
    @staticmethod
    def lane_type(value, **_kwargs):
        text = str(value).lower()
        return "crosswalk" if "crosswalk" in text else "vehicle"


class _SignalHeadTransforms:
    @staticmethod
    def take_lat(value, **_kwargs):
        return value["lat"]

    @staticmethod
    def node_xy(value, **_kwargs):
        return value["nodeXY"]

    @staticmethod
    def signal_group_id(value, **_kwargs):
        return value["signalGroupID"]


class MatchingEngineSignalGroupTest(unittest.TestCase):
    def test_auto_signal_group_skips_connection_when_all_phase_refs_are_dummy(self):
        engine = MatchingEngine({})
        facts = [
            Fact.from_dict(
                {
                    "fact_id": "connection_1",
                    "fact_name": "lane_connection_candidate_from_cad",
                    "payload": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                        "connection_ref": "connection_lane_1_to_lane_2",
                        "target_lane_ref": "lane_2",
                        "phase_refs": ["phase_D"],
                    },
                    "confidence": "medium",
                }
            )
        ]

        generated = engine._auto_connection_signal_group_facts(
            facts,
            {"dummy_phases": ["D"]},
        )

        self.assertEqual(generated, [])

    def test_lane_attribute_selection_prefers_lane_scoped_evidence(self):
        engine = MatchingEngine(
            {
                "scoring": {
                    "selected_statuses": {"enabled": True},
                    "weights": {
                        "extract_confidence": 0.15,
                        "conflict_agreement": 0.35,
                        "source_priority": 0.5,
                    },
                    "confidence_levels": {"low": 0.3, "medium": 0.6, "high": 0.9},
                    "source_priority_scores": {"P1": 1.0, "P2": 0.75},
                },
                "fields": [
                    {
                        "target": "mapData.intersections[].laneSet[].laneAttributes.laneType",
                        "population_mode": "final_score",
                        "sources": [
                            {
                                "fact_name": "lane_geometry_candidate_from_cad",
                                "priority": "P1",
                                "fact_group": "lane_attribute_classification",
                                "transform": ["lane_type"],
                            },
                            {
                                "fact_name": "lane_line_candidate_from_pdf_vector",
                                "priority": "P2",
                                "fact_group": "lane_attribute_classification",
                                "transform": ["lane_type"],
                            },
                        ],
                    }
                ],
            },
            _LaneTypeTransforms,
        )
        facts = [
                {
                    "fact_id": "scoped_crosswalk",
                    "fact_name": "lane_geometry_candidate_from_cad",
                    "payload": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                        "label": "crosswalk",
                    },
                    "confidence": "high",
                },
        ]
        facts.extend(
            {
                "fact_id": f"unscoped_vehicle_{index}",
                "fact_name": "lane_line_candidate_from_pdf_vector",
                "payload": {"label": "vehicle"},
                "confidence": "high",
            }
            for index in range(6)
        )
        output = engine.run(
            facts,
            {},
        )

        record = output["mapped_evidence"][0]
        self.assertEqual(record["value"], "crosswalk")
        self.assertEqual(record["source_facts"], ["scoped_crosswalk"])

    def test_site_config_populates_intersection_name_data_parameters_and_signal_heads(self):
        engine = MatchingEngine(
            {
                "fields": [
                    {
                        "target": "mapData.intersections[].name",
                        "population_mode": "client_configured",
                        "config_key": "intersection.name",
                    },
                    {
                        "target": "mapData.intersections[].refPoint.lat",
                        "population_mode": "final_score",
                        "sources": [
                            {
                                "fact_name": "manual_refpoint_from_site_config",
                                "priority": "P1",
                                "fact_group": "coordinate_reference",
                                "transform": ["take_lat"],
                            }
                        ],
                    },
                    {
                        "target": "mapData.dataParameters.processMethod",
                        "population_mode": "client_configured",
                        "config_key": "dataParameters.processMethod",
                    },
                    {
                        "target": "mapData.intersections[].signalHeadLocations[].nodeXY",
                        "population_mode": "final_score",
                        "sources": [
                            {
                                "fact_name": "manual_signal_head_location",
                                "priority": "P1",
                                "fact_group": "signal_head_geometry",
                                "transform": ["node_xy"],
                            }
                        ],
                    },
                    {
                        "target": "mapData.intersections[].signalHeadLocations[].signalGroupID",
                        "population_mode": "final_score",
                        "sources": [
                            {
                                "fact_name": "manual_signal_head_location",
                                "priority": "P1",
                                "fact_group": "signal_head_semantics",
                                "transform": ["signal_group_id"],
                            }
                        ],
                    },
                ]
            },
            _SignalHeadTransforms,
        )

        output = engine.run(
            [
                {
                    "fact_id": "lane_1",
                    "fact_name": "lane_geometry_candidate_from_cad",
                    "payload": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                    },
                    "confidence": "high",
                }
            ],
            {
                "intersection": {
                    "name": "397L Hyde Park Road Toucan near Brudenell Road"
                },
                "dataParameters": {
                    "processMethod": "Manual transcription from 397L DXF and UTMC specification PDF"
                },
                "manual": {
                    "refpoint": {"lat": 538124601, "long": -15637669},
                    "signal_head_locations": [
                        {
                            "intersection_ref": "intersection_1",
                            "signal_head_ref": "signal_head_1",
                            "nodeXY": {"x": -5.0, "y": -0.8},
                            "signalGroupID": 1,
                        }
                    ]
                },
            },
        )

        values = {record["target_path"]: record["value"] for record in output["mapped_evidence"]}
        self.assertEqual(
            values["mapData.intersections[0].name"],
            "397L Hyde Park Road Toucan near Brudenell Road",
        )
        self.assertEqual(
            values["mapData.dataParameters.processMethod"],
            "Manual transcription from 397L DXF and UTMC specification PDF",
        )
        self.assertEqual(values["mapData.intersections[0].refPoint.lat"], 538124601)
        self.assertEqual(
            values["mapData.intersections[0].signalHeadLocations[0].nodeXY"],
            {"x": -5.0, "y": -0.8},
        )
        self.assertEqual(
            values["mapData.intersections[0].signalHeadLocations[0].signalGroupID"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
