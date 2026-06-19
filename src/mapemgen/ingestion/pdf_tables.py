"""PDF text and table extraction for MAPEM-relevant candidates."""

from __future__ import annotations

from pathlib import Path

from mapemgen.ingestion.movement_tables import (
    extract_controller_config_movement_facts,
    extract_controller_config_table_facts,
    extract_controller_config_text_facts,
)
from mapemgen.ingestion.pdf_cv import describe_image_page, extract_pdf_image_facts, extract_pdf_vector_facts
from mapemgen.ingestion.text_facts import extract_keyword_facts, extract_metadata_facts


def extract_pdf_facts(path: str | Path) -> list[dict]:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("PDF extraction requires the 'pdfplumber' package.") from exc

    facts: list[dict] = []
    source_role = _source_role(path)
    with pdfplumber.open(path) as document:
        for page_number, page in enumerate(document.pages, start=1):
            text = (page.extract_text() or "").strip()
            tables = page.extract_tables() or []
            images = list(getattr(page, "images", []) or [])
            page_role = source_role or _content_source_role(text, tables)
            if text:
                lines = text.splitlines()
                if page_role == "controller_config":
                    facts.extend(extract_controller_config_text_facts(lines, f"page {page_number} line"))
                else:
                    facts.extend(extract_keyword_facts(lines, f"page {page_number} line", source_role=page_role))
                facts.extend(extract_metadata_facts(lines, f"page {page_number} line"))
            if images:
                facts.extend(describe_image_page(page, page_number))
                try:
                    facts.extend(extract_pdf_image_facts(str(path), page_numbers=[page_number]))
                except Exception:
                    pass
            facts.extend(extract_pdf_vector_facts(page, page_number))
            for table_number, table in enumerate(tables, start=1):
                table_location = f"page {page_number} table {table_number}"
                if page_role == "controller_config":
                    facts.extend(extract_controller_config_table_facts(table, table_location))
                for row_number, row in enumerate(table or [], start=1):
                    cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                    if not cells:
                        continue
                    value = " | ".join(cells)
                    location = f"page {page_number} table {table_number} row {row_number}"
                    if page_role == "controller_config":
                        facts.extend(extract_controller_config_movement_facts(cells, location))
                    if page_role != "controller_config":
                        facts.extend(extract_keyword_facts([value], location, exact_location=True, source_role=page_role))
                    facts.extend(extract_metadata_facts([value], location, exact_location=True))
    return facts


def _source_role(path: str | Path) -> str | None:
    name = Path(path).name.lower()
    if any(token in name for token in ("2500", "config", "configuration")):
        return "controller_config"
    return None


def _content_source_role(text: str, tables: list[list[list[str | None]]]) -> str | None:
    joined_tables = " ".join(
        str(cell)
        for table in tables or []
        for row in table or []
        for cell in row or []
        if cell is not None
    )
    content = f"{text} {joined_tables}".lower()
    if any(token in content for token in ("use of phases", "use of stages", "uk traffic", "phase intergreen")):
        return "controller_config"
    return None
