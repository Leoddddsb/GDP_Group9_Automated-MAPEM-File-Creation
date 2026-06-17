"""
MAPEM semantic-value -> bit-string encoder
==========================================

Stage 5 (encoding) of the Automated MAPEM pipeline. Takes the fused_model.json
produced by matching/fusion (which holds human-readable SEMANTIC values such as
"both", "vehicle", ['busVehicleTraffic']) and encodes every element into the
exact on-the-wire representation required by the C-Roads MAPEM/SPATEM 3.2.0
handbook.

Design rules
------------
* EVERY element produced by matching/fusion is handled here — none skipped.
* Bit strings follow the C-Roads handbook bit positions exactly (see citations
  in each encoder). Bit position N means "set the Nth bit, MSB-or-LSB per the
  output convention chosen below".
* Output convention for bit strings: a fixed-width string of '0'/'1' characters,
  index 0 = bit 0 (as the handbook numbers them). e.g. directionalUse "both"
  -> bit0=ingress, bit1=egress -> "11". This matches how ASN.1 UPER BIT STRING
  is conventionally written left-to-right from bit 0. If your serialiser needs
  the reverse order or an integer, switch via BITSTRING_AS_INT / REVERSE_BITS.
* null / None values pass through unchanged (a gap stays a gap; encoding never
  invents data).
* Unknown / unexpected values are NOT silently coerced — they raise EncodeError
  so a bad upstream value is caught, not hidden.

C-Roads 3.2.0 handbook references:
  §3.3.2.1 LaneType        (bit-string choice; normal lane = all 0)
  §3.3.2.2 sharedWith      (bit positions 0,2,3,4,5,6,7,8; 1 & 9 never set)
  §3.3.2.3 directionalUse  (2-bit: ingressPath(0), egressPath(1))
  §3.3.3   maneuvers       (lane-level: PROHIBITED — must not appear)
  §3.3.5.1 connectingLane.maneuver  (DE_AllowedManeuvers, SAE J2735 12-bit)
"""

from __future__ import annotations
import copy
from typing import Any


class EncodeError(ValueError):
    """Raised when a semantic value cannot be mapped to a valid bit string."""


# ---------------------------------------------------------------------------
# Output conventions (flip these if your serialiser expects something else)
# ---------------------------------------------------------------------------
BITSTRING_AS_INT = False     # True -> return integer; False -> return '0/1' string
REVERSE_BITS = False         # True -> MSB-first; False -> bit0 at string index 0


def _bits_to_output(bit_positions: set[int], width: int):
    """Turn a set of set-bit positions into the configured output form."""
    arr = ["0"] * width
    for b in bit_positions:
        if b < 0 or b >= width:
            raise EncodeError(f"bit position {b} out of range for width {width}")
        arr[b] = "1"
    if REVERSE_BITS:
        arr = arr[::-1]
    s = "".join(arr)
    if BITSTRING_AS_INT:
        # interpret with bit0 as least-significant
        return int(s[::-1] if not REVERSE_BITS else s, 2)
    return s


# ===========================================================================
# §3.3.2.3 directionalUse — 2-bit string: ingressPath(0), egressPath(1)
# ===========================================================================
def encode_directional_use(value: Any):
    """
    Semantic -> 2-bit string.
      "ingress" / "ingressPath" -> bit0           -> "10"
      "egress"  / "egressPath"  -> bit1           -> "01"
      "both" / "bidirectional"  -> bit0 & bit1    -> "11"
      "none" / "median" / "curb"-> neither        -> "00"
    Per handbook: bidirectional sets both; non-travel lanes set none.
    """
    if value is None:
        return None
    v = str(value).strip().lower()
    bits: set[int] = set()
    if v in ("both", "bidirectional", "bidirectionaluse", "ingress_egress"):
        bits = {0, 1}
    elif v in ("ingress", "ingresspath", "in"):
        bits = {0}
    elif v in ("egress", "egresspath", "out"):
        bits = {1}
    elif v in ("none", "median", "medianlane", "curb", "kerb", "no_travel", ""):
        bits = set()
    else:
        raise EncodeError(f"directionalUse: unknown value {value!r}")
    return _bits_to_output(bits, 2)


# ===========================================================================
# §3.3.2.2 sharedWith — bit string. Not shared => all 0.
#   overlappingLaneDescriptionProvided(0), otherNonMotorizedTrafficTypes(2),
#   individualMotorizedVehicleTraffic(3), busVehicleTraffic(4),
#   taxiVehicleTraffic(5), pedestriansTraffic(6), cyclistVehicleTraffic(7),
#   trackedVehicleTraffic(8).  Bits 1 & 9 SHALL NEVER be set.
# ===========================================================================
SHARED_WITH_BITS = {
    "overlappinglanedescriptionprovided": 0,
    "othernonmotorizedtraffictypes": 2,
    "individualmotorizedvehicletraffic": 3,
    "busvehicletraffic": 4,
    "taxivehicletraffic": 5,
    "pedestrianstraffic": 6,
    "cyclistvehicletraffic": 7,
    "trackedvehicletraffic": 8,
}
SHARED_WITH_WIDTH = 10           # bits 0..9 exist; 1 & 9 simply never set
_FORBIDDEN_SHARED_BITS = {1, 9}  # multipleLanesTreatedAsOneLane, pedestrianTraffic


def encode_shared_with(value: Any):
    """
    Semantic list -> sharedWith bit string.
      []                          -> "0000000000"  (not shared — the common case)
      ['busVehicleTraffic']       -> bit4 set
      ['busVehicleTraffic','cyclistVehicleTraffic'] -> bits 4 & 7
    Enforces the C-Roads rule that bits 1 and 9 are never set.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = [value] if value else []
    if not isinstance(value, (list, tuple, set)):
        raise EncodeError(f"sharedWith: expected list, got {type(value).__name__}")
    bits: set[int] = set()
    for item in value:
        key = str(item).strip().lower()
        if key not in SHARED_WITH_BITS:
            raise EncodeError(f"sharedWith: unknown user type {item!r}")
        b = SHARED_WITH_BITS[key]
        if b in _FORBIDDEN_SHARED_BITS:
            raise EncodeError(f"sharedWith: bit {b} must never be set (C-Roads)")
        bits.add(b)
    return _bits_to_output(bits, SHARED_WITH_WIDTH)


# ===========================================================================
# §3.3.2.1 laneType — bit-string CHOICE. The CHOICE selects which lane-type
# variant; within each variant the bit string details extra characteristics.
# For a normal lane with no special characteristics, the inner bit string is
# all 0. We emit the C-Roads structure: {choice: <type>, bits: <all-0 string>}.
# Width 16 covers the LaneAttributes-* bit strings; normal lane = all 0.
# ===========================================================================
LANE_TYPE_CHOICES = {
    "vehicle": "vehicle",
    "vehiclelane": "vehicle",
    "vehicle lane": "vehicle",
    "crosswalklane": "crosswalk",
    "crosswalk": "crosswalk",
    "bikelane": "bikeLane",
    "bike": "bikeLane",
    "sidewalk": "sidewalk",
    "medianlane": "median",
    "median": "median",
    "trackedvehicle": "trackedVehicle",
    "tracked": "trackedVehicle",
}
LANE_TYPE_INNER_WIDTH = 16        # LaneAttributes-* bit string; normal = all 0


def encode_lane_type(value: Any):
    """
    Semantic -> {'choice': <c-roads type>, 'attributes': <bit string all 0>}.
      "vehicle"      -> choice 'vehicle',      attributes all 0
      "crosswalkLane"-> choice 'crosswalk',    attributes all 0
      ...
    Per handbook §3.3.2.1: normal lanes set none of the inner bits.
    """
    if value is None:
        return None
    key = str(value).strip().lower()
    if key not in LANE_TYPE_CHOICES:
        raise EncodeError(f"laneType: unknown value {value!r}")
    choice = LANE_TYPE_CHOICES[key]
    return {
        "choice": choice,
        "attributes": _bits_to_output(set(), LANE_TYPE_INNER_WIDTH),
    }


# ===========================================================================
# §3.3.5.1 connectingLane.maneuver — DE_AllowedManeuvers (SAE J2735), 12-bit.
#   maneuverStraightAllowed(0), maneuverLeftAllowed(1), maneuverRightAllowed(2),
#   maneuverUTurnAllowed(3), maneuverLeftTurnOnRedAllowed(4),
#   maneuverRightTurnOnRedAllowed(5), maneuverLaneChangeAllowed(6),
#   maneuverNoStoppingAllowed(7), yieldAllwaysRequired(8),
#   goWithHalt(9), caution(10), reserved1(11)
# ===========================================================================
ALLOWED_MANEUVER_BITS = {
    "maneuverstraightallowed": 0, "straight": 0, "through": 0,
    "maneuverleftallowed": 1, "left": 1,
    "maneuverrightallowed": 2, "right": 2,
    "maneuveruturnallowed": 3, "uturn": 3, "u-turn": 3,
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
    """
    Semantic -> 12-bit AllowedManeuvers string.
      "straight"            -> bit0
      ["left","straight"]   -> bits 0 & 1
      None                  -> None (unknown manoeuvre stays a gap)
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        raise EncodeError(f"maneuver: expected list/str, got {type(value).__name__}")
    bits: set[int] = set()
    for item in value:
        key = str(item).strip().lower().replace(" ", "")
        if key not in ALLOWED_MANEUVER_BITS:
            raise EncodeError(f"maneuver: unknown value {item!r}")
        bits.add(ALLOWED_MANEUVER_BITS[key])
    return _bits_to_output(bits, MANEUVER_WIDTH)


# ===========================================================================
# Pass-through elements: already in correct on-the-wire form, no bit-string
# encoding needed. Listed explicitly so NOTHING is silently ignored.
# ===========================================================================
#  header.protocolVersion / messageID / stationID  -> integers, as-is
#  mapData.msgIssueRevision                         -> integer
#  id.region / id.id                                -> integers
#  revision                                         -> integer
#  refPoint.lat / refPoint.long                     -> int (deg x 1e7), as-is
#  laneWidth                                        -> int (cm), as-is
#  laneID                                           -> integer
#  ingressApproach / egressApproach                 -> integer (approach id)
#  nodeList.nodes[].delta                           -> offset structure, as-is
#  connectsTo[].connectingLane.lane                 -> integer (lane id)
#  connectsTo[].signalGroup                         -> integer
#  signalHeadLocations[].nodeXY                     -> offset structure, as-is
#  mapData.intersections / connectsTo               -> containers
#  laneSet[].maneuvers (lane-level)                 -> PROHIBITED (must be absent)


# ===========================================================================
# Whole-model encoder: walk fused_model.json and encode every bit-string field.
# ===========================================================================
def encode_model(fused_model: dict) -> dict:
    """
    Take a fused_model (semantic values) and return a copy with all bit-string
    fields encoded to C-Roads form. Pass-through fields are left untouched.
    null values stay null. Raises EncodeError on an invalid semantic value.
    """
    model = copy.deepcopy(fused_model)
    mapdata = model.get("mapData") or {}
    for inter in (mapdata.get("intersections") or []):
        # guard: lane-level 'maneuvers' is prohibited (§3.3.3)
        for lane in (inter.get("laneSet") or []):
            if "maneuvers" in lane:
                raise EncodeError(
                    "laneSet[].maneuvers is prohibited by C-Roads; "
                    "use connectsTo.connectingLane.maneuver instead")
            attrs = lane.get("laneAttributes") or {}
            if "directionalUse" in attrs:
                attrs["directionalUse"] = encode_directional_use(attrs["directionalUse"])
            if "sharedWith" in attrs:
                attrs["sharedWith"] = encode_shared_with(attrs["sharedWith"])
            if "laneType" in attrs:
                attrs["laneType"] = encode_lane_type(attrs["laneType"])
            for conn in (lane.get("connectsTo") or []):
                cl = conn.get("connectingLane") or {}
                if "maneuver" in cl:
                    cl["maneuver"] = encode_maneuver(cl["maneuver"])
    return model


# ===========================================================================
# CLI
# ===========================================================================
if __name__ == "__main__":
    import argparse, json, sys
    ap = argparse.ArgumentParser(description="Encode MAPEM semantic values -> bit strings")
    ap.add_argument("--model", required=True, help="fused_model.json (semantic)")
    ap.add_argument("--out", required=True, help="output encoded model json")
    ap.add_argument("--as-int", action="store_true", help="emit bit strings as integers")
    ap.add_argument("--msb-first", action="store_true", help="reverse bit order (MSB first)")
    args = ap.parse_args()

    if args.as_int:
        BITSTRING_AS_INT = True
    if args.msb_first:
        REVERSE_BITS = True

    with open(args.model) as f:
        fm = json.load(f)
    try:
        encoded = encode_model(fm)
    except EncodeError as e:
        print(f"[encode error] {e}", file=sys.stderr)
        sys.exit(1)
    with open(args.out, "w") as f:
        json.dump(encoded, f, ensure_ascii=False, indent=2)
    print(f"[ok] wrote {args.out}")
