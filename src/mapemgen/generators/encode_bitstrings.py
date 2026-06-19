"""
MAPEM semantic-value to bit-string encoder.

The matching/fusion stages keep values readable, for example ``"vehicle"``,
``["pedestriansTraffic", "cyclistVehicleTraffic"]`` or ``"straight"``.  The
generator stage turns those semantic values into the C-Roads MAPEM bit-string
shape.
"""

from __future__ import annotations

import copy
from typing import Any


class EncodeError(ValueError):
    """Raised when a semantic value cannot be mapped to a valid bit string."""


BITSTRING_AS_INT = False
REVERSE_BITS = False


def _bits_to_output(bit_positions: set[int], width: int):
    arr = ["0"] * width
    for bit in bit_positions:
        if bit < 0 or bit >= width:
            raise EncodeError(f"bit position {bit} out of range for width {width}")
        arr[bit] = "1"
    if REVERSE_BITS:
        arr = arr[::-1]
    text = "".join(arr)
    if BITSTRING_AS_INT:
        return int(text[::-1] if not REVERSE_BITS else text, 2)
    return text


def _is_binary_string(value: Any, width: int | None = None) -> bool:
    return (
        isinstance(value, str)
        and set(value) <= {"0", "1"}
        and (width is None or len(value) == width)
    )


def encode_directional_use(value: Any):
    if value is None:
        return None
    if _is_binary_string(value, 2):
        return value
    text = str(value).strip().lower()
    if text in {"both", "bidirectional", "bidirectionaluse", "ingress_egress"}:
        return _bits_to_output({0, 1}, 2)
    if text in {"ingress", "ingresspath", "in"}:
        return _bits_to_output({0}, 2)
    if text in {"egress", "egresspath", "out"}:
        return _bits_to_output({1}, 2)
    if text in {"none", "median", "medianlane", "curb", "kerb", "no_travel", ""}:
        return _bits_to_output(set(), 2)
    raise EncodeError(f"directionalUse: unknown value {value!r}")


SHARED_WITH_BITS = {
    "overlappinglanedescriptionprovided": 0,
    "othernonmotorizedtraffictypes": 2,
    "individualmotorizedvehicletraffic": 3,
    "busvehicletraffic": 4,
    "taxivehicletraffic": 5,
    "pedestrianstraffic": 6,
    "pedestrian": 6,
    "pedestrians": 6,
    "cyclistvehicletraffic": 7,
    "cycle": 7,
    "cyclist": 7,
    "bicycle": 7,
    "bike": 7,
    "trackedvehicletraffic": 8,
}
SHARED_WITH_WIDTH = 10
_FORBIDDEN_SHARED_BITS = {1, 9}


def encode_shared_with(value: Any):
    if value is None:
        return None
    if _is_binary_string(value, SHARED_WITH_WIDTH):
        if any(value[bit] == "1" for bit in _FORBIDDEN_SHARED_BITS):
            raise EncodeError("sharedWith: C-Roads forbids bits 1 and 9")
        return value
    if isinstance(value, str):
        value = [value] if value else []
    if not isinstance(value, (list, tuple, set)):
        raise EncodeError(f"sharedWith: expected list, got {type(value).__name__}")
    if len(value) == 1 and _is_binary_string(next(iter(value)), SHARED_WITH_WIDTH):
        return encode_shared_with(next(iter(value)))
    bits: set[int] = set()
    for item in value:
        key = str(item).strip().lower().replace(" ", "")
        if key not in SHARED_WITH_BITS:
            raise EncodeError(f"sharedWith: unknown user type {item!r}")
        bit = SHARED_WITH_BITS[key]
        if bit in _FORBIDDEN_SHARED_BITS:
            raise EncodeError(f"sharedWith: bit {bit} must never be set")
        bits.add(bit)
    return _bits_to_output(bits, SHARED_WITH_WIDTH)


LANE_TYPE_CHOICES = {
    "vehicle": "vehicle",
    "vehiclelane": "vehicle",
    "vehiclelaneattributes": "vehicle",
    "vehicle lane": "vehicle",
    "crosswalk": "crosswalkLane",
    "crosswalklane": "crosswalkLane",
    "bikelane": "bikeLane",
    "bike": "bikeLane",
    "cycle": "bikeLane",
    "cyclelane": "bikeLane",
    "sidewalk": "sideWalk",
    "sidewalklane": "sideWalk",
    "sidewalk": "sideWalk",
    "median": "medianLane",
    "medianlane": "medianLane",
    "trackedvehicle": "trackedVehicle",
    "tracked": "trackedVehicle",
}
LANE_TYPE_INNER_WIDTH = 16


def encode_lane_type(value: Any):
    if value is None:
        return None
    if isinstance(value, dict):
        choice = value.get("choice")
        attrs = value.get("attributes", value.get("bits"))
        if attrs is None:
            attrs = _bits_to_output(set(), LANE_TYPE_INNER_WIDTH)
        elif not _is_binary_string(attrs, LANE_TYPE_INNER_WIDTH):
            raise EncodeError(f"laneType.attributes: expected {LANE_TYPE_INNER_WIDTH}-bit string")
        return {
            "choice": _normalise_lane_type_choice(choice),
            "attributes": attrs,
        }
    return {
        "choice": _normalise_lane_type_choice(value),
        "attributes": _bits_to_output(set(), LANE_TYPE_INNER_WIDTH),
    }


def _normalise_lane_type_choice(value: Any) -> str:
    key = str(value or "").strip().lower().replace("_", "").replace("-", "")
    if key not in LANE_TYPE_CHOICES:
        raise EncodeError(f"laneType: unknown value {value!r}")
    return LANE_TYPE_CHOICES[key]


ALLOWED_MANEUVER_BITS = {
    "maneuverstraightallowed": 0,
    "straight": 0,
    "through": 0,
    "ahead": 0,
    "crossing": 0,
    "maneuverleftallowed": 1,
    "left": 1,
    "leftturn": 1,
    "maneuverrightallowed": 2,
    "right": 2,
    "rightturn": 2,
    "maneuveruturnallowed": 3,
    "uturn": 3,
    "u-turn": 3,
    "maneuverleftturnonredallowed": 4,
    "maneuverrightturnonredallowed": 5,
    "maneuverlanechangeallowed": 6,
    "maneuvernostoppingallowed": 7,
    "yieldallwaysrequired": 8,
    "gowithhalt": 9,
    "caution": 10,
}
MANEUVER_WIDTH = 12


def encode_maneuver(value: Any):
    if value is None:
        return None
    if _is_binary_string(value, MANEUVER_WIDTH):
        return value
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        raise EncodeError(f"maneuver: expected list/str, got {type(value).__name__}")
    bits: set[int] = set()
    for item in value:
        key = str(item).strip().lower().replace(" ", "").replace("_", "")
        if key not in ALLOWED_MANEUVER_BITS:
            raise EncodeError(f"maneuver: unknown value {item!r}")
        bits.add(ALLOWED_MANEUVER_BITS[key])
    return _bits_to_output(bits, MANEUVER_WIDTH)


def encode_model(fused_model: dict) -> dict:
    model = copy.deepcopy(fused_model)
    map_data = model.get("mapData") or {}
    for intersection in map_data.get("intersections") or []:
        for lane in intersection.get("laneSet") or []:
            lane.pop("maneuvers", None)
            attrs = lane.get("laneAttributes") or {}
            if "directionalUse" in attrs:
                attrs["directionalUse"] = encode_directional_use(attrs["directionalUse"])
            if "sharedWith" in attrs:
                attrs["sharedWith"] = encode_shared_with(attrs["sharedWith"])
            if "laneType" in attrs:
                attrs["laneType"] = encode_lane_type(attrs["laneType"])
            for connection in lane.get("connectsTo") or []:
                connecting_lane = connection.get("connectingLane") or {}
                if "maneuver" in connecting_lane:
                    connecting_lane["maneuver"] = encode_maneuver(connecting_lane["maneuver"])
    return model
