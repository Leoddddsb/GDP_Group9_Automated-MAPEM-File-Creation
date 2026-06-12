from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from mapemgen.generators.asn1_mapem import generate_asn1_mapem
from mapemgen.generators.json_mapem import generate_json_mapem


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert fused_model.json to MAPEM outputs.")
    parser.add_argument(
        "--input",
        default="src/mapemgen/fusion/fused_model.sample.json",
        help="Path to fused_model.json from the fusion stage.",
    )
    parser.add_argument(
        "--out-dir",
        default="outputs/generator_demo",
        help="Directory where mapem.json and mapem.asn1 will be written.",
    )
    args = parser.parse_args()

    input_path = _project_path(args.input)
    out_dir = _project_path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fused_model = json.loads(input_path.read_text(encoding="utf-8"))
    mapem_json = generate_json_mapem(fused_model)
    mapem_asn1 = generate_asn1_mapem(fused_model)

    (out_dir / "mapem.json").write_text(
        json.dumps(mapem_json, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "mapem.asn1").write_text(mapem_asn1, encoding="utf-8")

    print(f"Wrote {out_dir / 'mapem.json'}")
    print(f"Wrote {out_dir / 'mapem.asn1'}")
    return 0


def _project_path(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


if __name__ == "__main__":
    raise SystemExit(main())
