from __future__ import annotations

from pathlib import Path

from mapemgen.ingestion.text_facts import extract_keyword_facts, extract_metadata_facts, read_text_with_fallback


def extract_ram_text_facts(path: str | Path) -> list[dict]:
    lines = read_text_with_fallback(path).splitlines()
    return extract_keyword_facts(lines) + extract_metadata_facts(lines)
