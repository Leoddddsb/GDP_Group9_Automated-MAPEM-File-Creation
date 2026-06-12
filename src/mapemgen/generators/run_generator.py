import argparse
import json
from pathlib import Path

from asn1_mapem import generate_asn1_mapem
from json_mapem import generate_json_mapem


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="src/mapemgen/fusion/fused_model.sample.json")
    parser.add_argument("--out-dir", default="outputs/generator_demo")
    args = parser.parse_args()

    input_path = _path(args.input)
    out_dir = _path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fused_model = json.loads(input_path.read_text(encoding="utf-8"))
    mapem_json = generate_json_mapem(fused_model)
    mapem_asn1 = generate_asn1_mapem(fused_model)

    (out_dir / "mapem.json").write_text(
        json.dumps(mapem_json, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "mapem.asn1").write_text(mapem_asn1, encoding="utf-8")

    print(out_dir / "mapem.json")
    print(out_dir / "mapem.asn1")


def _path(path):
    value = Path(path)
    if value.is_absolute():
        return value
    return Path.cwd() / value


if __name__ == "__main__":
    main()
