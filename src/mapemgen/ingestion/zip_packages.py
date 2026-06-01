from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath


PARSEABLE_EXTENSIONS = {".pdf", ".docx", ".dwg", ".dxf", ".txt", ".8tx", ".mova", ".json", ".geojson", ".osm"}


def extract_zip_facts(path: str | Path) -> list[dict]:
    facts: list[dict] = []
    with zipfile.ZipFile(path) as archive:
        members = sorted(name for name in archive.namelist() if not name.endswith("/"))
    for index, member in enumerate(members, start=1):
        location = f"archive member {index}"
        facts.append(_fact("archive_member", member, location, 1.0))
        pure_path = PurePosixPath(member)
        lowered = member.lower()
        if pure_path.suffix.lower() == ".dwg":
            dwg_type = "xref_dwg_candidate" if len(pure_path.parts) > 1 else "root_dwg_candidate"
            facts.append(_fact(dwg_type, member, location, 0.8))
            if "os" in pure_path.stem.lower() or "topo" in lowered:
                facts.append(_fact("topographic_drawing_available", member, location, 0.85))
        if pure_path.suffix.lower() in PARSEABLE_EXTENSIONS:
            facts.append(_fact("nested_parseable_file_available", member, location, 0.75))
    return facts


def _fact(fact_type: str, value: object, location: str, confidence: float) -> dict:
    return {"fact_type": fact_type, "value": value, "evidence_location": location, "confidence": confidence}

