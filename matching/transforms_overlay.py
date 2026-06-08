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
