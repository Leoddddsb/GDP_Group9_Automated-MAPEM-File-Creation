from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def run_step(step_name: str, command: list[str], cwd: Path | None = None) -> None:
    print("\n" + "=" * 80)
    print(f"Running: {step_name}")
    print("=" * 80)
    print("Command:")
    print(" ".join(command))
    print()

    subprocess.run(
        command,
        cwd=str(cwd or PROJECT_ROOT),
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full MAPEM pipeline for one site."
    )
    parser.add_argument(
        "site_id",
        nargs="?",
        default="337L",
        help="Site ID to process, e.g. 337L, 1003, 1062. Default: 337L",
    )
    args = parser.parse_args()

    site_id = args.site_id
    site_folder = PROJECT_ROOT / "data" / site_id
    out_dir = PROJECT_ROOT / "outputs" / site_id

    if not site_folder.exists():
        raise FileNotFoundError(f"Site folder does not exist: {site_folder}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # Mac ODA File Converter path
    os.environ["ODAFC_PATH"] = (
        "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"
    )

    print(f"Project root: {PROJECT_ROOT}")
    print(f"Site ID: {site_id}")
    print(f"Site folder: {site_folder}")
    print(f"Output folder: {out_dir}")

    # Step 1: inventory
    run_step(
        "Step 1 - Inventory",
        [
            sys.executable,
            "-m",
            "mapemgen.cli",
            "inventory",
            "--site-folder",
            str(site_folder),
            "--site-id",
            site_id,
            "--out-dir",
            str(out_dir),
        ],
    )

    # Step 2: extract facts
    run_step(
        "Step 2 - Extract facts",
        [
            sys.executable,
            "-m",
            "mapemgen.cli",
            "extract",
            "--site-folder",
            str(site_folder),
            "--site-id",
            site_id,
            "--out-dir",
            str(out_dir),
        ],
    )

    # Step 3: assign geometry
    run_step(
        "Step 3 - Assign geometry",
        [
            sys.executable,
            "-m",
            "mapemgen.cli",
            "assign-geometry",
            "--input",
            str(out_dir / "extracted_facts.partial.json"),
            "--out-dir",
            str(out_dir),
        ],
    )

    matching_dir = PROJECT_ROOT / "src" / "mapemgen" / "matching"

    # Step 4: ingest adapter
    run_step(
        "Step 4 - Ingest adapter",
        [
            sys.executable,
            "ingest_adapter.py",
            "--facts",
            str(out_dir / "extracted_facts.partial.json"),
            "--assignments",
            str(out_dir / "geometry_assignments.partial.json"),
            "--out",
            str(out_dir / f"facts.{site_id}.json"),
        ],
        cwd=matching_dir,
    )

    # Step 5: matching
    run_step(
        "Step 5 - Matching",
        [
            sys.executable,
            "matching_engine.py",
            "--rules",
            "matching_rules.yaml",
            "--facts",
            str(out_dir / f"facts.{site_id}.json"),
            "--config",
            f"site_config_{site_id}.yaml",
            "--transforms",
            "transforms_overlay",
            "--out",
            str(out_dir / f"mapped_evidence.{site_id}.json"),
        ],
        cwd=matching_dir,
    )

    # Step 6: fusion
    run_step(
        "Step 6 - Fusion",
        [
            sys.executable,
            str(PROJECT_ROOT / "src" / "mapemgen" / "fusion" / "fuse.py"),
            "--evidence",
            str(out_dir / f"mapped_evidence.{site_id}.json"),
            "--out",
            str(out_dir / f"fused_model.{site_id}.json"),
            "--report",
            str(out_dir / f"fusion_report.{site_id}.json"),
        ],
    )

    print("\n" + "=" * 80)
    print("Pipeline finished.")
    print("=" * 80)
    print("Main outputs:")
    print(out_dir / "site_inventory.partial.json")
    print(out_dir / "extracted_facts.partial.json")
    print(out_dir / "geometry_assignments.partial.json")
    print(out_dir / f"facts.{site_id}.json")
    print(out_dir / f"mapped_evidence.{site_id}.json")
    print(out_dir / f"fused_model.{site_id}.json")
    print(out_dir / f"fusion_report.{site_id}.json")


if __name__ == "__main__":
    main()