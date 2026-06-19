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
from mapemgen.ingestion.cad import _configure_odafc_path, extract_dwg_facts, extract_dxf_facts
from mapemgen.ingestion.docx_tables import extract_docx_facts
from mapemgen.ingestion.facts import extract_site_folder_facts
from mapemgen.ingestion.gis import extract_gis_facts
from mapemgen.ingestion.mova import extract_mova_facts
from mapemgen.ingestion.pdf_cv import extract_pdf_image_facts
from mapemgen.ingestion.pdf_tables import extract_pdf_facts
from mapemgen.ingestion.ram_text import extract_ram_text_facts
from mapemgen.ingestion.zip_packages import extract_zip_facts
from mapemgen.training.pdf_yolo import build_weak_pdf_yolo_dataset, train_weak_pdf_yolo


class ExtractionTest(unittest.TestCase):
    def test_ram_text_extracts_mapem_relevant_keyword_lines(self):
        path = _test_dir() / "1003_RAMData.8tx"
        path.write_text(
            "Phase A override\nStage 2 demand\nIntergreen A B 5\nDetector D12\nI/O allocation 7\n",
            encoding="utf-8",
        )

        facts = extract_ram_text_facts(path)

        fact_names = {fact["fact_name"] for fact in facts}
        self.assertIn("phase_label_from_ram_8tx", fact_names)
        self.assertIn("stage_phase_relationship_from_ram_8tx", fact_names)
        self.assertIn("movement_phase_mapping_from_ram_8tx", fact_names)
        self.assertTrue(all("fact_type" not in fact and "value" not in fact for fact in facts))
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
            by_type.setdefault(fact["fact_name"], []).append(fact["payload"]["value"])
        archive_members = by_type["archive_member"]
        self.assertIn({"member": "T1003 Root.dwg", "status": "available", "cad_member_role": "root_dwg", "parseable": True}, archive_members)
        self.assertIn(
            {
                "member": "xref/OS-TOPO.dwg",
                "status": "available",
                "cad_member_role": "xref_dwg",
                "drawing_role": "topographic",
                "parseable": True,
            },
            archive_members,
        )
        self.assertFalse((path.parent / "xref").exists())

    def test_zip_parser_recursively_extracts_supported_members(self):
        path = _test_dir() / "site.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("notes/controller.8tx", "Phase A")

        facts = extract_zip_facts(path)

        phase = next(fact for fact in facts if fact["fact_name"] == "phase_label_from_ram_8tx")
        self.assertEqual(phase["payload"]["value"], "Phase A")
        self.assertEqual(phase["evidence_location"], "archive member notes/controller.8tx -> line 1")

    def test_zip_parser_recursively_extracts_nested_zip_members(self):
        nested_path = _test_dir() / "nested.zip"
        with zipfile.ZipFile(nested_path, "w") as archive:
            archive.writestr("ram/site.8tx", "Phase A")
        path = _test_dir() / "site.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.write(nested_path, "packages/nested.zip")

        facts = extract_zip_facts(path)

        phase = next(fact for fact in facts if fact["fact_name"] == "phase_label_from_ram_8tx")
        self.assertEqual(
            phase["evidence_location"],
            "archive member packages/nested.zip -> archive member ram/site.8tx -> line 1",
        )

    def test_zip_parser_rejects_path_traversal_member(self):
        path = _test_dir() / "site.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("../outside.txt", "Detector D12")

        facts = extract_zip_facts(path)

        rejected = next(fact for fact in facts if fact["fact_name"] == "archive_member")
        self.assertEqual(rejected["payload"]["value"]["member"], "../outside.txt")
        self.assertEqual(rejected["payload"]["value"]["status"], "rejected")

    def test_mova_parser_skips_without_mova_tools(self):
        path = _test_dir() / "site.mova"
        path.write_bytes(b"\x00binary mova dataset\xff")

        with patch.dict(os.environ, {}, clear=True):
            facts = extract_mova_facts(path)

        self.assertEqual(facts, [])

    def test_mova_parser_records_official_export_requirement(self):
        folder = _test_dir()
        path = folder / "site.mova"
        executable = folder / "MOVATools.exe"
        path.write_bytes(b"\x00binary mova dataset\xff")
        executable.write_bytes(b"synthetic executable placeholder")

        with patch.dict(os.environ, {"MOVA_TOOLS_PATH": str(executable)}):
            facts = extract_mova_facts(path)

        self.assertEqual(facts, [])

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

        self.assertTrue(
            any(
                fact["fact_name"] == "road_direction_from_ordnance_survey"
                and fact["payload"]["value"] == "London Road"
                and fact["evidence_location"] == "feature 1 properties.name"
                and fact["confidence"] == 0.85
                for fact in facts
            )
        )
        self.assertTrue(any(fact["fact_name"] == "coordinate_bounds" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "junction_centre_from_ordnance_survey" for fact in facts))

    def test_osm_parser_extracts_way_name_and_bounds(self):
        path = _test_dir() / "roads.osm"
        path.write_text(
            '<osm><node id="1" lat="51.0" lon="-1.0"/><node id="2" lat="51.2" lon="-1.2"/>'
            '<way id="3"><nd ref="1"/><nd ref="2"/><tag k="name" v="Oak Street"/></way></osm>',
            encoding="utf-8",
        )

        facts = extract_gis_facts(path)

        self.assertTrue(any(fact["fact_name"] == "road_direction_from_open_street_map" and fact["payload"]["value"] == "Oak Street" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "coordinate_bounds" for fact in facts))

    def test_dxf_parser_requires_ezdxf(self):
        with patch.dict(sys.modules, {"ezdxf": None}):
            with self.assertRaisesRegex(RuntimeError, "ezdxf"):
                extract_dxf_facts(_test_dir() / "site.dxf")

    def test_dwg_parser_requires_oda_file_converter(self):
        with self.assertRaisesRegex(RuntimeError, "ODA File Converter"):
            extract_dwg_facts(_test_dir() / "site.dwg")

    def test_dwg_parser_invokes_oda_file_converter(self):
        calls = []
        document = types.SimpleNamespace(modelspace=lambda: [])
        def execute(arguments):
            calls.append(("execute", arguments[0], Path(arguments[1]).name, Path(arguments[2]).name, arguments[3], arguments[4]))

        fake_odafc = types.SimpleNamespace(
            is_installed=lambda: True,
            _odafc_arguments=lambda filename, in_folder, out_folder, output_format, version, audit: [
                filename,
                in_folder,
                out_folder,
                output_format,
                version,
                audit,
            ],
            _execute_odafc=execute,
        )
        fake_addons = types.ModuleType("ezdxf.addons")
        fake_addons.odafc = fake_odafc
        fake_ezdxf = types.ModuleType("ezdxf")
        fake_ezdxf.addons = fake_addons
        fake_ezdxf.readfile = lambda path: calls.append(("readfile", Path(path).suffix)) or document
        fake_ezdxf.DXFStructureError = ValueError

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf, "ezdxf.addons": fake_addons}):
            facts = extract_dwg_facts("site.dwg")

        self.assertEqual(calls[-1], ("readfile", ".dxf"))
        self.assertEqual(calls[0][0], "execute")
        self.assertEqual(calls[0][1], "site.dwg")
        self.assertEqual(facts, [])

    def test_dwg_parser_uses_odafc_path_environment_variable(self):
        calls = []
        configured = {}
        document = types.SimpleNamespace(modelspace=lambda: [])
        def execute(arguments):
            calls.append(("execute", arguments[0], Path(arguments[2]).name))

        fake_odafc = types.SimpleNamespace(
            is_installed=lambda: configured.get(("odafc-addon", "win_exec_path")) == r"E:\ODA\ODAFileConverter.exe",
            _odafc_arguments=lambda filename, in_folder, out_folder, output_format, version, audit: [
                filename,
                in_folder,
                out_folder,
                output_format,
                version,
                audit,
            ],
            _execute_odafc=execute,
        )
        fake_addons = types.ModuleType("ezdxf.addons")
        fake_addons.odafc = fake_odafc
        fake_ezdxf = types.ModuleType("ezdxf")
        fake_ezdxf.addons = fake_addons
        fake_ezdxf.readfile = lambda path: calls.append(("readfile", Path(path).suffix)) or document
        fake_ezdxf.DXFStructureError = ValueError
        fake_ezdxf.options = types.SimpleNamespace(
            set=lambda section, key, value: configured.__setitem__((section, key), value)
        )

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf, "ezdxf.addons": fake_addons}):
            with patch.dict(os.environ, {"ODAFC_PATH": r"E:\ODA\ODAFileConverter.exe"}):
                extract_dwg_facts("site.dwg")

        self.assertEqual(configured[("odafc-addon", "win_exec_path")], r"E:\ODA\ODAFileConverter.exe")
        self.assertEqual(calls[-1], ("readfile", ".dxf"))

    def test_dwg_parser_uses_unix_odafc_path_environment_variable(self):
        configured = {}
        fake_ezdxf = types.ModuleType("ezdxf")
        fake_ezdxf.options = types.SimpleNamespace(
            set=lambda section, key, value: configured.__setitem__((section, key), value)
        )

        with patch.dict(os.environ, {"ODAFC_PATH": "/Applications/ODAFileConverter"}):
            with patch("mapemgen.ingestion.cad.os.name", "posix"):
                _configure_odafc_path(fake_ezdxf)

        self.assertEqual(configured[("odafc-addon", "unix_exec_path")], "/Applications/ODAFileConverter")

    def test_dwg_parser_recovers_converted_dxf_structure_error(self):
        calls = []

        class FakeDXFStructureError(Exception):
            pass

        document = types.SimpleNamespace(modelspace=lambda: [])
        def execute(arguments):
            calls.append(("execute", arguments[0], Path(arguments[2]).name))

        fake_odafc = types.SimpleNamespace(
            is_installed=lambda: True,
            _odafc_arguments=lambda filename, in_folder, out_folder, output_format, version, audit: [
                filename,
                in_folder,
                out_folder,
                output_format,
                version,
                audit,
            ],
            _execute_odafc=execute,
        )
        fake_recover = types.SimpleNamespace(
            readfile=lambda path: calls.append(("recover", Path(path).suffix)) or (document, object())
        )
        fake_addons = types.ModuleType("ezdxf.addons")
        fake_addons.odafc = fake_odafc
        fake_ezdxf = types.ModuleType("ezdxf")
        fake_ezdxf.addons = fake_addons
        fake_ezdxf.DXFStructureError = FakeDXFStructureError
        fake_ezdxf.readfile = lambda path: (_ for _ in ()).throw(FakeDXFStructureError("missing ENDSEC tag"))
        fake_ezdxf.recover = fake_recover

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf, "ezdxf.addons": fake_addons}):
            with patch.dict(os.environ, {}, clear=True):
                facts = extract_dwg_facts("site.dwg")

        self.assertEqual(calls[-1], ("recover", ".dxf"))
        self.assertEqual(calls[0][0], "execute")
        self.assertEqual(facts, [])

    def test_docx_parser_requires_python_docx(self):
        with patch.dict(sys.modules, {"docx": None}):
            with self.assertRaisesRegex(RuntimeError, "python-docx"):
                extract_docx_facts("site.docx")

    def test_pdf_parser_requires_pdfplumber(self):
        with patch.dict(sys.modules, {"pdfplumber": None}):
            with self.assertRaisesRegex(RuntimeError, "pdfplumber"):
                extract_pdf_facts("site.pdf")

    def test_pdf_image_recognition_requires_cv_packages(self):
        with patch.dict(sys.modules, {"fitz": None}):
            with self.assertRaisesRegex(RuntimeError, "PDF image recognition requires"):
                extract_pdf_image_facts("site.pdf", page_numbers=[1])

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
            facts = extract_docx_facts("1003_UTCForm_May24.docx")

        self.assertTrue(any(fact["fact_name"] == "phase_label_from_utc_form" and fact["evidence_location"] == "paragraph 1" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "stage_phase_relationship_from_utc_form" and fact["evidence_location"] == "table 1 row 1" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "site_description" and fact["payload"]["value"] == "London Rd / Morrisons" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "scn" and fact["payload"]["value"] == "J04121" for fact in facts))
        self.assertFalse(any(fact["fact_name"] == "ip_address" for fact in facts))

    def test_pdf_parser_defers_image_page_and_preserves_table_location(self):
        page = types.SimpleNamespace(
            extract_text=lambda: "",
            extract_tables=lambda: [[["Phase", "A"]]],
            width=595,
            height=842,
            images=[],
        )
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _ContextManager(types.SimpleNamespace(pages=[page])))

        with patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            facts = extract_pdf_facts("site.pdf")

        self.assertFalse(any(fact["fact_name"] == "needs_future_recognition" for fact in facts))
        self.assertFalse(any(fact["fact_name"] == "pdf_image_page_candidate" for fact in facts))
        self.assertFalse(any(fact["fact_name"] == "pdf_table_row" for fact in facts))

    def test_pdf_parser_runs_ocr_and_cv_for_image_page(self):
        page = types.SimpleNamespace(
            extract_text=lambda: "Native text still exists",
            extract_tables=lambda: [],
            width=595,
            height=842,
            images=[{"x0": 10, "top": 20, "x1": 500, "bottom": 700, "width": 490, "height": 680}],
        )
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _ContextManager(types.SimpleNamespace(pages=[page])))
        fake_pdf_page = types.SimpleNamespace(get_pixmap=lambda matrix, alpha: types.SimpleNamespace(tobytes=lambda _format: b"png"))
        fake_fitz_document = _ContextManager([fake_pdf_page])
        fake_fitz = types.SimpleNamespace(open=lambda _path: fake_fitz_document, Matrix=lambda x, y: (x, y))
        fake_pytesseract = types.SimpleNamespace(image_to_string=lambda _image, config=None: "Phase A\nDetector D12")
        fake_numpy = types.SimpleNamespace(frombuffer=lambda data, dtype: data, uint8="uint8")
        fake_cv2 = types.SimpleNamespace(
            IMREAD_COLOR=1,
            COLOR_BGR2GRAY=2,
            THRESH_BINARY=3,
            THRESH_OTSU=4,
            MORPH_RECT=5,
            imdecode=lambda data, flags: "image",
            cvtColor=lambda image, code: "gray",
            threshold=lambda gray, thresh, maxval, flags: (0, "thresholded"),
            getStructuringElement=lambda shape, ksize: "kernel",
            morphologyEx=lambda image, op, kernel: "morphed",
            MORPH_CLOSE=6,
            Canny=lambda image, low, high, apertureSize=3: "edges",
            HoughLinesP=lambda edges, rho, theta, threshold, minLineLength, maxLineGap: [[[1, 2, 30, 2]]],
        )

        with patch.dict(
            sys.modules,
            {
                "pdfplumber": fake_pdfplumber,
                "fitz": fake_fitz,
                "pytesseract": fake_pytesseract,
                "numpy": fake_numpy,
                "cv2": fake_cv2,
            },
        ):
            facts = extract_pdf_facts("site.pdf")

        self.assertFalse(any(fact["fact_name"] == "pdf_ocr_text_candidate" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "phase_candidate_from_pdf_ocr" for fact in facts))
        self.assertFalse(any(fact["fact_name"] == "pdf_cv_line_candidate" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "lane_line_candidate_from_pdf_cv" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "road_marking_candidate_from_pdf_cv" for fact in facts))

    def test_pdf_parser_extracts_vector_drawing_candidates(self):
        page = types.SimpleNamespace(
            extract_text=lambda: "Native text still exists",
            extract_tables=lambda: [],
            width=595,
            height=842,
            images=[],
            lines=[{"x0": 10, "top": 20, "x1": 200, "bottom": 20, "linewidth": 0.5}],
            curves=[{"x0": 30, "top": 40, "x1": 70, "bottom": 80, "linewidth": 0.25}],
            rects=[{"x0": 100, "top": 110, "x1": 160, "bottom": 170, "width": 60, "height": 60}],
        )
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _ContextManager(types.SimpleNamespace(pages=[page])))

        with patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            facts = extract_pdf_facts("site.pdf")

        self.assertFalse(any(fact["fact_name"] == "pdf_vector_page_candidate" for fact in facts))
        self.assertFalse(any(fact["fact_name"] == "pdf_vector_line_candidate" for fact in facts))
        self.assertFalse(any(fact["fact_name"] == "pdf_vector_curve_candidate" for fact in facts))
        self.assertFalse(any(fact["fact_name"] == "pdf_vector_rect_candidate" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "lane_line_candidate_from_pdf_vector" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "road_marking_candidate_from_pdf_vector" for fact in facts))

    def test_pdf_parser_skips_unavailable_ocr_but_keeps_native_text_and_tables(self):
        page = types.SimpleNamespace(
            extract_text=lambda: "USE OF PHASES\nA Selby Rd Eastbound ahead T O 7",
            extract_tables=lambda: [
                [
                    ["USE OF PHASES", None, "PHASE TYPE"],
                    ["A", "Selby Rd Eastbound ahead", "T", "O", "7"],
                ]
            ],
            width=595,
            height=842,
            images=[{"x0": 1, "top": 1, "x1": 2, "bottom": 2}],
            lines=[],
            curves=[],
            rects=[],
        )
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _ContextManager(types.SimpleNamespace(pages=[page])))

        with patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            facts = extract_pdf_facts("573L v1 P 05_09_07.pdf")

        self.assertTrue(any(fact["fact_name"] == "phase_label_from_controller_config" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "movement_phase_mapping_from_controller_config" for fact in facts))

    def test_pdf_use_of_phases_table_extracts_real_phase_movements_and_skips_dummy_movement(self):
        page = types.SimpleNamespace(
            extract_text=lambda: "USE OF PHASES",
            extract_tables=lambda: [
                [
                    ["USE OF PHASES\nLOCATION", None, "PHASE\nTYPE\nNOTE 3"],
                    ["A", "Selby Rd Eastbound ahead", "T", "O", "7"],
                    ["R", "Stage 2 Dummy G Bit reply", "D", "O", "2"],
                ]
            ],
            images=[],
            lines=[],
            curves=[],
            rects=[],
        )
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _ContextManager(types.SimpleNamespace(pages=[page])))

        with patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            facts = extract_pdf_facts("573L v1 P 05_09_07.pdf")

        labels = [fact["payload"]["value"] for fact in facts if fact["fact_name"] == "phase_label_from_controller_config"]
        movements = [fact["payload"]["value"] for fact in facts if fact["fact_name"] == "movement_phase_mapping_from_controller_config"]
        self.assertIn(
            {
                "phase_ref": "phase_A",
                "phase_label": "A",
                "phase_type": "T",
                "movement_text": "Selby Rd Eastbound ahead",
            },
            labels,
        )
        self.assertTrue(any(item["phase_label"] == "A" and item["maneuver"] == "ahead" for item in movements))
        self.assertFalse(any(item["phase_label"] == "R" for item in movements))

    def test_pdf_parser_does_not_promote_page_borders_to_semantic_candidates(self):
        page = types.SimpleNamespace(
            extract_text=lambda: "Native text still exists",
            extract_tables=lambda: [],
            width=600,
            height=800,
            images=[],
            lines=[{"x0": 0, "top": 0, "x1": 600, "bottom": 0, "linewidth": 0.5}],
            curves=[{"x0": 0, "top": 0, "x1": 600, "bottom": 20, "linewidth": 1.0}],
            rects=[{"x0": 0, "top": 0, "x1": 600, "bottom": 800, "width": 600, "height": 800}],
        )
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _ContextManager(types.SimpleNamespace(pages=[page])))

        with patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            facts = extract_pdf_facts("site.pdf")

        self.assertFalse(any(fact["fact_name"] == "pdf_vector_line_candidate" for fact in facts))
        self.assertFalse(any(fact["fact_name"] == "pdf_vector_curve_candidate" for fact in facts))
        self.assertFalse(any(fact["fact_name"] == "pdf_vector_rect_candidate" for fact in facts))
        self.assertFalse(any(fact["fact_name"].endswith("_candidate_from_pdf_vector") for fact in facts))

    def test_dxf_parser_extracts_geometry_labels_and_bounds(self):
        entities = [
            _Entity("LINE", "LANE_MAIN", start=(0, 0), end=(10, 5)),
            _Entity("TEXT", "LABELS", text="London Road inbound ahead", insert=(2, 3), rotation=90),
            _Entity("INSERT", "SIGNALS", name="RIGHT_ARROW", insert=(4, 5), rotation=45),
        ]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            facts = extract_dxf_facts("site.dxf")

        self.assertTrue(any(fact["fact_name"] == "lane_geometry_candidate_from_cad" for fact in facts))
        text_label = next(fact for fact in facts if fact["fact_name"] == "road_marking_or_sign_note_from_cad")
        self.assertEqual(text_label["payload"]["value"]["text"], "London Road inbound ahead")
        self.assertEqual(text_label["payload"]["value"]["geometry"], {"x": 2.0, "y": 3.0})
        movement_label = next(fact for fact in facts if fact["fact_name"] == "movement_direction_candidate_from_cad")
        self.assertEqual(movement_label["payload"]["value"]["movement_ref"], "movement_london_road_inbound_ahead")
        block = next(fact for fact in facts if fact["fact_name"] == "cad_block_reference")
        self.assertEqual(block["payload"]["value"]["name"], "RIGHT_ARROW")
        self.assertEqual(block["payload"]["value"]["geometry"], {"x": 4.0, "y": 5.0})
        self.assertTrue(any(fact["fact_name"] == "movement_direction_candidate_from_cad" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "coordinate_bounds" for fact in facts))

    def test_dxf_parser_applies_cad_symbol_semantic_rules(self):
        entities = [
            _Entity("INSERT", "SIGNALS", name="HD001S", insert=(1, 1)),
            _Entity("INSERT", "SIGNALS", name="HD004P", insert=(1, 2)),
            _Entity("INSERT", "POLES", name="pole", insert=(2, 2)),
            _Entity("INSERT", "TACTILE", name="tactpblk", insert=(3, 3)),
            _Entity("TEXT", "MARKINGS", text="KEEP CLEAR", insert=(4, 4)),
        ]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            facts = extract_dxf_facts("site.dxf")

        by_name = {fact["fact_name"]: fact["payload"]["value"] for fact in facts}
        signal_candidates = [
            fact["payload"]["value"]
            for fact in facts
            if fact["fact_name"] == "cad_block_reference" and fact["payload"]["value"].get("semantic_type") == "signal_head"
        ]
        self.assertIn(
            {"name": "HD001S", "geometry": {"x": 1.0, "y": 1.0}, "semantic_type": "signal_head", "source_block_name": "HD001S"},
            signal_candidates,
        )
        self.assertTrue(any(fact["fact_name"] == "lane_facility_geometry_candidate_from_cad" and fact["payload"]["value"]["semantic_type"] == "pole" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "lane_facility_geometry_candidate_from_cad" and fact["payload"]["value"]["semantic_type"] == "tactile_paving" for fact in facts))
        self.assertEqual(by_name["lane_use_label_from_cad"]["label"], "keep_clear")
        arrow_candidates = [fact["payload"]["value"] for fact in facts if fact["fact_name"] == "movement_direction_candidate_from_cad"]
        self.assertIn(
            {
                "name": "HD004P",
                "geometry": {"x": 1.0, "y": 2.0},
                "semantic_type": "signal_arrow",
                "source_block_name": "HD004P",
                "arrow_direction_candidate": "left",
                "requires_context_match": True,
            },
            arrow_candidates,
        )

    def test_dxf_parser_applies_leeds_cad_symbol_variants(self):
        entities = [
            _Entity("INSERT", "UTC SIGNALS", name="XREF UTC_716709_AJB_1b$0$HD001P", insert=(1, 1)),
            _Entity("INSERT", "UTC_Signals", name="Signal-Symbol-001P", insert=(2, 2)),
            _Entity("INSERT", "UTC PC POLES", name="WBPOLE-sym", insert=(3, 3)),
            _Entity("INSERT", "Tactpave", name="XREF UTC_716709_AJB_1b$0$TACTPBLK", insert=(4, 4)),
            _Entity("INSERT", "PRO-MARKINGS", name="Right turn arrow", insert=(5, 5)),
            _Entity("INSERT", "PRO-MARKINGS", name="Left-Arrow-4m(1038l4)", insert=(6, 6)),
        ]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            facts = extract_dxf_facts("site.dxf")

        signal_candidates = [
            fact["payload"]["value"]
            for fact in facts
            if fact["fact_name"] == "cad_block_reference" and fact["payload"]["value"].get("semantic_type") == "signal_head"
        ]
        pole_candidates = [fact["payload"]["value"] for fact in facts if fact["fact_name"] == "lane_facility_geometry_candidate_from_cad" and fact["payload"]["value"].get("semantic_type") == "pole"]
        tactile_candidates = [fact["payload"]["value"] for fact in facts if fact["fact_name"] == "lane_facility_geometry_candidate_from_cad" and fact["payload"]["value"].get("semantic_type") == "tactile_paving"]
        arrow_candidates = [fact["payload"]["value"] for fact in facts if fact["fact_name"] == "movement_direction_candidate_from_cad"]
        self.assertEqual(len(signal_candidates), 2)
        self.assertEqual(len(pole_candidates), 1)
        self.assertEqual(len(tactile_candidates), 1)
        self.assertTrue(any(candidate.get("arrow_direction_candidate") == "right" for candidate in arrow_candidates))
        self.assertTrue(any(candidate.get("arrow_direction_candidate") == "left" for candidate in arrow_candidates))

    def test_dxf_parser_applies_cad_layer_semantic_rules(self):
        entities = [
            _Entity("LINE", "OptionG+UTC cdp$0$-RoadMarkings", start=(0, 0), end=(10, 0)),
            _Entity("LINE", "OptionG+UTC cdp$0$stoplines", start=(0, 1), end=(10, 1)),
            _Entity("LINE", "UTC MOVA LOOPS", start=(0, 2), end=(10, 2)),
            _Entity("LINE", "UTC SIGNALS", start=(0, 3), end=(10, 3)),
            _Entity("LINE", "Tactpave", start=(0, 4), end=(10, 4)),
            _Entity("LINE", "KERB", start=(0, 5), end=(10, 5)),
        ]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            facts = extract_dxf_facts("site.dxf")

        by_name = {fact["fact_name"]: fact["payload"]["value"] for fact in facts if "modelspace entity" in fact["evidence_location"]}
        self.assertEqual(by_name["road_marking_or_sign_note_from_cad"]["semantic_type"], "road_marking")
        self.assertEqual(by_name["stop_line_from_cad"]["semantic_type"], "stop_line")
        self.assertTrue(any(fact["fact_name"] == "lane_facility_geometry_candidate_from_cad" and fact["payload"]["value"]["semantic_type"] == "detector_loop" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "lane_facility_geometry_candidate_from_cad" and fact["payload"]["value"]["semantic_type"] == "signal_geometry" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "lane_facility_geometry_candidate_from_cad" and fact["payload"]["value"]["semantic_type"] == "crossing_or_tactile" for fact in facts))
        self.assertEqual(by_name["approach_arm_geometry_from_cad"]["semantic_type"], "road_context_geometry")
        self.assertEqual(by_name["road_marking_or_sign_note_from_cad"]["layer"], "OptionG+UTC cdp$0$-RoadMarkings")

    def test_dxf_parser_filters_empty_cad_text_labels(self):
        entities = [
            _Entity("TEXT", "LABELS", text=""),
            _Entity("TEXT", "LABELS", text="   "),
            _Entity("MTEXT", "LABELS", text="Phase A"),
        ]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            facts = extract_dxf_facts("site.dxf")

        labels = [fact["payload"]["value"] for fact in facts if fact["fact_name"] == "road_marking_or_sign_note_from_cad"]
        self.assertEqual([label["text"] for label in labels], ["Phase A"])

    def test_dxf_parser_does_not_promote_utility_layers_to_lane_candidates(self):
        entities = [
            _Entity("LINE", "DUCTS", start=(0, 0), end=(1, 0)),
            _Entity("LINE", "LOOPS", start=(0, 0), end=(1, 1)),
            _Entity("LINE", "LANE_MAIN", start=(0, 5), end=(10, 5)),
        ]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            facts = extract_dxf_facts("site.dxf")

        layer_by_name = {fact["evidence_location"]: fact["fact_name"] for fact in facts if "modelspace entity" in fact["evidence_location"]}
        self.assertNotIn("modelspace entity 1 layer DUCTS", layer_by_name)
        self.assertEqual(layer_by_name["modelspace entity 2 layer LOOPS"], "lane_facility_geometry_candidate_from_cad")
        self.assertEqual(layer_by_name["modelspace entity 3 layer LANE_MAIN"], "lane_geometry_candidate_from_cad")

    def test_dxf_parser_promotes_long_generic_cad_lines_to_lane_candidates(self):
        entities = [
            _Entity("LINE", "KTS_LINES", start=(0, 0), end=(40, 0)),
            _Entity("LINE", "LINES", start=(0, 1), end=(2, 1)),
            _Entity("LINE", "du-UTMCDUCT-F1", start=(0, 2), end=(80, 2)),
        ]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            facts = extract_dxf_facts("site.dxf")

        lane_candidates = [fact for fact in facts if fact["fact_name"] == "lane_geometry_candidate_from_cad"]
        self.assertEqual(len(lane_candidates), 1)
        payload = lane_candidates[0]["payload"]["value"]
        self.assertEqual(payload["layer"], "KTS_LINES")
        self.assertEqual(payload["semantic_type"], "lane_centreline_candidate")
        self.assertEqual(payload["recognition_basis"], "cad_layer_geometry_heuristic")
        self.assertTrue(payload["requires_context_match"])
        self.assertLess(lane_candidates[0]["confidence"], 0.7)

    def test_dxf_parser_keeps_broad_road_layers_out_of_lane_candidates(self):
        entities = [
            _Entity("LINE", "GENLINE", start=(0, 0), end=(80, 0)),
            _Entity("LINE", "ROAD", start=(0, 1), end=(80, 1)),
            _Entity("LINE", "GENPECK", start=(0, 2), end=(80, 2)),
        ]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            facts = extract_dxf_facts("site.dxf")

        self.assertFalse(any(fact["fact_name"] == "lane_geometry_candidate_from_cad" for fact in facts))

    def test_dxf_parser_keeps_non_lane_line_layers_out_of_lane_candidates(self):
        entities = [
            _Entity("LINE", "Construction Lines", start=(0, 0), end=(80, 0)),
            _Entity("LINE", "T-ROAD_MARKINGS_YELLOW_LINES", start=(0, 1), end=(80, 1)),
            _Entity("LINE", "zz-existing-LINES-OFF", start=(0, 2), end=(80, 2)),
        ]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            facts = extract_dxf_facts("site.dxf")

        self.assertFalse(any(fact["fact_name"] == "lane_geometry_candidate_from_cad" for fact in facts))

    def test_dxf_parser_extracts_classic_polyline_vertices(self):
        polyline = _Entity("POLYLINE", "LANE_MAIN")
        polyline.vertices = [
            types.SimpleNamespace(dxf=types.SimpleNamespace(location=(0, 0))),
            types.SimpleNamespace(dxf=types.SimpleNamespace(location=(10, 5))),
        ]
        fake_ezdxf = types.SimpleNamespace(
            readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: [polyline])
        )

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            facts = extract_dxf_facts("site.dxf")

        self.assertTrue(any(fact["fact_name"] == "lane_geometry_candidate_from_cad" for fact in facts))
        self.assertTrue(any(fact["fact_name"] == "coordinate_bounds" for fact in facts))

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

    def test_coordinator_prefixes_fact_location_with_source_file(self):
        folder = _test_dir()
        text_path = folder / "nested" / "site.8tx"
        text_path.parent.mkdir()
        text_path.write_text("Phase A", encoding="utf-8")

        output = extract_site_folder_facts(folder, site_id="1003")

        fact = output["source_files"][0]["extracted_facts"][0]
        self.assertEqual(fact["evidence_location"], f"{text_path.as_posix()} -> line 1")

    def test_coordinator_preserves_archive_member_provenance_after_source_file_prefix(self):
        folder = _test_dir()
        zip_path = folder / "packages" / "site.zip"
        zip_path.parent.mkdir()
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("notes/controller.8tx", "Phase A")

        output = extract_site_folder_facts(folder, site_id="1003")

        facts = output["source_files"][0]["extracted_facts"]
        detector = next(fact for fact in facts if fact["fact_name"] == "phase_label_from_ram_8tx")
        self.assertEqual(
            detector["evidence_location"],
            f"{zip_path.as_posix()} -> archive member notes/controller.8tx -> line 1",
        )

    def test_coordinator_emits_ram_dictionary_fact_names(self):
        folder = _test_dir()
        path = folder / "1003_RAMData_Jan26.8tx"
        path.write_text("Phase A\nStage 2\n", encoding="utf-8")

        output = extract_site_folder_facts(folder, site_id="1003")

        facts = output["source_files"][0]["extracted_facts"]
        self.assertTrue(
            any(
                fact["fact_name"] == "phase_label_from_ram_8tx"
                for fact in facts
            )
        )
        self.assertTrue(
            any(
                fact["fact_name"] == "stage_phase_relationship_from_ram_8tx"
                for fact in facts
            )
        )

    def test_coordinator_emits_controller_config_pdf_dictionary_fact_names(self):
        folder = _test_dir()
        path = folder / "1003_2500Config_Mar24.pdf"
        path.write_bytes(b"%PDF synthetic")
        page = types.SimpleNamespace(
            extract_text=lambda: "Phase A\nStage 2",
            extract_tables=lambda: [],
        )
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _ContextManager(types.SimpleNamespace(pages=[page])))

        with patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            output = extract_site_folder_facts(folder, site_id="1003")

        facts = output["source_files"][0]["extracted_facts"]
        self.assertTrue(
            any(
                fact["fact_name"] == "phase_label_from_controller_config"
                for fact in facts
            )
        )

    def test_pdf_controller_config_extracts_phase_movement_mappings(self):
        path = _test_dir() / "1003_2500Config_Mar24.pdf"
        path.write_bytes(b"%PDF synthetic")
        page = types.SimpleNamespace(
            extract_text=lambda: "",
            extract_tables=lambda: [
                [
                    ["Phase Type and Conditions"],
                    ["A LONDON ROAD INBOUND AHEAD 0 - UK Traffic 0 0 - End of stage"],
                    ["B LONDON ROAD OUTBOUND AHEAD 0 - UK Traffic 0 0 - End of stage"],
                    ["C LONDON ROAD OUTBOUND RIGHT TURN 0 - UK Traffic 0 0 - End of stage"],
                ]
            ],
            images=[],
            lines=[],
            curves=[],
            rects=[],
        )
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _ContextManager(types.SimpleNamespace(pages=[page])))

        with patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            facts = extract_pdf_facts(path)

        mappings = [fact for fact in facts if fact["fact_name"] == "movement_phase_mapping_from_controller_config"]
        payloads = [fact["payload"]["value"] for fact in mappings]
        self.assertIn(
            {
                "phase_ref": "phase_A",
                "phase_label": "A",
                "movement_ref": "movement_london_road_inbound_ahead",
                "movement_text": "LONDON ROAD INBOUND AHEAD",
                "road_name": "London Road",
                "direction": "inbound",
                "maneuver": "ahead",
            },
            payloads,
        )
        self.assertIn(
            {
                "phase_ref": "phase_C",
                "phase_label": "C",
                "movement_ref": "movement_london_road_outbound_right_turn",
                "movement_text": "LONDON ROAD OUTBOUND RIGHT TURN",
                "road_name": "London Road",
                "direction": "outbound",
                "maneuver": "right_turn",
            },
            payloads,
        )

    def test_docx_utc_form_extracts_phase_link_movement_and_stage_mappings(self):
        fake_document = types.SimpleNamespace(
            paragraphs=[],
            tables=[
                _Table(
                    [
                        ["Link SCN", "Link Description"],
                        ["N04211A", "1003 A4 London Rd/ Cleveland Place: London Rd WB Ahead"],
                        ["N04211C", "1003 A4 London Rd/ Cleveland Place: London Rd EB Rt"],
                    ]
                ),
                _Table([["unused"]]),
                _Table([["unused"]]),
                _Table([["unused"]]),
                _Table([["unused"]]),
                _Table(
                    [
                        ["SCOOT Stage", "Controller Stage Change", "Interstage + Stage Min", "SCOOT Stage: Minimum Stage Length"],
                        ["1", "5 to 1", "8 + 7 = 15", "15"],
                    ]
                ),
                _Table(
                    [
                        [
                            "Controller Phase Letter",
                            "SCOOT Link Letter",
                            "Value In Spec (Time to Phase Gaining Green)",
                            "SLAG: SCOOT Value (Subtract 7)",
                            "ELAG: SCOOT Value (=Phase Delay)",
                        ],
                        ["A", "A", "5", "-2", "0"],
                        ["C", "C", "7", "0", "4"],
                    ]
                ),
                _Table(
                    [
                        ["Link Letter", "Link Type", "Upstream Node", "UNTL", "MDSL", "Junction SCN", "UTC Green Stage No’s"],
                        ["A", "N", "N04116", "I", "NA", "J04211", "1"],
                        ["C", "E", "NA", "NA", "NA", "J04211", "2,3"],
                    ]
                ),
            ],
        )
        fake_docx = types.SimpleNamespace(Document=lambda _path: fake_document)

        with patch.dict(sys.modules, {"docx": fake_docx}):
            facts = extract_docx_facts("1003_UTCForm_May24.docx")

        by_name = {}
        for fact in facts:
            by_name.setdefault(fact["fact_name"], []).append(fact["payload"]["value"])
        self.assertIn(
            {
                "scoot_link_ref": "A",
                "scn": "N04211A",
                "movement_ref": "movement_london_rd_wb_ahead",
                "movement_text": "London Rd WB Ahead",
                "road_name": "London Rd",
                "direction": "WB",
                "maneuver": "ahead",
            },
            by_name["movement_direction_candidate_from_utc_form"],
        )
        self.assertIn(
            {
                "phase_ref": "phase_A",
                "phase_label": "A",
                "scoot_link_ref": "A",
                "movement_ref": "movement_london_rd_wb_ahead",
                "value_in_spec": 5,
                "slag": -2,
                "elag": 0,
            },
            by_name["movement_phase_mapping_from_utc_form"],
        )
        self.assertIn(
            {
                "scoot_link_ref": "C",
                "stage_refs": ["stage_2", "stage_3"],
                "stage_numbers": [2, 3],
                "junction_scn": "J04211",
            },
            by_name["stage_phase_relationship_from_utc_form"],
        )

    def test_coordinator_emits_cad_dictionary_fact_names(self):
        folder = _test_dir()
        path = folder / "site.dxf"
        path.write_text("synthetic", encoding="utf-8")
        entities = [_Entity("LINE", "LANE_MAIN", start=(0, 0), end=(10, 5))]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            output = extract_site_folder_facts(folder, site_id="1003")

        facts = output["source_files"][0]["extracted_facts"]
        self.assertTrue(
            any(
                fact["fact_name"] == "lane_geometry_candidate_from_cad"
                for fact in facts
            )
        )

    def test_coordinator_filters_non_site_dwg_sources(self):
        folder = _test_dir()
        site_path = folder / "1003_Main_Overlay.dxf"
        other_path = folder / "1018_Other_Overlay.dxf"
        site_path.write_text("synthetic", encoding="utf-8")
        other_path.write_text("synthetic", encoding="utf-8")
        entities = [_Entity("LINE", "LANE_MAIN", start=(0, 0), end=(10, 5))]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            output = extract_site_folder_facts(folder, site_id="1003")

        by_name = {Path(source["source_file"]).name: source for source in output["source_files"]}
        self.assertEqual(by_name["1003_Main_Overlay.dxf"]["status"], "parsed")
        self.assertEqual(by_name["1018_Other_Overlay.dxf"]["status"], "skipped")
        self.assertEqual(by_name["1018_Other_Overlay.dxf"]["skip_reason"], "non_site_cad_source")
        self.assertEqual(by_name["1018_Other_Overlay.dxf"]["extracted_facts"], [])

    def test_coordinator_accepts_site_id_embedded_after_project_number_in_cad_name(self):
        folder = _test_dir()
        site_path = folder / "733647-UTC-378L-01a 25-06-24.dxf"
        site_path.write_text("synthetic", encoding="utf-8")
        entities = [_Entity("LINE", "LANE_MAIN", start=(0, 0), end=(10, 5))]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            output = extract_site_folder_facts(folder, site_id="378L")

        source = output["source_files"][0]
        self.assertEqual(source["status"], "parsed")
        self.assertTrue(any(fact["fact_name"] == "lane_geometry_candidate_from_cad" for fact in source["extracted_facts"]))

    def test_coordinator_limits_topographic_cad_to_metadata(self):
        folder = _test_dir()
        topo_path = folder / "OS-TOPO.dxf"
        topo_path.write_text("synthetic", encoding="utf-8")
        entities = [
            _Entity("LINE", "LANE_MAIN", start=(0, 0), end=(10, 5)),
            _Entity("TEXT", "LABELS", text="Phase A"),
        ]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            output = extract_site_folder_facts(folder, site_id="1003")

        facts = output["source_files"][0]["extracted_facts"]
        self.assertEqual({fact["fact_name"] for fact in facts}, {"coordinate_bounds"})

    def test_coordinator_prefers_standalone_cad_over_duplicate_zip_member_cad(self):
        folder = _test_dir()
        standalone = folder / "1003_Main.dxf"
        package = folder / "1003_package.zip"
        standalone.write_text("synthetic", encoding="utf-8")
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("1003_Main.dxf", "synthetic")
        entities = [_Entity("LINE", "LANE_MAIN", start=(0, 0), end=(10, 5))]
        fake_ezdxf = types.SimpleNamespace(readfile=lambda _path: types.SimpleNamespace(modelspace=lambda: entities))

        with patch.dict(sys.modules, {"ezdxf": fake_ezdxf}):
            output = extract_site_folder_facts(folder, site_id="1003")

        by_name = {Path(source["source_file"]).name: source for source in output["source_files"]}
        standalone_facts = by_name["1003_Main.dxf"]["extracted_facts"]
        zip_facts = by_name["1003_package.zip"]["extracted_facts"]
        self.assertTrue(any(fact["fact_name"] == "lane_geometry_candidate_from_cad" for fact in standalone_facts))
        self.assertFalse(any(fact["fact_name"] == "lane_geometry_candidate_from_cad" for fact in zip_facts))
        self.assertTrue(
            any(
                fact["fact_name"] == "archive_member"
                and fact["payload"]["value"].get("reason") == "duplicate_standalone_cad"
                for fact in zip_facts
            )
        )

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

    def test_build_weak_pdf_yolo_dataset_exports_images_labels_and_data_yaml(self):
        folder = _test_dir()
        pdf_path = folder / "drawings" / "site.pdf"
        pdf_path.parent.mkdir()
        pdf_path.write_bytes(b"%PDF synthetic")
        out_dir = folder / "training_dataset"
        facts = [
            {
                "fact_name": "lane_line_candidate_from_pdf_vector",
                "payload": {"value": {"geometry": {"x0": 10, "top": 20, "x1": 90, "bottom": 24}}},
                "evidence_location": "page 1 line 1",
                "confidence": 0.45,
            },
            {
                "fact_name": "signal_head_symbol_candidate_from_pdf_vector",
                "payload": {"value": {"geometry": {"x0": 40, "top": 40, "x1": 50, "bottom": 50}}},
                "evidence_location": "page 1 curve 1",
                "confidence": 0.42,
            },
        ]
        fake_fitz = types.SimpleNamespace(
            open=lambda _path: _ContextManager(
                [
                    types.SimpleNamespace(
                        rect=types.SimpleNamespace(width=100, height=100),
                        get_pixmap=lambda matrix, alpha: types.SimpleNamespace(save=lambda path: Path(path).write_bytes(b"png")),
                    )
                ]
            ),
            Matrix=lambda _x, _y: object(),
        )

        with patch.dict(sys.modules, {"fitz": fake_fitz}):
            with patch("mapemgen.training.pdf_yolo.extract_pdf_facts", return_value=facts):
                manifest = build_weak_pdf_yolo_dataset(folder, out_dir)

        label_files = list((out_dir / "labels" / "train").glob("*.txt"))
        image_files = list((out_dir / "images" / "train").glob("*.png"))
        self.assertEqual(manifest["source_pdf_count"], 1)
        self.assertEqual(manifest["image_count"], 1)
        self.assertEqual(manifest["label_count"], 2)
        self.assertEqual(len(label_files), 1)
        self.assertEqual(len(image_files), 1)
        self.assertIn("1 ", label_files[0].read_text(encoding="utf-8"))
        self.assertIn("5 ", label_files[0].read_text(encoding="utf-8"))
        self.assertIn("lane_line", (out_dir / "data.yaml").read_text(encoding="utf-8"))

    def test_build_weak_pdf_yolo_dataset_refuses_non_empty_output_directory(self):
        folder = _test_dir()
        out_dir = folder / "training_dataset"
        out_dir.mkdir()
        (out_dir / "existing.txt").write_text("keep", encoding="utf-8")
        fake_fitz = types.SimpleNamespace()

        with patch.dict(sys.modules, {"fitz": fake_fitz}):
            with self.assertRaisesRegex(RuntimeError, "not empty"):
                build_weak_pdf_yolo_dataset(folder, out_dir)

    def test_train_weak_pdf_yolo_requires_ultralytics(self):
        with patch.dict(sys.modules, {"ultralytics": None}):
            with self.assertRaisesRegex(RuntimeError, "ultralytics"):
                train_weak_pdf_yolo("data.yaml", _test_dir())

    def test_train_pdf_detector_cli_can_export_dataset_only(self):
        out_dir = _test_dir()
        manifest = {"data_yaml": str(out_dir / "weak_pdf_yolo_dataset" / "data.yaml"), "image_count": 1}

        with patch("mapemgen.cli.build_weak_pdf_yolo_dataset", return_value=manifest) as build_dataset:
            with patch("mapemgen.cli.train_weak_pdf_yolo") as train_detector:
                exit_code = main(
                    [
                        "train-pdf-detector",
                        "--site-folder",
                        str(_test_dir()),
                        "--out-dir",
                        str(out_dir),
                        "--dataset-only",
                    ]
                )

        output = json.loads((out_dir / "pdf_training_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(output["image_count"], 1)
        build_dataset.assert_called_once()
        train_detector.assert_not_called()

    def test_train_pdf_detector_cli_requires_ultralytics_before_dataset_export(self):
        with patch("mapemgen.cli.require_yolo_training_package", side_effect=RuntimeError("ultralytics")):
            with patch("mapemgen.cli.build_weak_pdf_yolo_dataset") as build_dataset:
                with self.assertRaisesRegex(RuntimeError, "ultralytics"):
                    main(
                        [
                            "train-pdf-detector",
                            "--site-folder",
                            str(_test_dir()),
                            "--out-dir",
                            str(_test_dir()),
                        ]
                    )

        build_dataset.assert_not_called()


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


class _Table:
    def __init__(self, rows: list[list[str]]):
        self.rows = [
            types.SimpleNamespace(cells=[types.SimpleNamespace(text=cell) for cell in row])
            for row in rows
        ]


class _Entity:
    def __init__(self, entity_type, layer, **attributes):
        self._entity_type = entity_type
        self.dxf = types.SimpleNamespace(layer=layer, **attributes)

    def dxftype(self):
        return self._entity_type


if __name__ == "__main__":
    unittest.main()
