"""PDF text and table extraction for MAPEM-relevant candidates."""

from __future__ import annotations

from pathlib import Path

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
            if text:
                lines = text.splitlines()
                facts.extend(extract_keyword_facts(lines, f"page {page_number} line", source_role=source_role))
                facts.extend(extract_metadata_facts(lines, f"page {page_number} line"))
            else:
                facts.append(_fact("needs_future_recognition", "PDF page has no extractable text", f"page {page_number}", 1.0))
            for table_number, table in enumerate(page.extract_tables() or [], start=1):
                for row_number, row in enumerate(table or [], start=1):
                    cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                    if not cells:
                        continue
                    value = " | ".join(cells)
                    location = f"page {page_number} table {table_number} row {row_number}"
                    facts.append(_fact("pdf_table_row", value, location, 0.8))
                    facts.extend(extract_keyword_facts([value], location, exact_location=True, source_role=source_role))
                    facts.extend(extract_metadata_facts([value], location, exact_location=True))
    return facts


def _source_role(path: str | Path) -> str | None:
    name = Path(path).name.lower()
    if any(token in name for token in ("2500", "config", "configuration")):
        return "controller_config"
    return None


def _fact(fact_type: str, value: object, location: str, confidence: float) -> dict:
    return {"fact_type": fact_type, "value": value, "evidence_location": location, "confidence": confidence}
