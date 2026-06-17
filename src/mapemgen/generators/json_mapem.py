from collections.abc import Mapping
from copy import deepcopy
from typing import Any

try:
    from .encode_bitstrings import encode_model
except ImportError:
    from encode_bitstrings import encode_model


def generate_json_mapem(source):
    raw = _as_mapping(source)
    if "mapData" not in raw:
        raise ValueError("input must contain mapData")

    output = {}
    if "header" in raw:
        output["header"] = _normalise_value(raw["header"])
    output["mapData"] = _normalise_value(raw["mapData"])

    _remove_lane_level_maneuvers(output)
    return encode_model(output)


def _as_mapping(source):
    if isinstance(source, Mapping):
        return source
    if hasattr(source, "as_dict"):
        return source.as_dict()
    raise TypeError("input must be a dict-like object or have as_dict()")


def _normalise_value(value):
    if isinstance(value, Mapping):
        return _normalise_mapping(value)
    if isinstance(value, list):
        return [_normalise_value(item) for item in value]
    return deepcopy(value)


def _normalise_mapping(value):
    result = {}
    has_long = "long" in value

    for key, item in value.items():
        if key == "lon":
            if has_long:
                continue
            result["long"] = _normalise_value(item)
        else:
            result[str(key)] = _normalise_value(item)

    return result


def _remove_lane_level_maneuvers(model: dict[str, Any]) -> None:
    map_data = model.get("mapData") or {}
    for intersection in map_data.get("intersections") or []:
        for lane in intersection.get("laneSet") or []:
            lane.pop("maneuvers", None)
