import unittest

from mapemgen.matching.ingest_adapter import adapt


class MatchingIngestAdapterTest(unittest.TestCase):
    def test_adapt_adds_site_id_and_normalises_legacy_controller_fact_names(self):
        extracted = {
            "site_id": "397L",
            "source_files": [
                {
                    "source_file": "UTMC_397L_SPEC_02a.pdf",
                    "file_type": "pdf",
                    "extracted_facts": [
                        {
                            "fact_id": "phase_1",
                            "fact_name": "phase_candidate",
                            "payload": {"value": "Phase C pedestrian"},
                            "confidence": 0.65,
                        },
                        {
                            "fact_id": "control_1",
                            "fact_name": "control_candidate",
                            "payload": {"value": "OTU SCN 03450 Cont SCN 03451"},
                            "confidence": 0.65,
                        },
                    ],
                }
            ],
        }

        assignments = {
            "lanes": [
                {
                    "lane_ref": "lane_1",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_7",
                    "centroid": {"x": 10, "y": 0},
                    "source_file": "site.dwg",
                }
            ],
            "approaches": [
                {
                    "approach_ref": "approach_7",
                    "centroid": {"x": 0, "y": 0},
                }
            ],
            "assigned_facts": [
                {
                    "fact_id": "phase_1",
                    "target_scope": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                        "approach_ref": "approach_7",
                    },
                },
                {
                    "fact_id": "stop_1",
                    "fact_name": "stop_line_from_cad",
                    "target_scope": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                        "approach_ref": "approach_7",
                    },
                }
            ]
        }

        result = adapt(extracted, assignments)
        facts = result["facts"]
        by_name = {}
        for fact in facts:
            by_name.setdefault(fact["fact_name"], []).append(fact)

        self.assertEqual(
            by_name["official_intersection_id_from_cad"][0]["payload"]["value"],
            "397L",
        )
        self.assertEqual(
            by_name["phase_label_from_controller_config"][0]["payload"]["value"],
            "Phase C pedestrian",
        )
        self.assertEqual(
            by_name["phase_label_from_controller_config"][0]["payload"]["approach_ref"],
            "approach_7",
        )
        self.assertEqual(
            by_name["movement_phase_mapping_from_controller_config"][0]["payload"]["value"],
            "OTU SCN 03450 Cont SCN 03451",
        )
        self.assertEqual(
            by_name["approach_assignment_candidate_from_cad"][0]["payload"]["approach_ref"],
            "approach_7",
        )
        self.assertEqual(
            by_name["approach_assignment_candidate_from_cad"][0]["payload"]["direction"],
            "ingress",
        )
        self.assertEqual(
            by_name["approach_assignment_candidate_from_cad"][0]["payload"]["direction_basis"],
            "cad_stop_line",
        )
        self.assertNotIn("scn", by_name)

    def test_approach_assignment_does_not_use_arrow_alone_as_direction(self):
        extracted = {"source_files": []}
        assignments = {
            "lanes": [
                {
                    "lane_ref": "lane_1",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_1",
                }
            ],
            "assigned_facts": [
                {
                    "fact_id": "arrow_1",
                    "fact_name": "movement_direction_candidate_from_cad",
                    "target_scope": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                        "approach_ref": "approach_1",
                    },
                }
            ],
        }

        result = adapt(extracted, assignments)
        approach = next(
            fact["payload"]
            for fact in result["facts"]
            if fact["fact_name"] == "approach_assignment_candidate_from_cad"
        )

        self.assertNotIn("direction", approach)
        self.assertNotIn("direction_basis", approach)

    def test_approach_assignment_marks_non_stop_line_lane_as_egress_when_approach_has_stop_line(self):
        extracted = {"source_files": []}
        assignments = {
            "lanes": [
                {
                    "lane_ref": "lane_1",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_1",
                },
                {
                    "lane_ref": "lane_2",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_1",
                },
                {
                    "lane_ref": "lane_3",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_2",
                },
            ],
            "assigned_facts": [
                {
                    "fact_id": "stop_1",
                    "fact_name": "stop_line_from_cad",
                    "target_scope": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                        "approach_ref": "approach_1",
                    },
                }
            ],
        }

        result = adapt(extracted, assignments)
        approach_facts = {
            fact["payload"]["lane_ref"]: fact["payload"]
            for fact in result["facts"]
            if fact["fact_name"] == "approach_assignment_candidate_from_cad"
        }

        self.assertEqual(approach_facts["lane_1"]["direction"], "ingress")
        self.assertEqual(approach_facts["lane_2"]["direction"], "egress")
        self.assertEqual(
            approach_facts["lane_2"]["direction_basis"],
            "approach_stop_line_complement",
        )
        self.assertNotIn("direction", approach_facts["lane_3"])

    def test_adapt_adds_connection_candidate_between_ingress_and_nearest_egress(self):
        extracted = {"source_files": []}
        assignments = {
            "lanes": [
                {
                    "lane_ref": "lane_1",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_1",
                    "centroid": {"x": 0, "y": 0},
                },
                {
                    "lane_ref": "lane_2",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_1",
                    "centroid": {"x": 10, "y": 0},
                },
                {
                    "lane_ref": "lane_3",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_2",
                    "centroid": {"x": 100, "y": 0},
                },
            ],
            "assigned_facts": [
                {
                    "fact_id": "stop_1",
                    "fact_name": "stop_line_from_cad",
                    "target_scope": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                        "approach_ref": "approach_1",
                    },
                }
            ],
        }

        result = adapt(extracted, assignments)
        connection = next(
            fact["payload"]
            for fact in result["facts"]
            if fact["fact_name"] == "lane_connection_candidate_from_cad"
        )

        self.assertEqual(connection["lane_ref"], "lane_1")
        self.assertEqual(connection["target_lane_ref"], "lane_2")
        self.assertEqual(connection["connection_ref"], "connection_lane_1_to_lane_2")

    def test_movement_mapping_creates_connection_and_scopes_phase_to_connection(self):
        extracted = {
            "source_files": [
                {
                    "source_file": "controller.docx",
                    "file_type": "docx",
                    "extracted_facts": [
                        {
                            "fact_id": "phase_a",
                            "fact_name": "movement_phase_mapping_from_controller_config",
                            "payload": {
                                "phase_ref": "phase_A",
                                "phase_label": "A",
                                "movement_ref": "movement_london_road_wb_ahead",
                                "movement_text": "London Road WB Ahead",
                                "maneuver": "ahead",
                            },
                            "confidence": 0.9,
                        }
                    ],
                }
            ]
        }
        assignments = {
            "lanes": [
                {
                    "lane_ref": "lane_1",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_1",
                    "centroid": {"x": 0, "y": 0},
                },
                {
                    "lane_ref": "lane_2",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_2",
                    "centroid": {"x": 20, "y": 0},
                },
            ],
            "assigned_facts": [
                {
                    "fact_id": "stop_1",
                    "fact_name": "stop_line_from_cad",
                    "target_scope": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                        "approach_ref": "approach_1",
                    },
                }
            ],
            "movement_lane_mappings": [
                {
                    "movement_ref": "movement_london_road_wb_ahead",
                    "lane_ref": "lane_1",
                    "target_lane_ref": "lane_2",
                    "intersection_ref": "intersection_1",
                    "phase_refs": ["phase_A"],
                    "movement_text": "London Road WB Ahead",
                }
            ],
        }

        result = adapt(extracted, assignments)
        connection = next(
            fact["payload"]
            for fact in result["facts"]
            if fact["fact_name"] == "lane_connection_candidate_from_cad"
        )
        phase_fact = next(
            fact["payload"]
            for fact in result["facts"]
            if fact["fact_name"] == "movement_phase_mapping_from_controller_config"
        )

        self.assertEqual(connection["lane_ref"], "lane_1")
        self.assertEqual(connection["target_lane_ref"], "lane_2")
        self.assertEqual(connection["movement_ref"], "movement_london_road_wb_ahead")
        self.assertEqual(connection["phase_refs"], ["phase_A"])
        self.assertEqual(connection["maneuver"], "ahead")
        self.assertEqual(phase_fact["lane_ref"], "lane_1")
        self.assertEqual(phase_fact["connection_ref"], connection["connection_ref"])

    def test_movement_mapping_allows_multiple_connections_from_same_ingress_lane(self):
        extracted = {"source_files": []}
        assignments = {
            "lanes": [
                {
                    "lane_ref": "lane_1",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_1",
                    "centroid": {"x": 0, "y": 0},
                },
                {
                    "lane_ref": "lane_2",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_2",
                    "centroid": {"x": 20, "y": 0},
                },
                {
                    "lane_ref": "lane_3",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_3",
                    "centroid": {"x": 0, "y": -20},
                },
            ],
            "assigned_facts": [
                {
                    "fact_id": "stop_1",
                    "fact_name": "stop_line_from_cad",
                    "target_scope": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                        "approach_ref": "approach_1",
                    },
                }
            ],
            "movement_lane_mappings": [
                {
                    "movement_ref": "movement_straight",
                    "lane_ref": "lane_1",
                    "target_lane_ref": "lane_2",
                    "phase_refs": ["phase_A"],
                    "maneuver": "ahead",
                },
                {
                    "movement_ref": "movement_right",
                    "lane_ref": "lane_1",
                    "target_lane_ref": "lane_3",
                    "phase_refs": ["phase_B"],
                    "maneuver": "right_turn",
                },
            ],
        }

        result = adapt(extracted, assignments)
        connections = [
            fact["payload"]
            for fact in result["facts"]
            if fact["fact_name"] == "lane_connection_candidate_from_cad"
        ]

        self.assertEqual(len(connections), 2)
        self.assertEqual(
            {(item["target_lane_ref"], item["maneuver"]) for item in connections},
            {("lane_2", "ahead"), ("lane_3", "right_turn")},
        )

    def test_adapt_exposes_movement_lane_prototype_geometry_and_attributes(self):
        extracted = {"source_files": []}
        assignments = {
            "lanes": [
                {
                    "lane_ref": "lane_1",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_1",
                    "centroid": {"x": -50, "y": 0},
                    "geometry": [[-100, 0], [0, 0]],
                    "direction": "ingress",
                    "lane_type": "vehicle",
                    "lane_semantic_basis": "movement_lane_prototype",
                },
                {
                    "lane_ref": "lane_2",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_2",
                    "centroid": {"x": 50, "y": 0},
                    "geometry": [[0, 0], [100, 0]],
                    "direction": "egress",
                    "lane_type": "vehicle",
                    "lane_semantic_basis": "movement_lane_prototype",
                },
            ],
            "movement_lane_mappings": [
                {
                    "movement_ref": "movement_vehicle_straight_1",
                    "lane_ref": "lane_1",
                    "target_lane_ref": "lane_2",
                    "maneuver": "straight",
                    "assignment_method": "movement_lane_prototype",
                }
            ],
        }

        result = adapt(extracted, assignments)
        lane_geometry = [
            fact["payload"]
            for fact in result["facts"]
            if fact["fact_name"] == "lane_geometry_candidate_from_cad"
        ]
        lane_use = [
            fact["payload"]
            for fact in result["facts"]
            if fact["fact_name"] == "lane_use_label_from_cad"
        ]
        lane_nodes = [
            fact["payload"]
            for fact in result["facts"]
            if fact["fact_name"] == "lane_node_candidate_from_assignment"
        ]
        connection = next(
            fact["payload"]
            for fact in result["facts"]
            if fact["fact_name"] == "lane_connection_candidate_from_cad"
        )

        self.assertEqual({item["lane_ref"] for item in lane_geometry}, {"lane_1", "lane_2"})
        self.assertEqual({item["direction"] for item in lane_geometry}, {"ingress", "egress"})
        self.assertEqual({item["lane_type"] for item in lane_use}, {"vehicle"})
        self.assertEqual(len(lane_nodes), 4)
        self.assertEqual({item["node_ref"] for item in lane_nodes}, {"lane_1_node_1", "lane_1_node_2", "lane_2_node_1", "lane_2_node_2"})
        self.assertEqual(connection["lane_ref"], "lane_1")
        self.assertEqual(connection["target_lane_ref"], "lane_2")
        self.assertEqual(connection["maneuver"], "straight")

    def test_crosswalk_prototype_use_label_exposes_toucan_users_for_shared_with(self):
        extracted = {"source_files": []}
        assignments = {
            "lanes": [
                {
                    "lane_ref": "lane_5",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_3",
                    "centroid": {"x": 0, "y": 0},
                    "geometry": [[0, -1], [0, 0]],
                    "direction": "ingress",
                    "lane_type": "crosswalk",
                    "lane_semantic_basis": "movement_lane_prototype",
                },
            ],
        }

        result = adapt(extracted, assignments)
        lane_use = next(
            fact["payload"]
            for fact in result["facts"]
            if fact["fact_name"] == "lane_use_label_from_cad"
        )

        self.assertEqual(lane_use["lane_type"], "crosswalk")
        self.assertIn("pedestrian", lane_use["label"])
        self.assertIn("cycle", lane_use["label"])

    def test_prototype_connections_preserve_assignment_signal_groups(self):
        extracted = {"source_files": []}
        assignments = {
            "lanes": [
                {"lane_ref": "lane_1", "intersection_ref": "intersection_1", "approach_ref": "approach_1", "centroid": {"x": -5, "y": 0}, "geometry": [[-10, 0], [0, 0]], "direction": "ingress", "lane_type": "vehicle", "lane_semantic_basis": "movement_lane_prototype"},
                {"lane_ref": "lane_2", "intersection_ref": "intersection_1", "approach_ref": "approach_2", "centroid": {"x": 5, "y": 0}, "geometry": [[0, 0], [10, 0]], "direction": "egress", "lane_type": "vehicle", "lane_semantic_basis": "movement_lane_prototype"},
                {"lane_ref": "lane_5", "intersection_ref": "intersection_1", "approach_ref": "approach_2", "centroid": {"x": 0, "y": -5}, "geometry": [[0, -10], [0, 0]], "direction": "ingress", "lane_type": "crosswalk", "lane_semantic_basis": "movement_lane_prototype"},
                {"lane_ref": "lane_6", "intersection_ref": "intersection_1", "approach_ref": "approach_1", "centroid": {"x": 0, "y": 5}, "geometry": [[0, 0], [0, 10]], "direction": "egress", "lane_type": "crosswalk", "lane_semantic_basis": "movement_lane_prototype"},
            ],
            "movement_lane_mappings": [
                {"movement_ref": "movement_vehicle_direction_1", "lane_ref": "lane_1", "target_lane_ref": "lane_2", "maneuver": "straight", "signal_group": 1, "assignment_method": "movement_lane_prototype"},
                {"movement_ref": "movement_pedestrian_crossing", "lane_ref": "lane_5", "target_lane_ref": "lane_6", "maneuver": "crossing", "signal_group": 2, "assignment_method": "movement_lane_prototype"},
            ],
        }

        result = adapt(extracted, assignments)
        connections = [
            fact["payload"]
            for fact in result["facts"]
            if fact["fact_name"] == "lane_connection_candidate_from_cad"
        ]

        by_lane = {item["lane_ref"]: item for item in connections}
        self.assertEqual(by_lane["lane_1"]["signalGroup"], 1)
        self.assertEqual(by_lane["lane_5"]["signalGroup"], 2)

    def test_approach_assignment_uses_geometry_relative_to_cad_center_when_no_arrow(self):
        extracted = {
            "source_files": [
                {
                    "source_file": "site.dwg",
                    "file_type": "cad",
                    "extracted_facts": [
                        {
                            "fact_id": "lane_geom_1",
                            "fact_name": "lane_geometry_candidate_from_cad",
                            "payload": {"geometry": [[10, 0], [1, 0]]},
                            "confidence": 0.8,
                        },
                        {
                            "fact_id": "lane_geom_2",
                            "fact_name": "lane_geometry_candidate_from_cad",
                            "payload": {"geometry": [[1, 0], [10, 0]]},
                            "confidence": 0.8,
                        },
                    ],
                }
            ]
        }
        assignments = {
            "lanes": [
                {
                    "lane_ref": "lane_1",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_1",
                    "source_fact_id": "lane_geom_1",
                },
                {
                    "lane_ref": "lane_2",
                    "intersection_ref": "intersection_1",
                    "approach_ref": "approach_2",
                    "source_fact_id": "lane_geom_2",
                },
            ],
            "approaches": [{"approach_ref": "approach_1", "centroid": {"x": 0, "y": 0}}],
        }

        result = adapt(extracted, assignments)
        approach_facts = {
            fact["payload"]["lane_ref"]: fact["payload"]
            for fact in result["facts"]
            if fact["fact_name"] == "approach_assignment_candidate_from_cad"
        }

        self.assertEqual(approach_facts["lane_1"]["direction"], "ingress")
        self.assertEqual(approach_facts["lane_2"]["direction"], "egress")
        self.assertEqual(
            approach_facts["lane_1"]["direction_basis"],
            "geometry_relative_to_cad_center",
        )


if __name__ == "__main__":
    unittest.main()
