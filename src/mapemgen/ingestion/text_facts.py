from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


KEYWORD_FACTS = {
    "phase": "phase_candidate",
    "stage": "stage_candidate",
    "stream": "stream_candidate",
    "intergreen": "intergreen_candidate",
    "detector": "detector_candidate",
    "i/o": "io_allocation_candidate",
    "input/output": "io_allocation_candidate",
    "scoot": "scoot_link_candidate",
    "timing": "timing_candidate",
    "override": "ram_override_candidate",
    "control": "control_candidate",
}

IP_ADDRESS_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
SCN_PATTERN = re.compile(r"\b[JSXY]\d{4,}\b", re.IGNORECASE)
SITE_DESCRIPTION_PATTERN = re.compile(r"junction\s+description\s*[:=-]\s*(.+)", re.IGNORECASE)


def read_text_with_fallback(path: str | Path) -> str:
    data = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", data, 0, len(data), "No supported text encoding")


def extract_keyword_facts(lines: Iterable[str], location_prefix: str = "line", exact_location: bool = False) -> list[dict]:
    facts: list[dict] = []
    for index, raw_line in enumerate(lines, start=1):
        line = " ".join(raw_line.split())
        if not line:
            continue
        lowered = line.lower()
        emitted: set[str] = set()
        for keyword, fact_type in KEYWORD_FACTS.items():
            if keyword in lowered and fact_type not in emitted:
                location = location_prefix if exact_location else f"{location_prefix} {index}"
                facts.append(_fact(fact_type, line, location, 0.65))
                emitted.add(fact_type)
    return facts


def extract_metadata_facts(lines: Iterable[str], location_prefix: str = "line", exact_location: bool = False) -> list[dict]:
    facts: list[dict] = []
    for index, raw_line in enumerate(lines, start=1):
        line = " ".join(raw_line.split())
        if not line:
            continue
        location = location_prefix if exact_location else f"{location_prefix} {index}"
        description = SITE_DESCRIPTION_PATTERN.search(line)
        if description:
            facts.append(_fact("site_description", description.group(1).strip(), location, 0.9))
        for value in SCN_PATTERN.findall(line):
            facts.append(_fact("scn", value.upper(), location, 0.9))
        for value in IP_ADDRESS_PATTERN.findall(line):
            facts.append(_fact("ip_address", value, location, 0.9))
    return facts


def printable_fragments(data: bytes, minimum_length: int = 4) -> list[str]:
    pattern = rb"[\x20-\x7e]{" + str(minimum_length).encode("ascii") + rb",}"
    return [match.decode("ascii") for match in re.findall(pattern, data)]


def _fact(fact_type: str, value: object, location: str, confidence: float) -> dict:
    return {
        "fact_type": fact_type,
        "value": value,
        "evidence_location": location,
        "confidence": confidence,
    }
