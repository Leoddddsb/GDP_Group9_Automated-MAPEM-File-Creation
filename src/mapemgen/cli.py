from __future__ import annotations

import argparse
from pathlib import Path

from mapemgen.assignment.geometry import assign_geometry_to_lanes, default_assignment_output_path
from mapemgen.ingestion.inventory import build_site_inventory
from mapemgen.io import read_json, write_json, write_text
from mapemgen.models import SiteModel
from mapemgen.pipeline import generate_outputs, validate_site


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mapemgen")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--input", required=True)

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--input", required=True)
    generate_parser.add_argument("--out-dir", required=True)

    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("--site-folder", required=True)
    inventory_parser.add_argument("--out-dir")
    inventory_parser.add_argument("--site-id", required=True)
    inventory_parser.add_argument("--site-name", default="")
    inventory_parser.add_argument("--dataset", default="")

    assign_geometry_parser = subparsers.add_parser("assign-geometry")
    assign_geometry_parser.add_argument("--input", required=True)
    assign_geometry_parser.add_argument("--out-dir", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "inventory":
        inventory = build_site_inventory(
            args.site_folder,
            site_id=args.site_id,
            site_name=args.site_name,
            dataset=args.dataset,
        )
        out_dir = Path(args.out_dir) if args.out_dir else Path("outputs") / Path(args.site_folder).name
        output_path = out_dir / "site_inventory.partial.json"
        write_json(output_path, inventory)
        print(f"Wrote site inventory to {output_path}")
        return 0

    if args.command == "assign-geometry":
        assignments = assign_geometry_to_lanes(read_json(args.input))
        output_path = default_assignment_output_path(args.out_dir)
        write_json(output_path, assignments)
        print(f"Wrote geometry assignments to {output_path}")
        return 0

    site = SiteModel.from_dict(read_json(args.input))

    if args.command == "validate":
        report = validate_site(site)
        print(report.to_json())
        return 0 if report.is_usable else 2

    if args.command == "generate":
        out_dir = Path(args.out_dir)
        outputs = generate_outputs(site)
        write_json(out_dir / "mapem.json", outputs.mapem_json)
        write_text(out_dir / "mapem.asn1", outputs.mapem_asn1)
        write_json(out_dir / "validation_report.json", outputs.validation_report)
        print(f"Wrote MAPEM outputs to {out_dir}")
        return 0 if outputs.validation_report["is_usable"] else 2

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
