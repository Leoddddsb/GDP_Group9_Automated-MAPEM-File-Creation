import json
import re
from collections.abc import Mapping

try:
    from .json_mapem import generate_json_mapem
except ImportError:
    from json_mapem import generate_json_mapem


IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")
BIT_STRING_FIELDS = {"directionalUse", "sharedWith", "attributes", "maneuver"}
BINARY_STRING = re.compile(r"^[01]+$")


def generate_asn1_mapem(source):
    model = generate_json_mapem(source)
    sections = []

    if model.get("header"):
        sections.append(f"ItsPduHeader ::= {_format_value(model['header'], 0)}")

    sections.append(f"MapData ::= {_format_value(model['mapData'], 0)}")
    return "\n\n".join(sections) + "\n"


def _format_value(value, indent, field_name=None):
    if isinstance(value, Mapping):
        return _format_mapping(value, indent)
    if isinstance(value, list):
        return _format_list(value, indent)
    return _format_scalar(value, field_name)


def _format_mapping(value, indent):
    if not value:
        return "{ }"

    child_indent = indent + 2
    lines = []
    items = list(value.items())

    for index, (key, item) in enumerate(items):
        line = f"{' ' * child_indent}{key} {_format_value(item, child_indent, key)}"
        if index < len(items) - 1:
            line += ","
        lines.append(line)

    return "{\n" + "\n".join(lines) + f"\n{' ' * indent}" + "}"


def _format_list(value, indent):
    if not value:
        return "{ }"

    if all(not isinstance(item, (Mapping, list)) for item in value):
        return "{ " + ", ".join(_format_scalar(item) for item in value) + " }"

    child_indent = indent + 2
    lines = []

    for index, item in enumerate(value):
        line = f"{' ' * child_indent}{_format_value(item, child_indent)}"
        if index < len(value) - 1:
            line += ","
        lines.append(line)

    return "{\n" + "\n".join(lines) + f"\n{' ' * indent}" + "}"


def _format_scalar(value, field_name=None):
    if value is None:
        return "NULL -- unresolved"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if field_name in BIT_STRING_FIELDS and BINARY_STRING.fullmatch(value):
            return f"'{value}'B"
        if IDENTIFIER.fullmatch(value):
            return value
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)
