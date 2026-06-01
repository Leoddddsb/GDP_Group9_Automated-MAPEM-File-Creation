import json
import os
import sys
import types
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

from mapemgen.cli import main
from mapemgen.ingestion.cad import extract_dwg_facts, extract_dxf_facts
from mapemgen.ingestion.docx_tables import extract_docx_facts
from mapemgen.ingestion.facts import extract_site_folder_facts
from mapemgen.ingestion.gis import extract_gis_facts
from mapemgen.ingestion.mova import extract_mova_facts
from mapemgen.ingestion.pdf_tables import extract_pdf_facts
from mapemgen.ingestion.ram_text import extract_ram_text_facts
from mapemgen.ingestion.zip_packages import extract_zip_facts


class ExtractionTest(unittest.TestCase):
    def test_ram_text_extracts_mapem_relevant_keyword_lines(self):
        path = _test_dir() / "1003_RAMData.8tx"
        path.write_text(
            "Phase A override\nStage 2 demand\nIntergreen A B 5\nDetector D12\nI/O allocation 7\n",
            encoding="utf-8",
        )

        facts = extract_ram_text_facts(path)

        fact_types = {fact["fact_type"] for fact in facts}
        self.assertIn("phase_candidate", fact_types)
        self.assertIn("stage_candidate", fact_types)
        self.assertIn("intergreen_candidate", fact_types)
        self.assertIn("detector_candidate", fact_types)
        self.assertIn("io_allocation_candidate", fact_types)
        self.assertTrue(all(fact["evidence_location"].startswith("line ") for fact in facts))

    def test_zip_parser_classifies_dwg_members_and_removes_temporary_extraction(self):
        path = _test_dir() / "site.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("T1003 Root.dwg", "root")
            archive.writestr("xref/OS-TOPO.dwg", "xref")
            archive.writestr("notes/readme.txt", "notes")

        facts = extract_zip_facts(path, member_parser=lambda _path, _depth: [])

        by_type = {}
        for fact in facts:
            by_type.setdefault(fact["fact_type"], []).append(fact["value"])
        self.assertIn("T1003 Root.dwg", by_type["root_dwg_candidate"])
        self.assertIn("xref/OS-TOPO.dwg", by_type["xref_dwg_candidate"])
        self.assertIn("xref/OS-TOPO.dwg", by_type["topographic_drawing_available"])
        self.assertFalse((path.parent / "xref").exists())

    def test_zip_parser_recursively_extracts_supported_members(self):
        path = _test_dir() / "site.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("notes/controller.txt", "Detector D12")

        facts = extract_zip_facts(path)

        detector = next(fact for fact in facts if fact["fact_type"] == "detector_candidate")
        self.assertEqual(detector["value"], "Detector D12")
        self.assertEqual(detector["evidence_location"], "archive member notes/controller.txt -> line 1")

    def test_zip_parser_recursively_extracts_nested_zip_members(self):
        nested_path = _test_dir() / "nested.zip"
        with zipfile.ZipFile(nested_path, "w") as archive:
            archive.writestr("ram/site.8tx", "Phase A")
        path = _test_dir() / "site.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.write(nested_path, "packages/nested.zip")

        facts = extract_zip_facts(path)

        phase = next(fact for fact in facts if fact["fact_type"] == "phase_candidate")
        self.assertEqual(
            phase["evidence_location"],
            "archive member packages/nested.zip -> archive member ram/site.8tx -> line 1",
        )

    def test_zip_parser_rejects_path_traversal_member(self):
        path = _test_dir() / "site.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("../outside.txt", "Detector D12")

        facts = extract_zip_facts(path)

        rejected = next(fact for fact in facts if fact["fact_type"] == "archive_member_rejected")
        self.assertEqual(rejected["value"], "../outside.txt")

    def test_mova_parser_reports_shallow_extraction(self):
        path = _test_dir() / "site.mova"
        path.write_bytes(b"\x00DETECTOR D12\x00MOVA CONTROL\xff")

        facts = extract_mova_facts(path)

        self.assertEqual(facts[0]["fact_type"], "mova_shallow_extraction_limitation")
        self.assertTrue(any(fact["fact_type"] == "detector_candidate" for fact in facts))
        self.assertTrue(any(fact["fact_type"] == "control_candidate" for fact in facts))

    def test_geojson_parser_extracts_bounds_and_reference_point(self):
        path = _test_dir() / "roads.geojson"
        path.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"name": "London Road"},
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [[-1.0, 51.0], [-1.2, 51.2]],
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        facts = extract_gis_facts(path)

        self.assertIn(
            {"fact_type": "road_name", "value": "London Road", "evidence_location": "feature 1 properties.name", "confidence": 0.85},
            facts,
        )
        self.assertTrue(any(fact["fact_type"] == "coordinate_bounds" for fact in facts))
        self.assertTrue(any(fact["fact_type"] == "junction_centre_candidate" for fact in facts))

    def test_osm_parser_extracts_way_name_and_bounds(self):
        path = _test_dir() / "roads.osm"
        path.write_text(
            '<osm><node id="1" lat="51.0" lon="-1.0"/><node id="2" lat="51.2" lon="-1.2"/>'
            '<way id="3"><nd ref="1"/><nd ref="2"/><tag k="name" v="Oak Street"/></way></osm>',
            encoding="utf-8",
        )

        facts = extract_gis_facts(path)

        self.assertTrue(any(fact["fact_type"] == "road_name" and fact["value"] == "Oak Street" for fact in facts))
        self.assertTrue(any(fact["fact_type"] == "coordinate_bounds" for fact in facts))

    def test_dxf_parser_requires_ezdxf(self):
        with self.assertRaisesRegex(RuntimeError, "ezdxf"):
            extract_dxf_facts(_test_dir() / "site.dxf")

    def test_dwg_parser_requires_oda_file_converter(self):
        with self.assertRaisesRegex(RuntimeError, "ODA File Converter"):
            extract_dwg_facts(_test_dir() / "site.dwg")

    def test_dwg_parser_invokes_oda_file_converter(self):
        calls = []
        fake_odafc = types.SimpleNamespace(
            is_installed=lambda: True,
            readfile=lambda path: calls.append(path) or types.SimpleNamespace(modelspace=lambda: []),
        )
        fake_addons = types.ModuleType("ezdxf.addons")
        fake_addons.odafc = fake_odafc
        fake_ezdxf = types.ModuleType("ezdxf")
        fake_ezdxf.addons = fake_addons

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf, "ezdxf.addons": fake_addons}):
            facts = extract_dwg_facts("site.dwg")

        self.assertEqual(calls, ["site.dwg"])
        self.assertTrue(any(fact["fact_type"] == "cad_entity_counts" for fact in facts))

    def test_dwg_parser_uses_odafc_path_environment_variable(self):
        calls = []
        configured = {}
        fake_odafc = types.SimpleNamespace(
            is_installed=lambda: configured.get(("odafc-addon", "win_exec_path")) == r"E:\ODA\ODAFileConverter.exe",
            readfile=lambda path: calls.append(path) or types.SimpleNamespace(modelspace=lambda: []),
        )
        fake_addons = types.ModuleType("ezdxf.addons")
        fake_addons.odafc = fake_odafc
        fake_ezdxf = types.ModuleType("ezdxf")
        fake_ezdxf.addons = fake_addons
        fake_ezdxf.options = types.SimpleNamespace(
            set=lambda section, key, value: configured.__setitem__((section, key), value)
        )

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf, "ezdxf.addons": fake_addons}):
            with patch.dict(os.environ, {"ODAFC_PATH": r"E:\ODA\ODAFileConverter.exe"}):
                extract_dwg_facts("site.dwg")

        self.assertEqual(configured[("odafc-addon", "win_exec_path")], r"E:\ODA\ODAFileConverter.exe")
        self.assertEqual(calls, ["site.dwg"])

    def test_docx_parser_requires_python_docx(self):
        with patch.dict(sys.modules, {"docx": None}):
            with self.assertRaisesRegex(RuntimeError, "python-docx"):
                extract_docx_facts("site.docx")

    def test_pdf_parser_requires_pdfplumber(self):
        with patch.dict(sys.modules, {"pdfplumber": None}):
            with self.assertRaisesRegex(RuntimeError, "pdfplumber"):
                extract_pdf_facts("site.pdf")

    def test_shapefile_parser_requires_fiona(self):
        with patch.dict(sys.modules, {"fiona": None}):
            with self.assertRaisesRegex(RuntimeError, "fiona"):
                extract_gis_facts("site.shp")

    def test_docx_parser_preserves_paragraph_and_table_locations(self):
        fake_document = types.SimpleNamespace(
            paragraphs=[
                types.SimpleNamespace(text="Phase A"),
                types.SimpleNamespace(text="Junction Description: London Rd / Morrisons"),
                types.SimpleNamespace(text="SCN J04121 IP 172.16.52.53"),
            ],
            tables=[
                types.SimpleNamespace(
                    rows=[
                        types.SimpleNamespace(
                            cells=[types.SimpleNamespace(text="Intergreen"), types.SimpleNamespace(text="5")]
                        )
                    ]
                )
            ],
        )
        fake_docx = types.SimpleNamespace(Document=lambda _path: fake_document)

        with patch.dict(sys.modules, {"docx": fake_docx}):
            facts = extract_docx_facts("site.docx")

        self.assertTrue(any(fact["fact_type"] == "phase_candidate" and fact["evidence_location"] == "paragraph 1" for fact in facts))
        self.assertTrue(any(fact["fact_type"] == "intergreen_candidate" and fact["evidence_location"] == "table 1 row 1" for fact in facts))
        self.assertTrue(any(fact["fact_type"] == "site_description" and fact["value"] == "London Rd / Morrisons" for fact in facts))
        self.assertTrue(any(fact["fact_type"] == "scn" and fact["value"] == "J04121" for fact in facts))
        self.assertTrue(any(fact["fact_type"] == "ip_address" and fact["value"] == "172.16.52.53" for fact in facts))

    def test_pdf_parser_defers_image_page_and_preserves_table_location(self):
        page = types.SimpleNamespace(
            extract_text=lambda: "",
            extract_tables=lambda: [[["Detector", "D1"]]],
        )
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _ContextManager(types.SimpleNamespace(pages=[page])))

        with patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            facts = extract_pdf_facts("site.pdf")

        self.assertTrue(any(fact["fact_type"] == "needs_future_recognition" for fact in facts))
        self.assertTrue(any(fact["fact_type"] == "detector_candidate" and fact["evidence_location"] == "page 1 table 1 row 1" for fact in facts))

    def test_dxf_parser_extracts_geometry_labels_and_bounds(self):
        entities = [
            _Entity("LINE", "LANE_MAIN", start=(0, 0), end=(10, 5)),
            _Entity("TEXT", "LABELS", text="Phase A"),
            _Entity("INSERT", "SIGNALS", name="HEAD_A"),
        ]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            facts = extract_dxf_facts("site.dxf")

        self.assertTrue(any(fact["fact_type"] == "lane_candidate" for fact in facts))
        self.assertTrue(any(fact["fact_type"] == "cad_text_label" and fact["value"] == "Phase A" for fact in facts))
        self.assertTrue(any(fact["fact_type"] == "cad_block_reference" and fact["value"] == "HEAD_A" for fact in facts))
        self.assertTrue(any(fact["fact_type"] == "coordinate_bounds" for fact in facts))

    def test_coordinator_continues_after_corrupt_zip(self):
        folder = _test_dir()
        text_path = folder / "site.txt"
        zip_path = folder / "broken.zip"
        text_path.write_text("Detector D1", encoding="utf-8")
        zip_path.write_bytes(b"not a zip")

        output = extract_site_folder_facts(folder, site_id="1003")

        by_name = {Path(source["source_file"]).name: source for source in output["source_files"]}
        self.assertEqual(by_name["site.txt"]["status"], "parsed")
        self.assertEqual(by_name["broken.zip"]["status"], "parser_error")

    def test_extract_cli_scans_site_folder_without_inventory(self):
        folder = _test_dir()
        nested = folder / "nested"
        nested.mkdir()
        (folder / "site.txt").write_text("Phase A", encoding="utf-8")
        (nested / "site.8tx").write_text("Detector D1", encoding="utf-8")
        out_dir = folder / "out"

        exit_code = main(
            [
                "extract",
                "--site-folder",
                str(folder),
                "--site-id",
                "397L",
                "--out-dir",
                str(out_dir),
            ]
        )

        output = json.loads((out_dir / "extracted_facts.partial.json").read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(output["site_id"], "397L")
        self.assertEqual(
            [Path(source["source_file"]).name for source in output["source_files"]],
            ["site.8tx", "site.txt"],
        )

    def test_extract_cli_requires_site_folder(self):
        with self.assertRaises(SystemExit):
            main(["extract", "--site-id", "397L", "--out-dir", str(_test_dir())])

    def test_extract_cli_rejects_inventory_argument(self):
        with self.assertRaises(SystemExit):
            main(
                [
                    "extract",
                    "--inventory",
                    "site_inventory.partial.json",
                    "--site-id",
                    "397L",
                    "--out-dir",
                    str(_test_dir()),
                ]
            )


def _test_dir() -> Path:
    path = Path("outputs") / f"test_extraction_{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    return path


class _ContextManager:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, *_args):
        return False


class _Entity:
    def __init__(self, entity_type, layer, **attributes):
        self._entity_type = entity_type
        self.dxf = types.SimpleNamespace(layer=layer, **attributes)

    def dxftype(self):
        return self._entity_type


if __name__ == "__main__":
    unittest.main()
