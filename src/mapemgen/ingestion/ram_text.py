from __future__ import annotations

from pathlib import Path

from mapemgen.ingestion.text_facts import extract_keyword_facts, extract_metadata_facts, read_text_with_fallback


def extract_ram_text_facts(path: str | Path) -> list[dict]:
    lines = read_text_with_fallback(path).splitlines()
    name = Path(path).name.lower()
    source_role = "ram_8tx" if Path(path).suffix.lower() == ".8tx" or "ram" in name else None
    return extract_keyword_facts(lines, source_role=source_role) + extract_metadata_facts(lines)
