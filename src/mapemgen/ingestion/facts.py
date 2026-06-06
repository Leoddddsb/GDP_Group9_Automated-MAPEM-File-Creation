from __future__ import annotations

from pathlib import Path
from typing import Callable

from mapemgen.ingestion.cad import extract_dwg_facts, extract_dxf_facts
from mapemgen.ingestion.docx_tables import extract_docx_facts
from mapemgen.ingestion.fact_names import apply_dictionary_fact_name
from mapemgen.ingestion.gis import extract_gis_facts
from mapemgen.ingestion.mova import extract_mova_facts
from mapemgen.ingestion.pdf_tables import extract_pdf_facts
from mapemgen.ingestion.ram_text import extract_ram_text_facts
from mapemgen.ingestion.zip_packages import extract_zip_facts


Parser = Callable[[str | Path], list[dict]]

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
    return {"site_id": str(site_id), "source_files": [_extract_source_file(source) for source in source_files]}


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


def _extract_source_file(source: dict) -> dict:
    file_type = str(source.get("file_type", "")).lower()
    source_file = str(source.get("file_path", ""))
    parser_entry = PARSERS.get(file_type)
    if parser_entry is None:
        return {"source_file": source_file, "file_type": file_type, "parser": "manual_review", "status": "unsupported", "extracted_facts": []}
    parser_name, parser = parser_entry
    try:
        facts = extract_file_facts(source_file)
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
        item = dict(fact)
        item["evidence_location"] = f"{source_file} -> {fact['evidence_location']}"
        prefixed.append(apply_dictionary_fact_name(item, source_file))
    return prefixed
