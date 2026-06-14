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

    def test_promotes_anchored_cad_road_markings_to_lane_candidates(self):
        marking = _fact(
            "road_marking_candidate_from_cad",
            {"geometry": [[0, 0], [40, 0]], "layer": "A1-WHITE-LINES", "semantic_type": "road_marking"},
            "site.dxf -> modelspace entity 1 layer A1-WHITE-LINES",
            source_file="site.dxf",
        )
        signal_head = _fact(
            "cad_signal_head_candidate",
            {"name": "HD001", "geometry": {"x": 8, "y": 4}, "semantic_type": "signal_head"},
            "site.dxf -> modelspace entity 2 layer UTC SIGNALS",
            source_file="site.dxf",
        )
        stop_line = _fact(
            "stop_line_from_cad",
            {"geometry": [[35, -3], [35, 3]], "layer": "STOPLINE", "semantic_type": "stop_line"},
            "site.dxf -> modelspace entity 3 layer STOPLINE",
            source_file="site.dxf",
        )

        output = assign_geometry_to_lanes(_extracted([marking, signal_head, stop_line]))

        self.assertEqual(output["lane_source_tier"], 0)
        self.assertEqual(len(output["lanes"]), 1)
        lane = output["lanes"][0]
        self.assertEqual(lane["source_fact_name"], "lane_geometry_candidate_from_cad")
        self.assertEqual(lane["lane_semantic_basis"], "anchored_cad_road_marking_lane_candidate")
        self.assertEqual(lane["lane_validation_status"], "cad_context_confirmed")

    def test_does_not_promote_unanchored_cad_road_markings_to_lanes(self):
        marking = _fact(
            "road_marking_candidate_from_cad",
            {"geometry": [[0, 0], [40, 0]], "layer": "A1-WHITE-LINES", "semantic_type": "road_marking"},
            "site.dxf -> modelspace entity 1 layer A1-WHITE-LINES",
            source_file="site.dxf",
        )

        output = assign_geometry_to_lanes(_extracted([marking]))

        self.assertEqual(output["lane_source_tier"], -1)
        self.assertEqual(output["lanes"], [])

    def test_excludes_non_site_cad_lane_candidates_from_lane_definitions(self):
        foreign_lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 0], [100, 0]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "local_data/site_1003/1037_Bathwick St_overlay.dwg -> modelspace entity 1 layer LINES",
            source_file="local_data/site_1003/1037_Bathwick St_overlay.dwg",
        )
        own_lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 10], [100, 10]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "local_data/site_1003/1003_Cleveland Place.dwg -> modelspace entity 2 layer LINES",
            source_file="local_data/site_1003/1003_Cleveland Place.dwg",
        )

        output = assign_geometry_to_lanes(_extracted([foreign_lane, own_lane], site_id="1003"))

        self.assertEqual(len(output["lanes"]), 1)
        self.assertEqual(output["lanes"][0]["clustered_from"], [own_lane["fact_id"]])

    def test_excludes_topographic_cad_lane_candidates_from_lane_definitions(self):
        topo_lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 0], [100, 0]],
                "layer": "R_CL",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "OS-TOPO.dwg -> modelspace entity 1 layer R_CL",
            source_file="OS-TOPO.dwg",
        )
        pdf_lane = _fact(
            "lane_line_candidate_from_pdf_vector",
            {"geometry": {"x0": 0, "top": 10, "x1": 100, "bottom": 10}},
            "drawing.pdf -> page 1 vector line 1",
            source_file="drawing.pdf",
        )

        output = assign_geometry_to_lanes(_extracted([topo_lane, pdf_lane], site_id="1003"))

        self.assertEqual(output["lane_source_tier"], 2)
        self.assertEqual(len(output["lanes"]), 1)
        self.assertEqual(output["lanes"][0]["clustered_from"], [pdf_lane["fact_id"]])

    def test_excludes_non_site_cad_arrow_fallback_from_lane_definitions(self):
        foreign_arrow = _fact(
            "cad_arrow_block_candidate",
            {
                "name": "Right turn arrow",
                "geometry": {"x": 10, "y": 10},
                "semantic_type": "signal_arrow",
                "arrow_direction_candidate": "right",
                "requires_context_match": True,
            },
            "local_data/site_1003/1037_Bathwick St_overlay.dwg -> modelspace entity 1 layer SIGNALS",
            source_file="local_data/site_1003/1037_Bathwick St_overlay.dwg",
        )

        output = assign_geometry_to_lanes(_extracted([foreign_arrow], site_id="1003"))

        self.assertEqual(output["lanes"], [])
        self.assertEqual(output["lane_source_tier"], -1)

    def test_excludes_topographic_cad_arrow_fallback_from_lane_definitions(self):
        topo_arrow = _fact(
            "cad_arrow_block_candidate",
            {
                "name": "FLOW",
                "geometry": {"x": 10, "y": 10},
                "semantic_type": "signal_arrow",
                "arrow_direction_candidate": "ahead",
                "requires_context_match": True,
            },
            "OS-TOPO.dwg -> modelspace entity 1 layer FLOW",
            source_file="OS-TOPO.dwg",
        )

        output = assign_geometry_to_lanes(_extracted([topo_arrow], site_id="1003"))

        self.assertEqual(output["lanes"], [])
        self.assertEqual(output["lane_source_tier"], -1)

    def test_excludes_non_site_cad_movement_label_from_semantic_lane_proxy(self):
        foreign_label = _fact(
            "cad_movement_label_candidate",
            {
                "label": "RIGHT",
                "movement_ref": "movement_right",
                "movement_text": "RIGHT",
                "geometry": {"x": 10, "y": 10},
            },
            "local_data/site_1003/1065_1068_1067_1071 Sydney_Gdn_Overlay.dwg -> modelspace entity 1 layer LINES",
            source_file="local_data/site_1003/1065_1068_1067_1071 Sydney_Gdn_Overlay.dwg",
        )

        output = assign_geometry_to_lanes(_extracted([foreign_label], site_id="1003"))

        self.assertEqual(output["lanes"], [])
        self.assertEqual(output["lane_source_tier"], -1)

    def test_excludes_topographic_cad_movement_label_from_semantic_lane_proxy(self):
        topo_label = _fact(
            "cad_movement_label_candidate",
            {
                "label": "EB",
                "movement_ref": "movement_eb",
                "movement_text": "EB",
                "geometry": {"x": 10, "y": 10},
            },
            "OS-TOPO.dwg -> modelspace entity 1 layer TEXT",
            source_file="OS-TOPO.dwg",
        )

        output = assign_geometry_to_lanes(_extracted([topo_label], site_id="1003"))

        self.assertEqual(output["lanes"], [])
        self.assertEqual(output["lane_source_tier"], -1)

    def test_excludes_cycle_coloured_area_cad_lane_candidates_from_vehicle_lane_definitions(self):
        cycle_lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 0], [100, 0]],
                "layer": "CH-01-H_ColouredAreas_CycleLane",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dwg -> modelspace entity 1 layer CH-01-H_ColouredAreas_CycleLane",
            source_file="site.dwg",
        )
        vehicle_lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 10], [100, 10]],
                "layer": "KTS_LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dwg -> modelspace entity 2 layer KTS_LINES",
            source_file="site.dwg",
        )

        output = assign_geometry_to_lanes(_extracted([cycle_lane, vehicle_lane], site_id="378L"))

        self.assertEqual(len(output["lanes"]), 1)
        self.assertEqual(output["lanes"][0]["clustered_from"], [vehicle_lane["fact_id"]])

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

    def test_generic_cad_lane_candidates_cluster_into_lane_corridors(self):
        first = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 10], [100, 10]],
                "layer": "KTS_LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 1 layer KTS_LINES",
            source_file="site.dxf",
        )
        second = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[1, 11], [101, 11]],
                "layer": "KTS_LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 2 layer KTS_LINES",
            source_file="site.dxf",
        )
        third = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 40], [100, 40]],
                "layer": "KTS_LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 3 layer KTS_LINES",
            source_file="site.dxf",
        )

        output = assign_geometry_to_lanes(_extracted([first, second, third]))

        self.assertEqual(output["lane_source_tier"], 0)
        self.assertEqual(len(output["lanes"]), 2)
        self.assertTrue(output["lanes"][0]["clustered_from"])

    def test_confirms_heuristic_cad_lane_with_independent_cad_context_evidence(self):
        lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 10], [100, 10]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 1 layer LINES",
            source_file="site.dxf",
        )
        stop_line = _fact(
            "stop_line_from_cad",
            {"geometry": [[90, 8], [90, 12]], "layer": "SCT_LOOPS", "semantic_type": "stop_line"},
            "site.dxf -> modelspace entity 2 layer SCT_LOOPS",
            source_file="site.dxf",
        )
        signal_head = _fact(
            "cad_signal_head_candidate",
            {"name": "HD001S", "geometry": {"x": 96, "y": 11}, "semantic_type": "signal_head"},
            "site.dxf -> modelspace entity 3 layer SIGNALS",
            source_file="site.dxf",
        )

        output = assign_geometry_to_lanes(_extracted([lane, stop_line, signal_head]))

        lane_output = output["lanes"][0]
        self.assertEqual(lane_output["lane_validation_status"], "cad_context_confirmed")
        self.assertEqual(lane_output["requires_context_match"], False)
        self.assertEqual(set(lane_output["validation_evidence_groups"]), {"signal_head", "stop_line"})
        self.assertEqual(len(lane_output["validation_evidence_fact_ids"]), 2)
        audit = {item["method"]: item for item in output["assignment_method_audit"]}
        self.assertEqual(audit["cad_context_validation"]["matched_count"], 1)
        self.assertEqual(audit["cad_context_validation"]["examples"][0]["lane_ref"], "lane_1")

    def test_keeps_heuristic_cad_lane_unconfirmed_with_single_context_evidence_group(self):
        lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 10], [100, 10]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 1 layer LINES",
            source_file="site.dxf",
        )
        stop_line = _fact(
            "stop_line_from_cad",
            {"geometry": [[90, 8], [90, 12]], "layer": "SCT_LOOPS", "semantic_type": "stop_line"},
            "site.dxf -> modelspace entity 2 layer SCT_LOOPS",
            source_file="site.dxf",
        )

        output = assign_geometry_to_lanes(_extracted([lane, stop_line]))

        lane_output = output["lanes"][0]
        self.assertEqual(lane_output["lane_validation_status"], "needs_context_match")
        self.assertEqual(lane_output["requires_context_match"], True)
        self.assertEqual(lane_output["validation_evidence_groups"], ["stop_line"])
        self.assertEqual(lane_output["unconfirmed_reason"], "insufficient_distinct_cad_entity_locations")
        self.assertEqual(lane_output["missing_validation_evidence_group_count"], 1)
        self.assertEqual(lane_output["nearest_validation_candidates"][0]["group"], "stop_line")
        self.assertEqual(lane_output["nearest_validation_candidates"][0]["fact_name"], "stop_line_from_cad")
        self.assertLess(lane_output["nearest_validation_candidates"][0]["distance_to_lane"], 50)

    def test_confirms_parallel_cad_lanes_from_shared_approach_context(self):
        lane_a = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 10], [100, 10]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 1 layer LINES",
            source_file="site.dxf",
        )
        lane_b = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 14], [100, 14]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 2 layer LINES",
            source_file="site.dxf",
        )
        stop_line = _fact(
            "stop_line_from_cad",
            {"geometry": [[90, 8], [90, 12]], "layer": "STOP", "semantic_type": "stop_line"},
            "site.dxf -> modelspace entity 3 layer STOP",
            source_file="site.dxf",
        )
        signal_head = _fact(
            "cad_signal_head_candidate",
            {"name": "HD001S", "geometry": {"x": 96, "y": 16}, "semantic_type": "signal_head"},
            "site.dxf -> modelspace entity 4 layer SIGNALS",
            source_file="site.dxf",
        )

        output = assign_geometry_to_lanes(_extracted([lane_a, lane_b, stop_line, signal_head]))

        self.assertEqual(len(output["approaches"]), 1)
        approach = output["approaches"][0]
        self.assertEqual(approach["approach_validation_status"], "cad_context_confirmed")
        self.assertEqual(set(approach["lane_refs"]), {"lane_1", "lane_2"})
        self.assertEqual(set(approach["validation_evidence_groups"]), {"signal_head", "stop_line"})
        for lane in output["lanes"]:
            self.assertEqual(lane["approach_ref"], approach["approach_ref"])
            self.assertEqual(lane["lane_validation_status"], "cad_context_confirmed")
            self.assertEqual(lane["lane_confirmation_basis"], "approach_context_validation")
            self.assertEqual(lane["requires_context_match"], False)

    def test_does_not_share_approach_context_across_distant_cad_lanes(self):
        near_lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 10], [100, 10]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 1 layer LINES",
            source_file="site.dxf",
        )
        distant_lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 200], [100, 200]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 2 layer LINES",
            source_file="site.dxf",
        )
        stop_line = _fact(
            "stop_line_from_cad",
            {"geometry": [[90, 8], [90, 12]], "layer": "STOP", "semantic_type": "stop_line"},
            "site.dxf -> modelspace entity 3 layer STOP",
            source_file="site.dxf",
        )
        signal_head = _fact(
            "cad_signal_head_candidate",
            {"name": "HD001S", "geometry": {"x": 96, "y": 11}, "semantic_type": "signal_head"},
            "site.dxf -> modelspace entity 4 layer SIGNALS",
            source_file="site.dxf",
        )

        output = assign_geometry_to_lanes(_extracted([near_lane, distant_lane, stop_line, signal_head]))

        self.assertEqual(len(output["approaches"]), 2)
        by_lane_ref = {lane["lane_ref"]: lane for lane in output["lanes"]}
        self.assertEqual(by_lane_ref["lane_1"]["lane_validation_status"], "cad_context_confirmed")
        self.assertEqual(by_lane_ref["lane_2"]["lane_validation_status"], "out_of_scope_candidate")
        self.assertEqual(by_lane_ref["lane_2"]["lane_confirmation_basis"], "distant_insufficient_context")

    def test_adopts_nearby_orphan_cad_lane_into_confirmed_approach(self):
        approach_lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 10], [100, 10]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 1 layer LINES",
            source_file="site.dxf",
        )
        orphan_lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[200, 18], [300, 18]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 2 layer LINES",
            source_file="site.dxf",
        )
        stop_line = _fact(
            "stop_line_from_cad",
            {"geometry": [[90, 8], [90, 12]], "layer": "STOP", "semantic_type": "stop_line"},
            "site.dxf -> modelspace entity 3 layer STOP",
            source_file="site.dxf",
        )
        signal_head = _fact(
            "cad_signal_head_candidate",
            {"name": "HD001S", "geometry": {"x": 120, "y": 12}, "semantic_type": "signal_head"},
            "site.dxf -> modelspace entity 4 layer SIGNALS",
            source_file="site.dxf",
        )

        output = assign_geometry_to_lanes(_extracted([approach_lane, orphan_lane, stop_line, signal_head]))

        by_lane_ref = {lane["lane_ref"]: lane for lane in output["lanes"]}
        self.assertEqual(by_lane_ref["lane_1"]["lane_validation_status"], "cad_context_confirmed")
        self.assertEqual(by_lane_ref["lane_2"]["lane_validation_status"], "cad_context_confirmed")
        self.assertEqual(by_lane_ref["lane_2"]["lane_confirmation_basis"], "nearby_confirmed_approach_adoption")
        self.assertEqual(by_lane_ref["lane_2"]["requires_context_match"], False)
        self.assertEqual(by_lane_ref["lane_2"]["adopted_from_approach_ref"], by_lane_ref["lane_1"]["approach_ref"])

    def test_marks_distant_unconfirmed_cad_lane_as_out_of_scope_candidate(self):
        lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 10], [100, 10]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 1 layer LINES",
            source_file="site.dxf",
        )
        distant_lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[500, 200], [600, 200]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 2 layer LINES",
            source_file="site.dxf",
        )
        stop_line = _fact(
            "stop_line_from_cad",
            {"geometry": [[90, 8], [90, 12]], "layer": "STOP", "semantic_type": "stop_line"},
            "site.dxf -> modelspace entity 3 layer STOP",
            source_file="site.dxf",
        )
        signal_head = _fact(
            "cad_signal_head_candidate",
            {"name": "HD001S", "geometry": {"x": 96, "y": 11}, "semantic_type": "signal_head"},
            "site.dxf -> modelspace entity 4 layer SIGNALS",
            source_file="site.dxf",
        )
        road_text = _fact(
            "cad_text_label",
            {"text": "HIGH STREET", "geometry": {"x": 550, "y": 205}},
            "site.dxf -> modelspace entity 5 layer ROADTXT",
            source_file="site.dxf",
        )

        output = assign_geometry_to_lanes(_extracted([lane, distant_lane, stop_line, signal_head, road_text]))

        by_lane_ref = {lane["lane_ref"]: lane for lane in output["lanes"]}
        self.assertEqual(by_lane_ref["lane_1"]["lane_validation_status"], "cad_context_confirmed")
        self.assertEqual(by_lane_ref["lane_2"]["lane_validation_status"], "out_of_scope_candidate")
        self.assertEqual(by_lane_ref["lane_2"]["lane_confirmation_basis"], "distant_insufficient_context")
        self.assertEqual(by_lane_ref["lane_2"]["out_of_scope_reason"], "distant_from_confirmed_cad_context")

    def test_assignment_method_audit_reports_pdf_coordinate_mismatch_examples(self):
        cad_lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 10], [100, 10]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 1 layer LINES",
            source_file="site.dxf",
        )
        pdf_fact = _fact(
            "lane_line_candidate_from_pdf_vector",
            {"geometry": {"x0": 0, "top": 10, "x1": 100, "bottom": 10}},
            "drawing.pdf -> page 1 vector line 1",
            source_file="drawing.pdf",
        )

        output = assign_geometry_to_lanes(_extracted([cad_lane, pdf_fact]))

        audit = {item["method"]: item for item in output["assignment_method_audit"]}
        self.assertEqual(audit["pdf_same_page_assignment"]["matched_count"], 0)
        self.assertEqual(audit["pdf_to_cad_transform_required"]["candidate_count"], 1)
        self.assertEqual(audit["pdf_to_cad_transform_required"]["examples"][0]["fact_name"], "lane_line_candidate_from_pdf_vector")
        self.assertEqual(audit["pdf_to_cad_transform_required"]["examples"][0]["reason"], "pdf_page_without_cad_transform")

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

    def test_does_not_auto_map_cad_key_legend_movement_label_to_lane(self):
        lane = _fact(
            "lane_geometry_candidate_from_cad",
            {
                "geometry": [[0, 0], [10, 0]],
                "layer": "LINES",
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            "site.dxf -> modelspace entity 1 layer LINES",
            source_file="site.dxf",
        )
        cad_label = _fact(
            "cad_movement_label_candidate",
            {
                "label": "AHEAD ONLY",
                "movement_ref": "movement_ahead_only",
                "movement_text": "AHEAD ONLY",
                "geometry": {"x": 5, "y": 1},
            },
            "site.dxf -> modelspace entity 2 layer UTC_KEY",
            source_file="site.dxf",
        )

        output = assign_geometry_to_lanes(_extracted([lane, cad_label]))

        mapping = output["movement_lane_mappings"][0]
        self.assertEqual(mapping["lane_ref"], None)
        self.assertEqual(mapping["assignment_method"], "needs_context_match")
        self.assertEqual(mapping["unmatched_reason"], "cad_movement_label_on_key_or_notes_layer")

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


def _extracted(facts: list[dict], site_id: str = "1003") -> dict:
    by_source: dict[str, list[dict]] = {}
    for fact in facts:
        by_source.setdefault(fact["source_file"], []).append(fact)
    return {
        "site_id": site_id,
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
