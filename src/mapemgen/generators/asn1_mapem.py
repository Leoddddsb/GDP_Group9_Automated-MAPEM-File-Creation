from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from mapemgen.generators.json_mapem_new import MapemSource, generate_json_mapem


IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")


def generate_asn1_mapem(source: MapemSource) -> str:
    """Generate the project's ASN.1-style MAPEM text.

    This is a readable draft encoder for the project's MAPEM workflow, not a
    DER/UPER encoder. It accepts both legacy ``SiteModel`` objects and the newer
    ``fusion/fused_model.json`` dicts.
    """
    model = generate_json_mapem(source)
    sections: list[str] = []

    if header := model.get("header"):
        sections.append(f"ItsPduHeader ::= {_format_value(header, 0)}")

    sections.append(f"MapData ::= {_format_value(model['mapData'], 0)}")
    return "\n\n".join(sections) + "\n"


def _format_value(value: Any, indent: int) -> str:
    if isinstance(value, Mapping):
        return _format_mapping(value, indent)
    if isinstance(value, list):
        return _format_list(value, indent)
    return _format_scalar(value)


def _format_mapping(value: Mapping[str, Any], indent: int) -> str:
    if not value:
        return "{ }"

    child_indent = indent + 2
    lines: list[str] = []
    items = list(value.items())
    for index, (key, item) in enumerate(items):
        field = f"{' ' * child_indent}{key} {_format_value(item, child_indent)}"
        if index < len(items) - 1:
            field += ","
        lines.append(field)

    return "{\n" + "\n".join(lines) + f"\n{' ' * indent}" + "}"


def _format_list(value: list[Any], indent: int) -> str:
    if not value:
        return "{ }"

    if all(not isinstance(item, (Mapping, list)) for item in value):
        return "{ " + ", ".join(_format_scalar(item) for item in value) + " }"

    child_indent = indent + 2
    lines: list[str] = []
    for index, item in enumerate(value):
        entry = f"{' ' * child_indent}{_format_value(item, child_indent)}"
        if index < len(value) - 1:
            entry += ","
        lines.append(entry)
    return "{\n" + "\n".join(lines) + f"\n{' ' * indent}" + "}"


def _format_scalar(value: Any) -> str:
    if value is None:
        return "NULL -- unresolved"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if IDENTIFIER.fullmatch(value):
            return value
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)
