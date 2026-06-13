from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from mapemgen.ingestion.cad import extract_dwg_facts, extract_dxf_facts
from mapemgen.ingestion.docx_tables import extract_docx_facts
from mapemgen.ingestion.fact_records import with_evidence_prefix, with_source_file
from mapemgen.ingestion.gis import extract_gis_facts
from mapemgen.ingestion.mova import extract_mova_facts
from mapemgen.ingestion.pdf_tables import extract_pdf_facts
from mapemgen.ingestion.ram_text import extract_ram_text_facts
from mapemgen.ingestion.zip_packages import extract_zip_facts


Parser = Callable[[str | Path], list[dict]]
CAD_FILE_TYPES = {"dwg", "dxf"}
CAD_METADATA_FACT_NAMES = {"cad_layer_names", "cad_entity_counts", "coordinate_bounds"}

PARSERS: dict[str, tuple[str, Parser]] = {
    "txt": ("ram_text_parser", extract_ram_text_facts),
    "8tx": ("ram_text_parser", extract_ram_text_facts),
    "zip": ("zip_inventory_parser", extract_zip_facts),
    "docx": ("docx_parser", extract_docx_facts),
    "pdf": ("pdf_parser", extract_pdf_facts),
    "dxf": ("cad_parser", extract_dxf_facts),
    "dwg": ("cad_parser_after_conversion", extract_dwg_facts),
    "geojson": ("gis_parser", extract_gis_facts),
    "json": ("gis_parser", extract_gis_facts),
    "osm": ("gis_parser", extract_gis_facts),
    "shp": ("gis_parser", extract_gis_facts),
    "gpkg": ("gis_parser", extract_gis_facts),
    "mova": ("mova_tools_export_boundary", extract_mova_facts),
}


def extract_site_folder_facts(site_folder: str | Path, site_id: str) -> dict:
    folder = Path(site_folder)
    if not folder.exists():
        raise FileNotFoundError(f"Site folder does not exist: {folder}")
    if not folder.is_dir():
        raise ValueError(f"Site folder must be a directory: {folder}")
    source_files = [
        {"file_path": path.as_posix(), "file_type": path.suffix.lower().lstrip(".") or "unknown"}
        for path in sorted((path for path in folder.rglob("*") if path.is_file()), key=lambda path: path.as_posix())
    ]
    standalone_cad_names = {
        Path(source["file_path"]).name.lower()
        for source in source_files
        if source["file_type"] in CAD_FILE_TYPES
    }
    return {
        "site_id": str(site_id),
        "source_files": [
            _extract_source_file(source, site_id=str(site_id), standalone_cad_names=standalone_cad_names)
            for source in source_files
        ],
    }


def extract_file_facts(path: str | Path, zip_depth: int = 0) -> list[dict]:
    target = Path(path)
    file_type = target.suffix.lower().lstrip(".") or "unknown"
    parser_entry = PARSERS.get(file_type)
    if parser_entry is None:
        return []
    _, parser = parser_entry
    if file_type == "zip":
        return extract_zip_facts(target, depth=zip_depth)
    return parser(target)


def _extract_source_file(source: dict, site_id: str, standalone_cad_names: set[str]) -> dict:
    file_type = str(source.get("file_type", "")).lower()
    source_file = str(source.get("file_path", ""))
    parser_entry = PARSERS.get(file_type)
    if parser_entry is None:
        return {"source_file": source_file, "file_type": file_type, "parser": "manual_review", "status": "unsupported", "extracted_facts": []}
    parser_name, parser = parser_entry
    if file_type in CAD_FILE_TYPES and not _is_site_cad_source(source_file, site_id):
        return {
            "source_file": source_file,
            "file_type": file_type,
            "parser": parser_name,
            "status": "skipped",
            "skip_reason": "non_site_cad_source",
            "extracted_facts": [],
        }
    try:
        if file_type == "zip":
            facts = extract_zip_facts(source_file, ignored_cad_member_basenames=standalone_cad_names)
        else:
            facts = extract_file_facts(source_file)
        if file_type in CAD_FILE_TYPES and _is_topographic_source(source_file):
            facts = _cad_metadata_only(facts)
    except RuntimeError:
        raise
    except Exception as exc:
        return {
            "source_file": source_file,
            "file_type": file_type,
            "parser": parser_name,
            "status": "parser_error",
            "error": str(exc),
            "extracted_facts": [],
        }
    return {
        "source_file": source_file,
        "file_type": file_type,
        "parser": parser_name,
        "status": "parsed",
        "extracted_facts": _prefix_source_file(facts, source_file),
    }


def _prefix_source_file(facts: list[dict], source_file: str) -> list[dict]:
    prefixed: list[dict] = []
    for fact in facts:
        prefixed.append(with_source_file(with_evidence_prefix(fact, source_file), source_file))
    return prefixed


def _is_site_cad_source(source_file: str, site_id: str) -> bool:
    if _filename_contains_site_token(Path(source_file).name, site_id):
        return True
    source_token = _leading_site_token(Path(source_file).name)
    if source_token is None:
        return True
    return source_token == _normalise_site_token(site_id)


def _filename_contains_site_token(name: str, site_id: str) -> bool:
    token = _normalise_site_token(site_id)
    if not token:
        return False
    pattern = rf"(?<![0-9a-z]){re.escape(token)}(?![0-9a-z])"
    return re.search(pattern, name.lower()) is not None


def _leading_site_token(name: str) -> str | None:
    match = re.match(r"^t?([0-9]+[a-z]?)(?:[^0-9a-z]|$)", name, flags=re.IGNORECASE)
    if not match:
        return None
    return _normalise_site_token(match.group(1))


def _normalise_site_token(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", str(value).lower())


def _is_topographic_source(source_file: str) -> bool:
    name = Path(source_file).name.lower()
    return "topo" in name or name.startswith("os-") or name.startswith("os_")


def _cad_metadata_only(facts: list[dict]) -> list[dict]:
    return [fact for fact in facts if fact.get("fact_name") in CAD_METADATA_FACT_NAMES]
