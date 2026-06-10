import json
import unittest
import uuid
from pathlib import Path

from mapemgen.assignment.geometry import assign_geometry_to_lanes
from mapemgen.cli import main


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
        output = assign_geometry_to_lanes(_extracted([lane_a, lane_b, stop_line]))

        self.assertEqual(output["intersections"][0]["intersection_ref"], "intersection_1")
        self.assertEqual([lane["lane_ref"] for lane in output["lanes"]], ["lane_1", "lane_2"])
        stop_assignment = next(item for item in output["assigned_facts"] if item["fact_id"] == stop_line["fact_id"])
        self.assertEqual(stop_assignment["target_scope"]["intersection_ref"], "intersection_1")
        self.assertEqual(stop_assignment["target_scope"]["lane_ref"], "lane_1")
        self.assertEqual(stop_assignment["assignment_method"], "nearest_lane_centroid")

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
        input_path.write_text(json.dumps(_extracted([_fact("lane_geometry_candidate_from_cad", [[0, 0], [5, 0]], "entity 1")])), encoding="utf-8")

        exit_code = main(["assign-geometry", "--input", str(input_path), "--out-dir", str(out_dir)])

        output = json.loads((out_dir / "geometry_assignments.partial.json").read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(output["lanes"][0]["lane_ref"], "lane_1")


def _fact(fact_name: str, value: object, location: str, source_file: str = "site.dxf") -> dict:
    fact_id = f"fact_{abs(hash((fact_name, str(value), location, source_file))) % 1000000000000:012d}"
    return {
        "fact_id": fact_id,
        "fact_name": fact_name,
        "payload": {"value": value},
        "evidence_location": location,
        "confidence": 0.75,
        "source_file": source_file,
    }


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
