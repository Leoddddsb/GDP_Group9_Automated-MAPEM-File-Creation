import json
import unittest
import uuid
from pathlib import Path

from mapemgen.assignment.geometry import assign_geometry_to_lanes
from mapemgen.cli import main
from mapemgen.ingestion.fact_records import make_fact


class GeometryAssignmentTest(unittest.TestCase):
    def test_assigns_cad_geometry_to_default_intersection_and_nearest_lane(self):
        lane_a = _fact(
            "lane_geometry_candidate_from_cad",
            [[0, 0], [10, 0]],
            "site.dxf -> modelspace entity 1 layer LANE_A",
            source_file="site.dxf",
        )
        lane_b = _fact(
            "lane_geometry_candidate_from_cad",
            [[0, 10], [10, 10]],
            "site.dxf -> modelspace entity 2 layer LANE_B",
            source_file="site.dxf",
        )
        stop_line = _fact(
            "stop_line_from_cad",
            [[8, 1], [11, 1]],
            "site.dxf -> modelspace entity 3 layer STOP",
            source_file="site.dxf",
        )
        extracted = _extracted([lane_a, lane_b, stop_line])

        output = assign_geometry_to_lanes(extracted)

        self.assertEqual(output["intersections"][0]["intersection_ref"], "intersection_1")
        self.assertEqual([lane["lane_ref"] for lane in output["lanes"]], ["lane_1", "lane_2"])
        stop_assignment = next(item for item in output["assigned_facts"] if item["fact_id"] == stop_line["fact_id"])
        self.assertEqual(stop_assignment["target_scope"]["intersection_ref"], "intersection_1")
        self.assertEqual(stop_assignment["target_scope"]["lane_ref"], "lane_1")
        self.assertEqual(stop_assignment["assignment_method"], "nearest_lane_centroid")

    def test_assigns_geometry_to_nearest_explicit_intersection_centre(self):
        centre_a = _fact("junction_centre_from_ordnance_survey", {"lon": 0, "lat": 0}, "gis feature 1", source_file="site.geojson")
        centre_b = _fact("junction_centre_from_ordnance_survey", {"lon": 100, "lat": 100}, "gis feature 2", source_file="site.geojson")
        lane = _fact("lane_geometry_candidate_from_ordnance_survey", {"type": "LineString", "coordinates": [[90, 100], [110, 100]]}, "feature 3", source_file="site.geojson")

        output = assign_geometry_to_lanes(_extracted([centre_a, centre_b, lane]))

        self.assertEqual(output["lanes"][0]["intersection_ref"], "intersection_2")

    def test_pdf_page_geometry_only_assigns_within_same_page_ref(self):
        lane_page_1 = _fact(
            "lane_line_candidate_from_pdf_vector",
            {"geometry": {"x0": 0, "top": 10, "x1": 100, "bottom": 10}},
            "drawing.pdf -> page 1 vector line 1",
            source_file="drawing.pdf",
        )
        lane_page_2 = _fact(
            "lane_line_candidate_from_pdf_vector",
            {"geometry": {"x0": 0, "top": 200, "x1": 100, "bottom": 200}},
            "drawing.pdf -> page 2 vector line 1",
            source_file="drawing.pdf",
        )
        stop_page_2 = _fact(
            "stop_line_candidate_from_pdf_vector",
            {"geometry": {"x0": 45, "top": 201, "x1": 55, "bottom": 201}},
            "drawing.pdf -> page 2 vector line 2",
            source_file="drawing.pdf",
        )

        output = assign_geometry_to_lanes(_extracted([lane_page_1, lane_page_2, stop_page_2]))

        stop_assignment = next(item for item in output["assigned_facts"] if item["fact_id"] == stop_page_2["fact_id"])
        self.assertEqual(stop_assignment["target_scope"]["lane_ref"], "lane_2")
        self.assertEqual(stop_assignment["geometry_summary"]["page_ref"], "drawing.pdf#page=2")

    def test_assign_geometry_cli_writes_geometry_assignments(self):
        folder = _test_dir()
        input_path = folder / "extracted_facts.partial.json"
        out_dir = folder / "out"
        input_path.write_text(
            json.dumps(
                _extracted(
                    [
                        _fact(
                            "lane_geometry_candidate_from_cad",
                            [[0, 0], [5, 0]],
                            "site.dxf -> modelspace entity 1 layer LANE_MAIN",
                        )
                    ]
                )
            ),
            encoding="utf-8",
        )

        exit_code = main(["assign-geometry", "--input", str(input_path), "--out-dir", str(out_dir)])

        output = json.loads((out_dir / "geometry_assignments.partial.json").read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(output["lanes"][0]["lane_ref"], "lane_1")

    def test_assigns_phase_stage_and_detector_facts_to_semantic_scope(self):
        phase = _fact("phase_label_from_controller_config", "Phase A", "config.docx -> table 1 row 2", source_file="config.docx")
        stage = _fact("stage_phase_relationship_from_utc_form", "Stage 2 runs Phase A", "utc.docx -> table 1 row 3", source_file="utc.docx")
        detector = _fact("detector_candidate", "Detector D12 demand", "report.txt -> line 7", source_file="report.txt")

        output = assign_geometry_to_lanes(_extracted([phase, stage, detector]))

        by_fact_id = {item["fact_id"]: item for item in output["semantic_assignments"]}
        self.assertEqual(by_fact_id[phase["fact_id"]]["target_scope"]["phase_ref"], "phase_A")
        self.assertEqual(by_fact_id[stage["fact_id"]]["target_scope"]["stage_ref"], "stage_2")
        self.assertEqual(by_fact_id[detector["fact_id"]]["target_scope"]["detector_ref"], "detector_D12")
        self.assertEqual(by_fact_id[phase["fact_id"]]["target_scope"]["lane_ref"], None)

    def test_does_not_promote_generic_phase_stage_heading_to_specific_refs(self):
        heading = _fact(
            "phase_label_from_controller_config",
            "Phases, Stages and Streams",
            "config.docx -> heading 3",
            source_file="config.docx",
        )

        output = assign_geometry_to_lanes(_extracted([heading]))

        assignment = output["semantic_assignments"][0]
        self.assertEqual(assignment["target_scope"]["intersection_ref"], "intersection_1")
        self.assertNotIn("phase_ref", assignment["target_scope"])
        self.assertNotIn("stage_ref", assignment["target_scope"])
        self.assertEqual(assignment["assignment_method"], "intersection_semantic_scope")

    def test_assigns_road_name_fact_to_approach_scope(self):
        road_name = _fact("road_name_candidate_from_ordnance_survey", "London Road", "feature 4 properties", source_file="site.geojson")

        output = assign_geometry_to_lanes(_extracted([road_name]))

        assignment = output["semantic_assignments"][0]
        self.assertEqual(assignment["target_scope"]["approach_ref"], "approach_london_road")

    def test_cad_lanes_take_priority_over_pdf_lane_candidates(self):
        cad_lane = _fact(
            "lane_geometry_candidate_from_cad",
            [[0, 0], [10, 0]],
            "site.dxf -> modelspace entity 1 layer LANE_MAIN",
            source_file="site.dxf",
        )
        pdf_lane = _fact(
            "lane_line_candidate_from_pdf_vector",
            {"geometry": {"x0": 0, "top": 10, "x1": 100, "bottom": 10}},
            "drawing.pdf -> page 1 vector line 1",
            source_file="drawing.pdf",
        )

        output = assign_geometry_to_lanes(_extracted([cad_lane, pdf_lane]))

        self.assertEqual(output["lane_source_tier"], 0)
        self.assertEqual(len(output["lanes"]), 1)
        self.assertEqual(output["lanes"][0]["source_fact_name"], "lane_geometry_candidate_from_cad")
        pdf_assignment = next(item for item in output["assigned_facts"] if item["fact_id"] == pdf_lane["fact_id"])
        self.assertEqual(pdf_assignment["target_scope"]["lane_ref"], None)
        self.assertEqual(pdf_assignment["assignment_method"], "intersection_only")

    def test_ignores_legacy_cad_utility_layers_as_lane_definitions(self):
        duct = _fact(
            "lane_geometry_candidate_from_cad",
            [[0, 0], [1, 0]],
            "site.dxf -> modelspace entity 1 layer DUCTS",
            source_file="site.dxf",
        )
        loop = _fact(
            "lane_geometry_candidate_from_cad",
            [[0, 0], [1, 1]],
            "site.dxf -> modelspace entity 2 layer LOOPS",
            source_file="site.dxf",
        )
        pdf_lane = _fact(
            "lane_line_candidate_from_pdf_vector",
            {"geometry": {"x0": 0, "top": 10, "x1": 100, "bottom": 10}},
            "drawing.pdf -> page 1 vector line 1",
            source_file="drawing.pdf",
        )

        output = assign_geometry_to_lanes(_extracted([duct, loop, pdf_lane]))

        self.assertEqual(output["lane_source_tier"], 2)
        self.assertEqual(len(output["lanes"]), 1)
        self.assertEqual(output["lanes"][0]["source_fact_name"], "lane_line_candidate_from_pdf_vector")

    def test_pdf_lane_candidates_cluster_when_pdf_is_only_lane_source(self):
        first = _fact(
            "lane_line_candidate_from_pdf_vector",
            {"geometry": {"x0": 0, "top": 10, "x1": 100, "bottom": 10}},
            "drawing.pdf -> page 1 vector line 1",
            source_file="drawing.pdf",
        )
        second = _fact(
            "lane_line_candidate_from_pdf_vector",
            {"geometry": {"x0": 1, "top": 11, "x1": 101, "bottom": 11}},
            "drawing.pdf -> page 1 vector line 2",
            source_file="drawing.pdf",
        )
        third = _fact(
            "lane_line_candidate_from_pdf_vector",
            {"geometry": {"x0": 0, "top": 200, "x1": 100, "bottom": 200}},
            "drawing.pdf -> page 1 vector line 3",
            source_file="drawing.pdf",
        )

        output = assign_geometry_to_lanes(_extracted([first, second, third]))

        self.assertEqual(output["lane_source_tier"], 2)
        self.assertEqual(len(output["lanes"]), 2)
        self.assertTrue(output["lanes"][0]["clustered_from"])

    def test_pdf_lane_fallback_is_suppressed_when_too_many_clusters_are_found(self):
        facts = [
            _fact(
                "lane_line_candidate_from_pdf_vector",
                {"geometry": {"x0": 0, "top": index * 10, "x1": 100, "bottom": index * 10}},
                f"drawing.pdf -> page 1 vector line {index}",
                source_file="drawing.pdf",
            )
            for index in range(51)
        ]

        output = assign_geometry_to_lanes(_extracted(facts))

        self.assertEqual(output["lane_source_tier"], -1)
        self.assertEqual(output["lanes"], [])

    def test_outputs_movement_lane_mapping_when_lane_label_matches_movement_ref(self):
        lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 0], [10, 0]],
                "label": "London Road inbound ahead",
            },
            "site.dxf -> modelspace entity 1 layer LANE_MAIN",
            source_file="site.dxf",
        )
        movement = _fact(
            "phase_movement_mapping_from_controller_config",
            {
                "phase_ref": "phase_A",
                "movement_ref": "movement_london_road_inbound_ahead",
                "movement_text": "LONDON ROAD INBOUND AHEAD",
                "road_name": "London Road",
                "direction": "inbound",
                "maneuver": "ahead",
            },
            "config.pdf -> page 6 table 1 row 2",
            source_file="config.pdf",
        )

        output = assign_geometry_to_lanes(_extracted([lane, movement]))

        mapping = output["movement_lane_mappings"][0]
        self.assertEqual(mapping["movement_ref"], "movement_london_road_inbound_ahead")
        self.assertEqual(mapping["lane_ref"], "lane_1")
        self.assertEqual(mapping["phase_refs"], ["phase_A"])
        self.assertEqual(mapping["assignment_method"], "lane_label_movement_match")

    def test_outputs_movement_lane_mapping_from_spatial_cad_movement_label(self):
        lane = _fact(
            "lane_geometry_candidate_from_cad",
            [[0, 0], [10, 0]],
            "site.dxf -> modelspace entity 1 layer LANE_MAIN",
            source_file="site.dxf",
        )
        cad_label = _fact(
            "cad_movement_label_candidate",
            {
                "label": "London Road inbound ahead",
                "movement_ref": "movement_london_road_inbound_ahead",
                "movement_text": "London Road inbound ahead",
                "geometry": {"x": 5, "y": 1},
            },
            "site.dxf -> modelspace entity 2 layer LABELS",
            source_file="site.dxf",
        )
        movement = _fact(
            "phase_movement_mapping_from_controller_config",
            {
                "phase_ref": "phase_A",
                "movement_ref": "movement_london_road_inbound_ahead",
                "movement_text": "LONDON ROAD INBOUND AHEAD",
            },
            "config.pdf -> page 6 table 1 row 2",
            source_file="config.pdf",
        )

        output = assign_geometry_to_lanes(_extracted([lane, cad_label, movement]))

        mapping = next(item for item in output["movement_lane_mappings"] if item["lane_ref"] == "lane_1")
        self.assertEqual(mapping["movement_ref"], "movement_london_road_inbound_ahead")
        self.assertEqual(mapping["phase_refs"], ["phase_A"])
        self.assertEqual(mapping["assignment_method"], "cad_movement_label_nearest_lane")
        label_assignment = next(item for item in output["assigned_facts"] if item["fact_id"] == cad_label["fact_id"])
        self.assertEqual(label_assignment["target_scope"]["lane_ref"], "lane_1")

    def test_reports_unmatched_movement_lane_mapping_when_lane_context_is_missing(self):
        lane = _fact(
            "lane_geometry_candidate_from_cad",
            [[0, 0], [10, 0]],
            "site.dxf -> modelspace entity 1 layer LANE_MAIN",
            source_file="site.dxf",
        )
        movement = _fact(
            "phase_movement_mapping_from_controller_config",
            {
                "phase_ref": "phase_A",
                "movement_ref": "movement_london_road_inbound_ahead",
                "movement_text": "LONDON ROAD INBOUND AHEAD",
                "road_name": "London Road",
                "direction": "inbound",
                "maneuver": "ahead",
            },
            "config.pdf -> page 6 table 1 row 2",
            source_file="config.pdf",
        )

        output = assign_geometry_to_lanes(_extracted([lane, movement]))

        mapping = output["movement_lane_mappings"][0]
        self.assertEqual(mapping["movement_ref"], "movement_london_road_inbound_ahead")
        self.assertEqual(mapping["lane_ref"], None)
        self.assertEqual(mapping["requires_context_match"], True)
        self.assertEqual(mapping["unmatched_reason"], "no_lane_movement_label")

    def test_uses_cad_signal_arrow_as_lane_proxy_when_lane_geometry_is_missing(self):
        arrow = _fact(
            "cad_arrow_block_candidate",
            {
                "name": "HD003P",
                "geometry": {"x": 10, "y": 20},
                "semantic_type": "signal_arrow",
                "arrow_direction_candidate": "right",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 3 layer SIGNALS",
            source_file="site.dxf",
        )
        movement = _fact(
            "phase_movement_mapping_from_controller_config",
            {
                "phase_ref": "phase_C",
                "movement_ref": "movement_london_road_outbound_right_turn",
                "movement_text": "LONDON ROAD OUTBOUND RIGHT TURN",
                "road_name": "London Road",
                "direction": "outbound",
                "maneuver": "right_turn",
            },
            "config.pdf -> page 6 table 1 row 2",
            source_file="config.pdf",
        )

        output = assign_geometry_to_lanes(_extracted([arrow, movement]))

        self.assertEqual(output["lane_source_tier"], 3)
        self.assertEqual(output["lanes"][0]["source_fact_name"], "cad_arrow_block_candidate")
        self.assertEqual(output["lanes"][0]["lane_semantic_hint"], "right_turn")
        mapping = output["movement_lane_mappings"][0]
        self.assertEqual(mapping["movement_ref"], "movement_london_road_outbound_right_turn")
        self.assertEqual(mapping["lane_ref"], "lane_1")
        self.assertEqual(mapping["phase_refs"], ["phase_C"])
        self.assertEqual(mapping["assignment_method"], "cad_signal_arrow_direction_match")
        self.assertEqual(mapping["requires_context_match"], True)

    def test_creates_semantic_lane_proxy_for_unmatched_structured_movement(self):
        movement = _fact(
            "phase_movement_mapping_from_controller_config",
            {
                "phase_ref": "phase_A",
                "movement_ref": "movement_london_road_inbound_ahead",
                "movement_text": "LONDON ROAD INBOUND AHEAD",
                "road_name": "London Road",
                "direction": "inbound",
                "maneuver": "ahead",
            },
            "config.pdf -> page 6 table 1 row 2",
            source_file="config.pdf",
        )

        output = assign_geometry_to_lanes(_extracted([movement]))

        self.assertEqual(output["lane_source_tier"], 4)
        self.assertEqual(output["lanes"][0]["source_fact_name"], "semantic_movement_lane_proxy")
        self.assertEqual(output["lanes"][0]["movement_ref"], "movement_london_road_inbound_ahead")
        self.assertEqual(output["lanes"][0]["lane_semantic_basis"], "structured_movement_without_geometry")
        self.assertEqual(output["lanes"][0]["requires_context_match"], True)
        mapping = output["movement_lane_mappings"][0]
        self.assertEqual(mapping["movement_ref"], "movement_london_road_inbound_ahead")
        self.assertEqual(mapping["lane_ref"], "lane_1")
        self.assertEqual(mapping["assignment_method"], "semantic_movement_lane_proxy")
        self.assertEqual(mapping["requires_context_match"], True)


def _fact(fact_name: str, value: object, location: str, source_file: str = "site.dxf") -> dict:
    return make_fact(fact_name, value, location, 0.75, source_file=source_file)


def _extracted(facts: list[dict]) -> dict:
    by_source: dict[str, list[dict]] = {}
    for fact in facts:
        by_source.setdefault(fact["source_file"], []).append(fact)
    return {
        "site_id": "1003",
        "source_files": [
            {
                "source_file": source_file,
                "file_type": Path(source_file).suffix.lower().lstrip("."),
                "parser": "test_parser",
                "status": "parsed",
                "extracted_facts": source_facts,
            }
            for source_file, source_facts in by_source.items()
        ],
    }


def _test_dir() -> Path:
    path = Path("outputs") / f"test_geometry_assignment_{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    return path


if __name__ == "__main__":
    unittest.main()
