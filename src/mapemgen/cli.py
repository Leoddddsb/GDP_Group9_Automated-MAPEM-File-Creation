from __future__ import annotations

import argparse
from pathlib import Path

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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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

