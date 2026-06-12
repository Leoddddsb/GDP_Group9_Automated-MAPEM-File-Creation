from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from mapemgen.ingestion.fact_records import make_fact


DEFAULT_KEYWORD_FACTS = {
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

ROLE_KEYWORD_FACTS = {
    "ram_8tx": {
        **DEFAULT_KEYWORD_FACTS,
        "phase": "phase_label_from_ram_8tx",
        "stage": "stage_phase_relationship_from_ram_8tx",
        "intergreen": "stage_phase_relationship_from_ram_8tx",
        "timing": "stage_phase_relationship_from_ram_8tx",
        "override": "movement_phase_mapping_from_ram_8tx",
        "control": "movement_phase_mapping_from_ram_8tx",
    },
    "utc_form": {
        **DEFAULT_KEYWORD_FACTS,
        "phase": "phase_label_from_utc_form",
        "stage": "stage_phase_relationship_from_utc_form",
        "intergreen": "stage_phase_relationship_from_utc_form",
        "timing": "stage_phase_relationship_from_utc_form",
        "control": "movement_phase_mapping_from_utc_form",
    },
    "controller_config": {
        **DEFAULT_KEYWORD_FACTS,
        "phase": "phase_label_from_controller_config",
        "stage": "stage_phase_relationship_from_controller_config",
        "intergreen": "stage_phase_relationship_from_controller_config",
        "timing": "stage_phase_relationship_from_controller_config",
        "control": "movement_phase_mapping_from_controller_config",
    },
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


def extract_keyword_facts(
    lines: Iterable[str],
    location_prefix: str = "line",
    exact_location: bool = False,
    source_role: str | None = None,
) -> list[dict]:
    facts: list[dict] = []
    keyword_facts = ROLE_KEYWORD_FACTS.get(source_role or "", DEFAULT_KEYWORD_FACTS)
    for index, raw_line in enumerate(lines, start=1):
        line = " ".join(raw_line.split())
        if not line:
            continue
        lowered = line.lower()
        emitted: set[str] = set()
        for keyword, fact_name in keyword_facts.items():
            if keyword in lowered and fact_name not in emitted:
                location = location_prefix if exact_location else f"{location_prefix} {index}"
                facts.append(_fact(fact_name, line, location, 0.65))
                emitted.add(fact_name)
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


def _fact(fact_name: str, value: object, location: str, confidence: float) -> dict:
    return make_fact(fact_name, value, location, confidence)
