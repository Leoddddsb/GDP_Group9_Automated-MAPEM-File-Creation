import json
import unittest
import uuid
import zipfile
from pathlib import Path

from mapemgen.cli import main
from mapemgen.ingestion.inventory import build_site_inventory


class InventoryTest(unittest.TestCase):
    def test_build_site_inventory_records_files_and_parser_routing(self):
        site_folder = _workspace_test_dir() / "1003_LondonRdClevelandBridge"
        nested_folder = site_folder / "nested"
        nested_folder.mkdir(parents=True)
        (site_folder / "1003_RAMData_Jan26.8TX").write_text("ram", encoding="utf-8")
        (site_folder / "T1003 Cleveland Place.txt").write_text("notes", encoding="utf-8")
        (site_folder / "5062_MOVATools_Apr21.mova").write_bytes(b"mova")
        (site_folder / "Unknown.bin").write_bytes(b"\x00\x01")
        (nested_folder / "1003_UTCForm_Spec_Drawing.docx").write_bytes(b"docx")
        zip_path = site_folder / "T1003 Cleveland Place - Standard.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("root.dwg", "placeholder")

        inventory = build_site_inventory(
            site_folder,
            site_id="1003",
            site_name="London Rd Cleveland Bridge",
            dataset="DCIS/Bathnes",
        )

        self.assertEqual(inventory["site_id"], "1003")
        self.assertEqual(inventory["site_name"], "London Rd Cleveland Bridge")
        self.assertEqual(inventory["local_authority_or_dataset"], "DCIS/Bathnes")
        self.assertTrue(inventory["input_folder_path"].endswith("1003_LondonRdClevelandBridge"))
        self.assertEqual(inventory["inventory_summary"]["total_files"], 6)
        self.assertEqual(
            inventory["inventory_summary"]["file_type_counts"],
            {"8tx": 1, "bin": 1, "docx": 1, "mova": 1, "txt": 1, "zip": 1},
        )
        self.assertEqual(inventory["inventory_summary"]["readable_files"], 6)
        self.assertEqual(inventory["inventory_summary"]["unreadable_files"], 0)

        source_files = inventory["source_files"]
        self.assertEqual(
            [source["file_path"] for source in source_files],
            sorted(source["file_path"] for source in source_files),
        )
        by_name = {Path(source["file_path"]).name: source for source in source_files}

        self.assertEqual(by_name["1003_RAMData_Jan26.8TX"]["file_type"], "8tx")
        self.assertEqual(by_name["1003_RAMData_Jan26.8TX"]["parser_to_use"], "ram_text_parser")
        self.assertIn("possible RAM / override data", by_name["1003_RAMData_Jan26.8TX"]["filename_hints"])
        self.assertEqual(by_name["1003_RAMData_Jan26.8TX"]["readable_status"], "text_readable")

        self.assertEqual(by_name["T1003 Cleveland Place - Standard.zip"]["parser_to_use"], "zip_inventory_parser")
        self.assertEqual(by_name["T1003 Cleveland Place - Standard.zip"]["readable_status"], "archive_readable")
        self.assertIn("possible CAD package", by_name["T1003 Cleveland Place - Standard.zip"]["filename_hints"])

        self.assertEqual(by_name["5062_MOVATools_Apr21.mova"]["parser_to_use"], "mova_availability_recorder")
        self.assertEqual(by_name["5062_MOVATools_Apr21.mova"]["readable_status"], "available_not_directly_readable")
        self.assertIn("possible MOVA/control logic data", by_name["5062_MOVATools_Apr21.mova"]["filename_hints"])

        self.assertEqual(by_name["Unknown.bin"]["parser_to_use"], "manual_review")
        self.assertEqual(by_name["Unknown.bin"]["readable_status"], "available_unknown_format")

        docx_hints = by_name["1003_UTCForm_Spec_Drawing.docx"]["filename_hints"]
        self.assertIn("possible UTC form", docx_hints)
        self.assertIn("possible configuration file", docx_hints)
        self.assertIn("possible drawing / layout file", docx_hints)

        self.assertNotIn("junction_type", inventory)
        self.assertNotIn("controller_type", inventory)
        self.assertNotIn("stream_count", inventory)
        self.assertNotIn("site_level_hints", inventory)
        self.assertNotIn("manual_questions", inventory)

    def test_inventory_cli_writes_site_inventory_partial_json(self):
        base = _workspace_test_dir()
        site_folder = base / "397L"
        out_dir = base / "outputs"
        site_folder.mkdir()
        (site_folder / "397L_RAMData.txt").write_text("ram", encoding="utf-8")

        exit_code = main(
            [
                "inventory",
                "--site-folder",
                str(site_folder),
                "--out-dir",
                str(out_dir),
                "--site-id",
                "397L",
                "--dataset",
                "Leeds",
            ]
        )

        output_path = out_dir / "site_inventory.partial.json"
        output = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(output["site_id"], "397L")
        self.assertEqual(output["site_name"], "397L")
        self.assertEqual(output["local_authority_or_dataset"], "Leeds")
        self.assertEqual(output["inventory_summary"]["total_files"], 1)
        self.assertEqual(output["source_files"][0]["parser_to_use"], "ram_text_parser")

    def test_inventory_cli_defaults_output_directory_from_site_folder_name(self):
        base = _workspace_test_dir()
        site_folder = base / f"397L_{uuid.uuid4().hex}"
        site_folder.mkdir()
        (site_folder / "397L_RAMData.txt").write_text("ram", encoding="utf-8")

        exit_code = main(
            [
                "inventory",
                "--site-folder",
                str(site_folder),
                "--site-id",
                "397L",
            ]
        )

        output_path = Path("outputs") / site_folder.name / "site_inventory.partial.json"
        output = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(output["site_id"], "397L")
        self.assertEqual(output["site_name"], site_folder.name)
        self.assertEqual(output["inventory_summary"]["total_files"], 1)

def _workspace_test_dir() -> Path:
    base = Path("outputs") / f"test_inventory_{uuid.uuid4().hex}"
    base.mkdir(parents=True)
    return base


if __name__ == "__main__":
    unittest.main()
