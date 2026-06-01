from __future__ import annotations

from pathlib import Path
from typing import Callable

from mapemgen.ingestion.cad import extract_dwg_facts, extract_dxf_facts
from mapemgen.ingestion.docx_tables import extract_docx_facts
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
    "mova": ("mova_availability_recorder", extract_mova_facts),
}


def extract_inventory_facts(inventory: dict) -> dict:
    if not inventory.get("site_id"):
        raise ValueError("Inventory must contain site_id")
    source_files = inventory.get("source_files")
    if not isinstance(source_files, list):
        raise ValueError("Inventory must contain a source_files list")
    results = [_extract_source_file(source) for source in source_files]
    return {"site_id": str(inventory["site_id"]), "source_files": results}


def _extract_source_file(source: dict) -> dict:
    file_type = str(source.get("file_type", "")).lower()
    source_file = str(source.get("file_path", ""))
    parser_entry = PARSERS.get(file_type)
    if parser_entry is None:
        return {"source_file": source_file, "file_type": file_type, "parser": "manual_review", "status": "unsupported", "extracted_facts": []}
    parser_name, parser = parser_entry
    try:
        facts = parser(source_file)
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
    return {"source_file": source_file, "file_type": file_type, "parser": parser_name, "status": "parsed", "extracted_facts": facts}

