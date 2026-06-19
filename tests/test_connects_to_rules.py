import unittest
import sys
from pathlib import Path

from mapemgen.fusion.fuse import fuse
from mapemgen.matching.matching_engine import MatchingEngine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "mapemgen" / "matching"))
import transforms_overlay


class ConnectsToRulesTest(unittest.TestCase):
    def test_single_lane_connects_to_is_not_applicable(self):
        engine = MatchingEngine(_rules())
        output = engine.run(
            [
                _lane_fact("lane_1"),
            ],
            {},
        )

        record = _record(output, "mapData.intersections[0].laneSet[0].connectsTo")
        self.assertEqual(record["status"], "not_applicable")

        _, report = fuse(output)
        self.assertEqual(report["summary"]["skipped"], 1)
        self.assertEqual(report["summary"]["gaps"], 0)

    def test_multi_lane_connects_to_still_requires_evidence(self):
        engine = MatchingEngine(_rules())
        output = engine.run(
            [
                _lane_fact("lane_1", direction="ingress"),
                _lane_fact("lane_2", direction="ingress"),
            ],
            {},
        )

        record = _record(output, "mapData.intersections[0].laneSet[0].connectsTo")
        self.assertEqual(record["status"], "manual_review_required")

    def test_egress_lane_connects_to_is_not_applicable(self):
        engine = MatchingEngine(_rules())
        output = engine.run(
            [
                _lane_fact("lane_1", direction="ingress"),
                _lane_fact("lane_2", direction="egress"),
            ],
            {},
        )

        record = _record(output, "mapData.intersections[0].laneSet[1].connectsTo")
        self.assertEqual(record["status"], "not_applicable")

    def test_manual_connection_signal_group_is_scoped_to_connection(self):
        engine = MatchingEngine(_signal_group_rules(), transforms_overlay)
        output = engine.run(
            [
                _lane_fact("lane_1"),
                _lane_fact("lane_2"),
                {
                    "fact_id": "connection_lane_1_to_lane_2",
                    "fact_name": "lane_connection_candidate_from_cad",
                    "payload": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                        "connection_ref": "connection_lane_1_to_lane_2",
                        "target_lane_ref": "lane_2",
                    },
                    "confidence": "high",
                },
            ],
            {
                "manual": {
                    "connection_signal_groups": [
                        {
                            "lane_ref": "lane_1",
                            "target_lane_ref": "lane_2",
                            "signalGroup": "4",
                        },
                    ],
                },
            },
        )

        record = _record(
            output,
            "mapData.intersections[0].laneSet[0].connectsTo[0].signalGroup",
        )
        self.assertEqual(record["value"], 4)
        self.assertEqual(record["status"], "matched")

    def test_missing_signal_group_is_auto_generated_from_connection(self):
        engine = MatchingEngine(_signal_group_rules(), transforms_overlay)
        output = engine.run(
            [
                _lane_fact("lane_1"),
                _lane_fact("lane_2"),
                {
                    "fact_id": "connection_lane_1_to_lane_2",
                    "fact_name": "lane_connection_candidate_from_cad",
                    "payload": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                        "connection_ref": "connection_lane_1_to_lane_2",
                        "target_lane_ref": "lane_2",
                    },
                    "confidence": "high",
                },
            ],
            {},
        )

        record = _record(
            output,
            "mapData.intersections[0].laneSet[0].connectsTo[0].signalGroup",
        )
        self.assertEqual(record["value"], 1)
        self.assertEqual(record["status"], "matched")
        self.assertEqual(record["source_facts"][0], "auto_signal_group_1")

    def test_explicit_connection_signal_group_prevents_auto_fallback(self):
        engine = MatchingEngine(_signal_group_rules(), transforms_overlay)
        output = engine.run(
            [
                _lane_fact("lane_1"),
                _lane_fact("lane_2"),
                {
                    "fact_id": "connection_lane_1_to_lane_2",
                    "fact_name": "lane_connection_candidate_from_cad",
                    "payload": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                        "connection_ref": "connection_lane_1_to_lane_2",
                        "target_lane_ref": "lane_2",
                        "signalGroup": 7,
                    },
                    "confidence": "high",
                },
            ],
            {},
        )

        record = _record(
            output,
            "mapData.intersections[0].laneSet[0].connectsTo[0].signalGroup",
        )
        self.assertEqual(record["value"], 7)
        self.assertEqual(record["status"], "matched")
        self.assertNotIn("auto_signal_group_1", record["source_facts"])

    def test_connecting_lane_uses_explicit_connection_target(self):
        engine = MatchingEngine(_connecting_lane_rules(), transforms_overlay)
        output = engine.run(
            [
                _lane_fact("lane_1"),
                _lane_fact("lane_2"),
                {
                    "fact_id": "connection_lane_1_to_lane_2",
                    "fact_name": "lane_connection_candidate_from_cad",
                    "payload": {
                        "intersection_ref": "intersection_1",
                        "lane_ref": "lane_1",
                        "connection_ref": "connection_lane_1_to_lane_2",
                        "target_lane_ref": "lane_2",
                    },
                    "confidence": "high",
                },
            ],
            {},
        )

        record = _record(
            output,
            "mapData.intersections[0].laneSet[0].connectsTo[0].connectingLane.lane",
        )
        self.assertEqual(record["value"], 2)
        self.assertEqual(record["status"], "matched")
        self.assertEqual(record["source_facts"][0], "connection_lane_1_to_lane_2")


def _rules():
    return {
        "scoring": {"selected_statuses": {"enabled": True}},
        "fields": [
            {
                "target": "mapData.intersections[].laneSet[].connectsTo",
                "population_mode": "must_exist",
                "c_roads_mandatory": True,
                "applies_when": "lane.directionalUse contains ingress",
            },
        ],
    }


def _signal_group_rules():
    return {
        "scoring": {
            "selected_statuses": {"enabled": True},
            "weights": {
                "extract_confidence": 0.15,
                "conflict_agreement": 0.35,
                "source_priority": 0.5,
            },
            "confidence_levels": {"low": 0.3, "medium": 0.6, "high": 0.9},
            "source_priority_scores": {"P1": 1.0, "P2": 0.75, "P3": 0.5, "F": 0.25},
        },
        "source_priority_ranks": {"P1": 1, "P2": 2, "P3": 3, "F": 9},
        "conflict_detection": {
            "field_type_map": {"*.signalGroup": "integer_id"},
            "tolerances": {"integer_id": {"method": "exact", "tolerance": 0}},
        },
        "group_logic": {
            "alternative_sets": {
                "signal_semantics": ["signal_control_semantics", "movement_phase_mapping"],
                "connection_semantics": ["connection_topology"],
            },
            "required_group_sets": {
                "connection_signal_group": ["signal_semantics", "connection_semantics"],
            },
        },
        "fields": [
            {
                "target": "mapData.intersections[].laneSet[].connectsTo[].signalGroup",
                "population_mode": "final_score",
                "c_roads_mandatory": True,
                "sources": [
                    {
                        "fact_name": "lane_connection_candidate_from_cad",
                        "priority": "P1",
                        "fact_group": "signal_control_semantics",
                        "transform": ["explicit_signal_group_id"],
                    },
                    {
                        "fact_name": "manual_connection_signal_group",
                        "priority": "P1",
                        "fact_group": "signal_control_semantics",
                        "transform": ["signal_group_id"],
                    },
                    {
                        "fact_name": "auto_connection_signal_group_from_connection",
                        "priority": "F",
                        "fact_group": "signal_control_semantics",
                        "transform": ["signal_group_id"],
                    },
                    {
                        "fact_name": "lane_connection_candidate_from_cad",
                        "priority": "P1",
                        "fact_group": "connection_topology",
                    },
                ],
            }
        ],
    }


def _connecting_lane_rules():
    return {
        "scoring": {
            "selected_statuses": {"enabled": True},
            "weights": {
                "extract_confidence": 0.15,
                "conflict_agreement": 0.35,
                "source_priority": 0.5,
            },
            "confidence_levels": {"low": 0.3, "medium": 0.6, "high": 0.9},
            "source_priority_scores": {"P1": 1.0, "P2": 0.75, "P3": 0.5, "F": 0.25},
        },
        "source_priority_ranks": {"P1": 1, "P2": 2, "P3": 3, "F": 9},
        "conflict_detection": {
            "field_type_map": {"*.connectingLane.lane": "integer_id"},
            "tolerances": {"integer_id": {"method": "exact", "tolerance": 0}},
        },
        "fields": [
            {
                "target": "mapData.intersections[].laneSet[].connectsTo[].connectingLane.lane",
                "population_mode": "final_score",
                "c_roads_mandatory": True,
                "sources": [
                    {
                        "fact_name": "lane_connection_candidate_from_cad",
                        "priority": "P1",
                        "fact_group": "connection_topology",
                        "transform": ["connecting_lane_id"],
                    },
                    {
                        "fact_name": "lane_geometry_candidate_from_cad",
                        "priority": "P2",
                        "fact_group": "connection_topology",
                        "transform": ["pair_ingress_egress_by_geometry"],
                    },
                ],
            }
        ],
    }


def _lane_fact(lane_ref, direction=None):
    payload = {
        "intersection_ref": "intersection_1",
        "lane_ref": lane_ref,
        "geometry": [[0, 0], [10, 0]],
    }
    if direction is not None:
        payload["direction"] = direction
    return {
        "fact_id": f"lane_{lane_ref}",
        "fact_name": "lane_geometry_candidate_from_cad",
        "payload": payload,
        "confidence": "medium",
        "source_file": "site.dxf",
    }


def _record(output, target_path):
    return next(item for item in output["mapped_evidence"] if item["target_path"] == target_path)


if __name__ == "__main__":
    unittest.main()
