from __future__ import annotations

import shutil
import zipfile
from tempfile import NamedTemporaryFile
from pathlib import Path, PurePosixPath
from typing import Callable

from mapemgen.ingestion.fact_records import make_fact, with_evidence_prefix


PARSEABLE_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".dwg",
    ".dxf",
    ".txt",
    ".8tx",
    ".mova",
    ".json",
    ".geojson",
    ".osm",
    ".shp",
    ".gpkg",
    ".zip",
}
MAX_ARCHIVE_DEPTH = 5
MAX_MEMBER_SIZE_BYTES = 100 * 1024 * 1024

MemberParser = Callable[[str | Path, int], list[dict]]


def extract_zip_facts(
    path: str | Path,
    depth: int = 0,
    member_parser: MemberParser | None = None,
    ignored_cad_member_basenames: set[str] | None = None,
) -> list[dict]:
    if depth >= MAX_ARCHIVE_DEPTH:
        raise ValueError(f"ZIP nesting exceeds maximum depth of {MAX_ARCHIVE_DEPTH}")
    parser = member_parser or _default_member_parser
    ignored_cad_names = ignored_cad_member_basenames or set()
    facts: list[dict] = []
    with zipfile.ZipFile(path) as archive:
        members = sorted(
            (info for info in archive.infolist() if not info.is_dir()),
            key=lambda info: info.filename,
        )
        for index, info in enumerate(members, start=1):
            member = info.filename
            location = f"archive member {index}"
            pure_path = _safe_member_path(member)
            member_payload = {"member": member, "status": "available"}
            if pure_path is None:
                member_payload["status"] = "rejected"
                member_payload["reason"] = "unsafe_archive_path"
                facts.append(_fact("archive_member", member_payload, location, 1.0))
                continue
            lowered = member.lower()
            suffix = pure_path.suffix.lower()
            if suffix in {".dwg", ".dxf"} and pure_path.name.lower() in ignored_cad_names:
                member_payload["status"] = "skipped"
                member_payload["reason"] = "duplicate_standalone_cad"
                facts.append(_fact("archive_member", member_payload, location, 1.0))
                continue
            if suffix == ".dwg":
                member_payload["cad_member_role"] = "xref_dwg" if len(pure_path.parts) > 1 else "root_dwg"
                if "os" in pure_path.stem.lower() or "topo" in lowered:
                    member_payload["drawing_role"] = "topographic"
            if suffix not in PARSEABLE_EXTENSIONS:
                facts.append(_fact("archive_member", member_payload, location, 1.0))
                continue
            member_payload["parseable"] = True
            if info.file_size > MAX_MEMBER_SIZE_BYTES:
                member_payload["status"] = "rejected"
                member_payload["reason"] = "member_too_large"
                facts.append(_fact("archive_member", member_payload, location, 1.0))
                continue
            facts.append(_fact("archive_member", member_payload, location, 1.0))
            nested_facts = _extract_member_facts(archive, info, suffix, parser, depth)
            facts.extend(_prefix_locations(nested_facts, f"archive member {member}"))
    return facts


def _default_member_parser(path: str | Path, depth: int) -> list[dict]:
    from mapemgen.ingestion.facts import extract_file_facts

    return extract_file_facts(path, zip_depth=depth)


def _extract_member_facts(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    suffix: str,
    parser: MemberParser,
    depth: int,
) -> list[dict]:
    with NamedTemporaryFile(prefix="mapemgen_zip_", suffix=suffix, delete=False) as target:
        extracted_path = Path(target.name)
        with archive.open(info) as source:
            shutil.copyfileobj(source, target)
    try:
        return parser(extracted_path, depth + 1)
    finally:
        extracted_path.unlink(missing_ok=True)


def _safe_member_path(member: str) -> PurePosixPath | None:
    pure_path = PurePosixPath(member.replace("\\", "/"))
    if pure_path.is_absolute():
        return None
    if any(part in {"", ".", ".."} or ":" in part for part in pure_path.parts):
        return None
    return pure_path


def _prefix_locations(facts: list[dict], prefix: str) -> list[dict]:
    prefixed: list[dict] = []
    for fact in facts:
        prefixed.append(with_evidence_prefix(fact, prefix))
    return prefixed


def _fact(fact_name: str, value: object, location: str, confidence: float) -> dict:
    return make_fact(fact_name, value, location, confidence)

