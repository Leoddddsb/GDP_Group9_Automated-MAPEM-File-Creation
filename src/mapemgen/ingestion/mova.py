from __future__ import annotations

from pathlib import Path

from mapemgen.ingestion.text_facts import extract_keyword_facts, printable_fragments


def extract_mova_facts(path: str | Path) -> list[dict]:
    target = Path(path)
    fragments = printable_fragments(target.read_bytes())
    facts = [
        {
            "fact_type": "mova_shallow_extraction_limitation",
            "value": "MOVA binary fields are not fully decoded; printable text extraction only.",
            "evidence_location": "file",
            "confidence": 1.0,
        },
        {
            "fact_type": "file_metadata",
            "value": {"file_size_bytes": target.stat().st_size},
            "evidence_location": "file",
            "confidence": 1.0,
        },
    ]
    facts.extend(extract_keyword_facts(fragments, location_prefix="printable fragment"))
    return facts

