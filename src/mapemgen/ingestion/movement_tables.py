from __future__ import annotations

import re
from typing import Any

from mapemgen.ingestion.fact_records import make_fact


PHASE_MOVEMENT_FACT = "movement_phase_mapping_from_controller_config"
PHASE_LABEL_FACT = "phase_label_from_controller_config"
SCOOT_LINK_MOVEMENT_FACT = "movement_direction_candidate_from_utc_form"
PHASE_SCOOT_LINK_FACT = "movement_phase_mapping_from_utc_form"
SCOOT_LINK_STAGE_FACT = "stage_phase_relationship_from_utc_form"

PHASE_TYPES = {"T", "P", "F", "I", "S", "D", "L"}


def extract_controller_config_movement_facts(cells: list[str], location: str) -> list[dict[str, Any]]:
    text = " ".join(cell.strip() for cell in cells if cell.strip())
    if not text:
        return []
    facts: list[dict[str, Any]] = []
    for match in re.finditer(r"\b([A-Z])\s+([A-Z][A-Z /]+?)\s+\d+\s+-\s+UK\s+Traffic\b", text):
        phase_label = match.group(1)
        movement_text = _clean_spaces(match.group(2))
        payload = _movement_payload(movement_text)
        payload.update({"phase_ref": _phase_ref(phase_label), "phase_label": phase_label})
        facts.append(make_fact(PHASE_MOVEMENT_FACT, _ordered_phase_payload(payload), location, 0.86))
    return facts


def extract_controller_config_text_facts(lines: list[str], location_prefix: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for index, raw_line in enumerate(lines, start=1):
        line = _clean_spaces(raw_line)
        if not line:
            continue
        location = f"{location_prefix} {index}"
        phase_match = re.fullmatch(r"Phase\s+([A-Z](?:\d+)?)", line, flags=re.IGNORECASE)
        if phase_match:
            label = phase_match.group(1).upper()
            facts.append(make_fact(
                PHASE_LABEL_FACT,
                {"phase_ref": _phase_ref(label), "phase_label": label},
                location,
                0.75,
            ))
            continue
        stage_match = re.fullmatch(r"Stage\s+(\d+)(?:\s+.*)?", line, flags=re.IGNORECASE)
        if stage_match:
            stage_number = int(stage_match.group(1))
            facts.append(make_fact(
                "stage_phase_relationship_from_controller_config",
                {"stage_ref": f"stage_{stage_number}", "stage_number": stage_number},
                location,
                0.65,
            ))
    return facts


def extract_controller_config_table_facts(table: list[list[str | None]], location: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    facts.extend(extract_use_of_phases_facts(table, location))
    facts.extend(extract_use_of_stages_facts(table, location))
    return facts


def extract_use_of_phases_facts(table: list[list[str | None]], location: str) -> list[dict[str, Any]]:
    rows = [_clean_row(row) for row in table or []]
    if not rows or "use of phases" not in _table_text(rows).lower():
        return []

    facts: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows, start=1):
        if not row:
            continue
        phase_label = row[0].upper()
        if not re.fullmatch(r"[A-Z](?:\d+)?", phase_label):
            continue
        phase_type_index = _phase_type_index(row)
        if phase_type_index is None:
            continue
        phase_type = row[phase_type_index].upper()
        movement_text = _clean_movement_description(row[1:phase_type_index])
        if not movement_text:
            continue
        payload = {
            "phase_ref": _phase_ref(phase_label),
            "phase_label": phase_label,
            "phase_type": phase_type,
            "movement_text": _display_movement_text(movement_text),
        }
        facts.append(make_fact(PHASE_LABEL_FACT, payload, f"{location} row {row_index}", 0.9))
        if phase_type == "D":
            continue
        movement_payload = _movement_payload(movement_text)
        movement_payload.update({
            "phase_ref": _phase_ref(phase_label),
            "phase_label": phase_label,
            "phase_type": phase_type,
        })
        facts.append(make_fact(PHASE_MOVEMENT_FACT, _ordered_phase_payload(movement_payload), f"{location} row {row_index}", 0.9))
    return facts


def extract_use_of_stages_facts(table: list[list[str | None]], location: str) -> list[dict[str, Any]]:
    rows = [_clean_row(row) for row in table or []]
    if len(rows) < 3 or "use of stages" not in _table_text(rows[:2]).lower():
        return []
    header = rows[1]
    if not header or header[0].lower() != "stage":
        return []
    phase_columns = [(index, value.upper()) for index, value in enumerate(header[1:], start=1)
                     if re.fullmatch(r"[A-Z](?:\d+)?", value.upper())]
    facts: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows[2:], start=3):
        if not row or not re.fullmatch(r"\d+", row[0]):
            continue
        stage_number = int(row[0])
        if stage_number == 0:
            continue
        phase_labels = [
            phase_label
            for index, phase_label in phase_columns
            if index < len(row) and _stage_cell_is_active(row[index])
        ]
        if not phase_labels:
            continue
        payload = {
            "stage_ref": f"stage_{stage_number}",
            "stage_number": stage_number,
            "phase_refs": [_phase_ref(label) for label in phase_labels],
            "phase_labels": phase_labels,
        }
        facts.append(make_fact("stage_phase_relationship_from_controller_config", payload, f"{location} row {row_index}", 0.88))
    return facts


def extract_utc_form_movement_facts(tables: list[list[list[str]]]) -> list[dict[str, Any]]:
    link_movements: dict[str, dict[str, Any]] = {}
    facts: list[dict[str, Any]] = []

    for table_index, rows in enumerate(tables, start=1):
        if not rows:
            continue
        header = [_normalise_header(cell) for cell in rows[0]]
        if _is_link_description_table(header):
            for row_index, row in enumerate(rows[1:], start=2):
                fact = _link_movement_fact(row, table_index, row_index)
                if fact is None:
                    continue
                payload = fact["payload"]["value"]
                link_movements[payload["scoot_link_ref"]] = payload
                facts.append(fact)

    for table_index, rows in enumerate(tables, start=1):
        if not rows:
            continue
        header = [_normalise_header(cell) for cell in rows[0]]
        if _is_phase_link_table(header):
            for row_index, row in enumerate(rows[1:], start=2):
                fact = _phase_link_fact(row, table_index, row_index, link_movements)
                if fact is not None:
                    facts.append(fact)
        elif _is_link_stage_table(header):
            for row_index, row in enumerate(rows[1:], start=2):
                fact = _link_stage_fact(row, table_index, row_index)
                if fact is not None:
                    facts.append(fact)
    return facts


def _link_movement_fact(row: list[str], table_index: int, row_index: int) -> dict[str, Any] | None:
    if len(row) < 2:
        return None
    scn = row[0].strip()
    description = row[1].strip()
    if not scn or not description:
        return None
    link_ref = _link_ref_from_scn(scn)
    if link_ref is None:
        return None
    movement_text = description.split(":", 1)[-1].strip()
    payload = _movement_payload(movement_text)
    payload.update({"scoot_link_ref": link_ref, "scn": scn})
    return make_fact(SCOOT_LINK_MOVEMENT_FACT, _ordered_link_payload(payload), f"table {table_index} row {row_index}", 0.88)


def _phase_link_fact(
    row: list[str],
    table_index: int,
    row_index: int,
    link_movements: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if len(row) < 2:
        return None
    phase_label = row[0].strip().upper()
    if not re.fullmatch(r"[A-Z]", phase_label):
        return None
    link_refs = [_clean_link_ref(part) for part in re.split(r"[/, ]+", row[1]) if _clean_link_ref(part)]
    if not link_refs:
        return None
    primary_link = link_refs[0]
    payload: dict[str, Any] = {
        "phase_ref": _phase_ref(phase_label),
        "phase_label": phase_label,
        "scoot_link_ref": primary_link,
    }
    if len(link_refs) > 1:
        payload["scoot_link_refs"] = link_refs
    if primary_link in link_movements:
        payload["movement_ref"] = link_movements[primary_link]["movement_ref"]
    if len(row) >= 3:
        payload["value_in_spec"] = _int_or_text(row[2])
    if len(row) >= 4:
        payload["slag"] = _int_or_text(row[3])
    if len(row) >= 5:
        payload["elag"] = _int_or_text(row[4])
    return make_fact(PHASE_SCOOT_LINK_FACT, payload, f"table {table_index} row {row_index}", 0.88)


def _link_stage_fact(row: list[str], table_index: int, row_index: int) -> dict[str, Any] | None:
    if len(row) < 7:
        return None
    link_ref = _clean_link_ref(row[0])
    if not link_ref:
        return None
    stage_numbers = [int(value) for value in re.findall(r"\d+", row[6])]
    if not stage_numbers:
        return None
    payload = {
        "scoot_link_ref": link_ref,
        "stage_refs": [f"stage_{number}" for number in stage_numbers],
        "stage_numbers": stage_numbers,
        "junction_scn": row[5].strip(),
    }
    return make_fact(SCOOT_LINK_STAGE_FACT, payload, f"table {table_index} row {row_index}", 0.88)


def _movement_payload(movement_text: str) -> dict[str, Any]:
    road_name, direction, maneuver = _split_movement_text(movement_text)
    return {
        "movement_ref": "movement_" + _slug(movement_text),
        "movement_text": _display_movement_text(movement_text),
        "road_name": road_name,
        "direction": direction,
        "maneuver": maneuver,
    }


def _split_movement_text(movement_text: str) -> tuple[str, str | None, str | None]:
    tokens = movement_text.split()
    direction_index = next((i for i, token in enumerate(tokens) if _direction_token(token)), None)
    if direction_index is None:
        return _title(movement_text), None, None
    road_name = _title(" ".join(tokens[:direction_index]))
    direction = _direction_token(tokens[direction_index])
    tail = " ".join(tokens[direction_index + 1 :]).lower()
    maneuver = _maneuver(tail)
    return road_name, direction, maneuver


def _direction_token(token: str) -> str | None:
    mapping = {
        "inbound": "inbound",
        "outbound": "outbound",
        "northbound": "northbound",
        "southbound": "southbound",
        "eastbound": "eastbound",
        "westbound": "westbound",
        "nb": "NB",
        "sb": "SB",
        "eb": "EB",
        "wb": "WB",
    }
    return mapping.get(token.lower())


def _maneuver(text: str) -> str | None:
    if "right" in text or re.search(r"\brt\b", text):
        return "right_turn"
    if "left" in text or re.search(r"\blft\b", text):
        return "left_turn"
    if "ahead" in text:
        return "ahead"
    if "stopline" in text or "stop line" in text:
        return "stopline"
    return None


def _display_movement_text(value: str) -> str:
    if value.isupper():
        return value
    return _clean_spaces(value)


def _ordered_phase_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "phase_ref": payload["phase_ref"],
        "phase_label": payload["phase_label"],
        "movement_ref": payload["movement_ref"],
        "movement_text": payload["movement_text"],
        "road_name": payload["road_name"],
        "direction": payload["direction"],
        "maneuver": payload["maneuver"],
    }


def _ordered_link_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "scoot_link_ref": payload["scoot_link_ref"],
        "scn": payload["scn"],
        "movement_ref": payload["movement_ref"],
        "movement_text": payload["movement_text"],
        "road_name": payload["road_name"],
        "direction": payload["direction"],
        "maneuver": payload["maneuver"],
    }


def _is_link_description_table(header: list[str]) -> bool:
    return len(header) >= 2 and header[0] == "link scn" and header[1] == "link description"


def _is_phase_link_table(header: list[str]) -> bool:
    return len(header) >= 2 and header[0] == "controller phase letter" and header[1] == "scoot link letter"


def _is_link_stage_table(header: list[str]) -> bool:
    return "link letter" in header[:1] and any("utc green stage" in item for item in header)


def _link_ref_from_scn(scn: str) -> str | None:
    match = re.search(r"([A-Z])\d*$", scn.strip(), flags=re.IGNORECASE)
    return match.group(1).upper() if match else None


def _clean_link_ref(value: str) -> str | None:
    text = value.strip().upper()
    return text if re.fullmatch(r"[A-Z]", text) else None


def _phase_ref(value: str) -> str:
    return "phase_" + value.upper()


def _normalise_header(value: str) -> str:
    return _clean_spaces(value).lower()


def _clean_spaces(value: str) -> str:
    return " ".join(str(value).split())


def _title(value: str) -> str:
    return " ".join(word.capitalize() for word in _clean_spaces(value).split())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _int_or_text(value: str) -> int | str:
    text = value.strip()
    return int(text) if re.fullmatch(r"[+-]?\d+", text) else text


def _clean_row(row: list[str | None]) -> list[str]:
    return [_clean_spaces(cell or "") for cell in row]


def _table_text(rows: list[list[str]]) -> str:
    return " ".join(cell for row in rows for cell in row if cell)


def _phase_type_index(row: list[str]) -> int | None:
    for index, cell in enumerate(row[1:], start=1):
        if cell.upper() in PHASE_TYPES:
            return index
    return None


def _clean_movement_description(cells: list[str]) -> str:
    parts = []
    for cell in cells:
        text = _clean_spaces(cell)
        if not text or re.fullmatch(r"\d+", text):
            continue
        parts.append(text)
    return _clean_spaces(" ".join(parts))


def _stage_cell_is_active(value: str) -> bool:
    text = _clean_spaces(value).upper()
    return bool(text) and text not in {"0", "-", "X"}
