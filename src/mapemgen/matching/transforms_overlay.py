"""
transforms_overlay.py
=====================
Wraps the teammate's transforms.py WITHOUT editing it. It re-exports everything,
then (a) implements functions the teammate left as stubs, (b) adds small helpers
the matching engine needs, and (c) extends the TRANSFORMS registry.

The engine loads THIS module (it exposes a TRANSFORMS dict just like transforms.py).
When the teammate updates transforms.py, these overrides still apply on top.

Sync note: the implementations below (resolve_egress_lane_from_stage, the approach
lookups) are integration additions — share them with the transforms author so they
can fold them back into transforms.py if desired.
"""
from typing import Any, Mapping, Sequence

import transforms as _base
from transforms import *  # noqa: F401,F403  (re-export teammate's functions)

# start from the teammate's registry, then override/extend
TRANSFORMS = dict(getattr(_base, "TRANSFORMS", {}))


# ---------------------------------------------------------------------------
# (B3 fix) resolve_egress_lane_from_stage — was a stub returning None.
# A stage row alone cannot name a target lane, but lane geometry can: we pair
# each ingress lane to its nearest egress lane by geometry (the teammate already
# implemented pair_ingress_egress_by_geometry). This resolves connectingLane.lane.
# ---------------------------------------------------------------------------
def resolve_egress_lane_from_stage(value: Any,
                                   scope: Mapping[str, Any] | None = None,
                                   resolved: Mapping[str, Any] | None = None,
                                   **_ignore: Any):
    """Resolve the target (egress) lane id for a connection.

    Strategy: use the precomputed geometry pairing in resolved['lane_pairs']
    (built by the engine prepass via pair_ingress_egress_by_geometry), keyed by
    the current ingress lane (scope['lane']). Returns the target lane id, or None
    if no confident geometric match exists (→ engine marks manual_review).
    """
    pairs = (resolved or {}).get("lane_pairs", {})
    lane = (scope or {}).get("lane")
    if lane is not None and lane in pairs:
        return pairs[lane].get("target_lane_id")
    # fallback: value may already carry an explicit target lane id
    if isinstance(value, Mapping):
        return value.get("target_lane_id") or value.get("connecting_lane")
    if isinstance(value, int):
        return value
    return None


# ---------------------------------------------------------------------------
# (B2 fix) approach-id lookups — ingress/egress approach is a CROSS-LANE result
# (lanes are clustered by bearing around the junction). The engine prepass runs
# the clustering once and stores per-lane results in resolved['approach']; these
# transforms just read the right one for the current lane (scope['lane']).
# ---------------------------------------------------------------------------
def _approach_for(scope, resolved, want_dir):
    appr = (resolved or {}).get("approach", {})
    lane = (scope or {}).get("lane")
    info = appr.get(lane)
    if not info or info.get("dir") != want_dir:
        return None
    return assign_approach_id(info["id"])  # noqa: F405 (from teammate via *)


def ingress_approach_id(value: Any, scope=None, resolved=None, **_ignore):
    return _approach_for(scope, resolved, "ingress")


def egress_approach_id(value: Any, scope=None, resolved=None, **_ignore):
    return _approach_for(scope, resolved, "egress")


# ---------------------------------------------------------------------------
# Small extractors for the payload contract (see payload_contract.md).
# Let a pipeline pull the geometry list out of a wrapper payload dict.
# ---------------------------------------------------------------------------
def take_polyline(value: Any, **_ignore):
    """Return a list of points from a payload that may wrap geometry."""
    if isinstance(value, Mapping):
        for k in ("polyline", "vertices", "points", "geometry"):
            if k in value:
                return value[k]
    return value


def take_label(value: Any, **_ignore):
    """Return the label string from a payload that may wrap it."""
    if isinstance(value, Mapping):
        for k in ("label", "text", "value", "phase_label", "phase_letter"):
            if k in value:
                return value[k]
    return value


TRANSFORMS.update({
    "resolve_egress_lane_from_stage": resolve_egress_lane_from_stage,
    "ingress_approach_id": ingress_approach_id,
    "egress_approach_id": egress_approach_id,
    "take_polyline": take_polyline,
    "take_label": take_label,
})


# ---------------------------------------------------------------------------
# (v3 rules) Names referenced by matching_rules v3 that map onto existing
# functions, plus two small new ones. Direct references preserve each function's
# signature, so the engine's signature-aware runner still passes the right
# context kwargs (dummy_phase_set, phase_order, output, ref_point).
# ---------------------------------------------------------------------------

# 1. extract_int_from_identifier  (site/scn/intersection identifier -> int)
extract_int_from_identifier = extract_int_from_site_code          # noqa: F405

# 2. phase_label_to_signal_group  (== existing phase_letter_to_signal_group)
phase_label_to_signal_group = phase_letter_to_signal_group        # noqa: F405

# 3. phase_type_to_lane_type  (== existing phase_type_to_lanetype)
phase_type_to_lane_type = phase_type_to_lanetype                  # noqa: F405

# 4. layer_or_marking_to_lane_type  (general label/layer/marking -> lane type)
layer_or_marking_to_lane_type = lane_type_from_label             # noqa: F405


# 5. geometry_bounds_centre  (coordinate_bounds -> Point at the centre)
def geometry_bounds_centre(value, **_ignore):
    """Centre of a bounding box. Accepts {min_x,min_y,max_x,max_y} / {minx,...},
    a 4-tuple (minx,miny,maxx,maxy), or [[minx,miny],[maxx,maxy]]."""
    v = value
    if isinstance(v, Mapping):
        if "value" in v and not any(k in v for k in ("min_x", "minx", "bounds")):
            v = v["value"]
    if isinstance(v, Mapping):
        b = v.get("bounds", v)
        if isinstance(b, Mapping):
            minx = b.get("min_x", b.get("minx", b.get("xmin")))
            miny = b.get("min_y", b.get("miny", b.get("ymin")))
            maxx = b.get("max_x", b.get("maxx", b.get("xmax")))
            maxy = b.get("max_y", b.get("maxy", b.get("ymax")))
            return ((minx + maxx) / 2.0, (miny + maxy) / 2.0)
        v = b
    if isinstance(v, Sequence) and len(v) == 4 and all(
            isinstance(x, (int, float)) for x in v):
        minx, miny, maxx, maxy = v
        return ((minx + maxx) / 2.0, (miny + maxy) / 2.0)
    if isinstance(v, Sequence) and len(v) == 2:        # [[minx,miny],[maxx,maxy]]
        (minx, miny), (maxx, maxy) = v[0], v[1]
        return ((minx + maxx) / 2.0, (miny + maxy) / 2.0)
    raise TransformError(f"Cannot read coordinate_bounds from: {value!r}")  # noqa: F405


# 6. infer_lane_direction  (lane geometry + refPoint -> ingress|egress|both)
def infer_lane_direction(value, ref_point=None, **_ignore):
    """Classify a lane as ingress/egress relative to the reference point.
    Needs ref_point in the SAME CRS as the lane geometry; if absent or
    indeterminate, returns 'both' (safe default)."""
    poly = take_polyline(value)
    if ref_point is None or not isinstance(poly, (list, tuple)) or len(poly) < 2:
        return "both"
    try:
        d = direction_relative_to_refpoint(poly, ref_point)   # noqa: F405
    except Exception:
        return "both"
    return d if d in ("ingress", "egress") else "both"


# 7. marking_to_shared_with  (road-marking / lane-use label -> sharedWith bits)
# C-Roads 3.2.0 sharedWith bit positions (section 3.3.2.2). A lane that is NOT
# shared with other specific road users leaves the bit string all-0 (= []).
# Only the bits below may be used per the C-Roads profile; bits 1
# (multipleLanesTreatedAsOneLane) and 9 (pedestrianTraffic) shall NEVER be set.
SHARED_WITH_BITS = {
    "overlappingLaneDescriptionProvided": 0,
    "otherNonMotorizedTrafficTypes": 2,
    "individualMotorizedVehicleTraffic": 3,
    "busVehicleTraffic": 4,
    "taxiVehicleTraffic": 5,
    "pedestriansTraffic": 6,
    "cyclistVehicleTraffic": 7,
    "trackedVehicleTraffic": 8,
}

# keyword (lower-case, matched as substring) -> sharedWith user type
_SHARED_WITH_KEYWORDS = [
    ("bus", "busVehicleTraffic"),
    ("taxi", "taxiVehicleTraffic"),
    ("cycle", "cyclistVehicleTraffic"),
    ("bike", "cyclistVehicleTraffic"),
    ("cyclist", "cyclistVehicleTraffic"),
    ("pedestrian", "pedestriansTraffic"),
    ("foot", "pedestriansTraffic"),
    ("tram", "trackedVehicleTraffic"),
    ("rail", "trackedVehicleTraffic"),
    ("lrt", "trackedVehicleTraffic"),
    ("light rail", "trackedVehicleTraffic"),
]


def marking_to_shared_with(value, **_ignore):
    """Road-marking / lane-use label -> sharedWith user-type list.

    Returns a list of shared-with user-type names (e.g. ['busVehicleTraffic']).
    An empty list means the lane is not shared with any special road user
    (the bit string stays all-0), which is the correct C-Roads representation
    for an ordinary lane. The encoding stage turns this list into the bit
    string. This NEVER returns a laneType value (that was the previous bug).
    """
    # pull the raw text/label out of whatever shape the fact has
    text = value
    if isinstance(text, Mapping):
        text = (text.get("value") or text.get("label") or text.get("text")
                or text.get("marking") or text.get("road_marking") or "")
    if isinstance(text, (list, tuple)):
        text = " ".join(str(t) for t in text)
    text = str(text or "").lower()

    found = []
    for keyword, user_type in _SHARED_WITH_KEYWORDS:
        if keyword in text and user_type not in found:
            found.append(user_type)
    return found            # [] when nothing matches -> all-0 bit string


TRANSFORMS.update({
    "extract_int_from_identifier": extract_int_from_identifier,
    "phase_label_to_signal_group": phase_label_to_signal_group,
    "phase_type_to_lane_type": phase_type_to_lane_type,
    "layer_or_marking_to_lane_type": layer_or_marking_to_lane_type,
    "geometry_bounds_centre": geometry_bounds_centre,
    "infer_lane_direction": infer_lane_direction,
    "marking_to_shared_with": marking_to_shared_with,
})


# ---------------------------------------------------------------------------
# (B1 helper) OSTN15 grid availability check — surfaces the silent-degradation.
# ---------------------------------------------------------------------------
def ostn15_grid_available() -> bool:
    """True if pyproj can use the high-accuracy OSTN15 grid for 27700→4326."""
    try:
        from pyproj.transformer import TransformerGroup
        g = TransformerGroup("EPSG:27700", "EPSG:4326")
        # if the best op needs a grid that's unavailable, it lands here
        return len(g.unavailable_operations) == 0
    except Exception:
        return False


# --- polyline_centroid override ---------------------------------------------
# The base polyline_centroid expects a bare list of points, but several CAD
# geometry facts wrap the points under payload["geometry"] (or "polyline" /
# "vertices" / "points"). When the whole payload Mapping is passed in, the base
# version iterates the dict KEYS (e.g. "layer") and tries to read coordinates
# from the string "Lines", raising "could not convert string to float: 'g'".
# This override unwraps the geometry first, so refPoint and other geometry
# fields work whether or not the points are wrapped.
def polyline_centroid(value, **_ignore):
    poly = take_polyline(value)
    pts = []
    for p in poly:
        try:
            pts.append(as_point(p))                       # noqa: F405
        except Exception:
            continue
    if not pts:
        raise TransformError("Cannot calculate centroid: no usable points.")  # noqa: F405
    return (sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts))


TRANSFORMS["polyline_centroid"] = polyline_centroid


# --- polygon_centroid override ----------------------------------------------
# Same payload-unwrap fix as polyline_centroid: the active transform pipeline
# (transform_pipelines.yaml) uses polygon_centroid for refPoint, and the base
# version also iterates payload KEYS when handed a wrapped {"geometry": [...]}
# payload, raising "could not convert string to float: 'g'". Unwrap first.
def polygon_centroid(value, **_ignore):
    poly = take_polyline(value)
    pts = []
    for p in poly:
        try:
            pts.append(as_point(p))                       # noqa: F405
        except Exception:
            continue
    if len(pts) < 3:
        return polyline_centroid(pts)                     # reuse fixed version
    # close the ring
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    area2 = cx = cy = 0.0
    for a, b in zip(pts, pts[1:]):
        cross = a[0]*b[1] - b[0]*a[1]
        area2 += cross
        cx += (a[0]+b[0])*cross
        cy += (a[1]+b[1])*cross
    if area2 == 0:
        return polyline_centroid(pts)                     # degenerate -> mean
    return (cx/(3*area2), cy/(3*area2))


TRANSFORMS["polygon_centroid"] = polygon_centroid
