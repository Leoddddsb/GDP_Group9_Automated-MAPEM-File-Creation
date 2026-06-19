import unittest
import sys
from pathlib import Path

from mapemgen.matching.matching_engine import Fact, MatchingEngine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "mapemgen" / "matching"))
import transforms_overlay

from mapemgen.matching.transforms_overlay import (
    connecting_lane_id,
    directional_use_from_label,
    egress_approach_id,
    ingress_approach_id,
    node_xy_from_payload,
    signal_group_id,
)


class _PrepassTransforms:
    @staticmethod
    def polyline_centroid(points):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return [sum(xs) / len(xs), sum(ys) / len(ys)]

    @staticmethod
    def cluster_by_direction(polylines, ref):
        return list(range(1, len(list(polylines)) + 1))

    @staticmethod
    def direction_relative_to_refpoint(polyline, ref):
        return "ingress" if polyline[-1][0] < polyline[0][0] else "egress"


class MatchingApproachPrepassTest(unittest.TestCase):
    def test_analyze_lanes_reads_geometry_payload(self):
        engine = MatchingEngine({}, _PrepassTransforms)
        facts = [
            Fact(
                fact_id="lane_1_geom",
                fact_name="lane_geometry_candidate_from_cad",
                payload={
                    "lane_ref": "lane_1",
                    "geometry": [[10, 0], [0, 0]],
                },
            ),
            Fact(
                fact_id="lane_2_geom",
                fact_name="lane_geometry_candidate_from_cad",
                payload={
                    "lane_ref": "lane_2",
                    "geometry": [[0, 10], [10, 10]],
                },
            ),
        ]
        ctx = {"resolved": {}}

        engine._analyze_lanes(facts, ctx)

        self.assertEqual(
            ctx["resolved"]["approach"],
            {
                "lane_1": {"id": 1, "dir": "ingress"},
                "lane_2": {"id": 2, "dir": "egress"},
            },
        )

    def test_approach_lookup_honours_assignment_direction(self):
        value = {
            "approach_ref": "approach_7",
            "direction": "ingress",
        }

        self.assertEqual(ingress_approach_id(value), 7)
        self.assertIsNone(egress_approach_id(value))

    def test_assignment_direction_overrides_prepass_direction(self):
        value = {
            "approach_ref": "approach_7",
            "direction": "ingress",
        }
        scope = {"lane": "lane_1"}
        resolved = {"approach": {"lane_1": {"id": 1, "dir": "egress"}}}

        self.assertEqual(ingress_approach_id(value, scope=scope, resolved=resolved), 7)
        self.assertIsNone(egress_approach_id(value, scope=scope, resolved=resolved))

    def test_undirected_assignment_uses_only_matching_prepass_side(self):
        value = {"approach_ref": "approach_7"}
        scope = {"lane": "lane_1"}
        resolved = {"approach": {"lane_1": {"id": 1, "dir": "egress"}}}

        self.assertIsNone(ingress_approach_id(value, scope=scope, resolved=resolved))
        self.assertEqual(egress_approach_id(value, scope=scope, resolved=resolved), 1)

    def test_undirected_assignment_without_prepass_does_not_pick_a_side(self):
        value = {"approach_ref": "approach_7"}

        self.assertIsNone(ingress_approach_id(value))
        self.assertIsNone(egress_approach_id(value))

    def test_directional_use_reads_explicit_payload_direction(self):
        self.assertEqual(
            directional_use_from_label({"approach_ref": "approach_7", "direction": "egress"}),
            "egress",
        )
        self.assertEqual(directional_use_from_label({"approach_ref": "approach_7"}), "unknown")

    def test_node_xy_from_payload_uses_refpoint_when_available(self):
        value = {"x": 110.5, "y": 95.25}
        ref_point = {"x": 100.0, "y": 100.0}

        output = node_xy_from_payload(value, ref_point=ref_point)

        self.assertEqual(output, {"x": 10.5, "y": -4.75})

    def test_directional_use_selection_prefers_explicit_direction_over_unknown(self):
        rules = {
            "scoring": {
                "weights": {
                    "extract_confidence": 0.15,
                    "conflict_agreement": 0.35,
                    "source_priority": 0.5,
                },
                "confidence_levels": {"low": 0.3, "medium": 0.6, "high": 0.9},
                "source_priority_scores": {"P1": 1.0, "P2": 0.75, "P3": 0.5, "F": 0.25},
            },
            "conflict_detection": {
                "field_type_map": {"*.directionalUse": "enum"},
                "tolerances": {"enum": {"method": "exact"}},
            },
        }
        engine = MatchingEngine(rules, transforms_overlay)
        source = {
            "fact_name": "approach_assignment_candidate_from_cad",
            "priority": "P1",
            "transform": ["directional_use_from_label", "encode_bit_string_2"],
        }
        rule = {
            "target": "mapData.intersections[].laneSet[].laneAttributes.directionalUse",
        }
        candidates = [
            (source, Fact(fact_id="unknown_1", fact_name="approach_assignment_candidate_from_cad", payload={"approach_ref": "approach_1"}, confidence="high")),
            (source, Fact(fact_id="unknown_2", fact_name="approach_assignment_candidate_from_cad", payload={"approach_ref": "approach_1"}, confidence="high")),
            (source, Fact(fact_id="ingress_1", fact_name="approach_assignment_candidate_from_cad", payload={"approach_ref": "approach_1", "direction": "ingress"}, confidence="high")),
        ]

        winner, _corroborating, _rejected = engine._select_by_score(
            candidates,
            rule,
            {},
            lambda _source: 1,
        )

        self.assertEqual(winner[1].fact_id, "ingress_1")

    def test_selection_prefers_computable_candidate_over_pending_candidate(self):
        rules = {
            "scoring": {
                "weights": {
                    "extract_confidence": 0.15,
                    "conflict_agreement": 0.35,
                    "source_priority": 0.5,
                },
                "confidence_levels": {"low": 0.3, "medium": 0.6, "high": 0.9},
                "source_priority_scores": {"P1": 1.0, "P2": 0.75, "P3": 0.5, "F": 0.25},
            },
            "conflict_detection": {
                "field_type_map": {"*.connectingLane.lane": "integer_id"},
                "tolerances": {"integer_id": {"method": "exact"}},
            },
        }
        engine = MatchingEngine(rules, transforms_overlay)
        pending_source = {
            "fact_name": "lane_geometry_candidate_from_cad",
            "priority": "P1",
            "transform": ["missing_transform"],
        }
        computed_source = {
            "fact_name": "lane_connection_candidate_from_cad",
            "priority": "P1",
            "transform": ["connecting_lane_id"],
        }
        rule = {
            "target": "mapData.intersections[].laneSet[].connectsTo[].connectingLane.lane",
        }
        ctx = {"resolved": {"lane_id_by_ref": {"lane_2": 2}}}
        candidates = [
            (pending_source, Fact(fact_id="pending", fact_name="lane_geometry_candidate_from_cad", payload={"lane_ref": "lane_1"}, confidence="high")),
            (computed_source, Fact(fact_id="computed", fact_name="lane_connection_candidate_from_cad", payload={"target_lane_ref": "lane_2"}, confidence="medium")),
        ]

        winner, _corroborating, _rejected = engine._select_by_score(
            candidates,
            rule,
            ctx,
            lambda _source: 1,
        )

        self.assertEqual(winner[1].fact_id, "computed")

    def test_connecting_lane_id_uses_resolved_lane_id_map(self):
        value = {"target_lane_ref": "lane_23"}
        resolved = {"lane_id_by_ref": {"lane_23": 32}}

        self.assertEqual(connecting_lane_id(value, resolved=resolved), 32)

    def test_signal_group_id_reads_manual_connection_payload(self):
        value = {"lane_ref": "lane_1", "target_lane_ref": "lane_29", "signalGroup": "4"}

        self.assertEqual(signal_group_id(value), 4)


if __name__ == "__main__":
    unittest.main()
