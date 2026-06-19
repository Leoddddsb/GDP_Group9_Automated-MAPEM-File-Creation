"""
ingest_adapter.py
=================
Adapts the ingestion + geometry-assignment output into the flat
`{"facts": [...]}` shape the matching engine consumes.

It does four things (Step 1 — geometry-aware):
  1. Flatten facts out of `extracted_facts.source_files[].extracted_facts`.
  2. Unwrap each fact's data: payload {"value": X} -> payload usable by transforms.
     (Falls back to a top-level `value` if a parser still emits the old shape.)
  3. Convert float `confidence` -> "high"/"medium"/"low" (engine uses levels).
  4. Inject instance keys: for facts the geometry-assignment stage placed, copy
     target_scope.intersection_ref / lane_ref INTO the fact payload, where the
     engine's InstanceResolver looks (payload.intersection_ref / payload.lane_ref).

Step 2 (DONE): route non-geometry facts (phase / label) to a lane. Phase facts
can't carry lane_ref (assignment's internal id) but carry a movement_ref /
phase_ref. assignment emits `movement_lane_mappings`
({movement_ref, lane_ref, phase_refs[], requires_context_match, ...});
`build_movement_to_lane` indexes it by movement_ref AND phase_ref, and
`_inject_nongeometry_scope` resolves each phase fact's ref to a lane_ref.
requires_context_match mappings are injected but marked provisional. Facts with
no ref, or an unmapped one, stay intersection-scoped rather than guessed. An
explicit --movement-map file can override / fill gaps.

Usage:
    python ingest_adapter.py \
        --facts extracted_facts.partial.json \
        --assignments geometry_assignments.partial.json \
        --out facts.json
    # --assignments is optional; without it you get unwrap + confidence only.
"""
import argparse
import json
import math
import sys


# --- confidence float -> engine level ---------------------------------------
# Thresholds are deliberately simple and adjustable. The engine reasons in
# levels; the original float is preserved in payload["_confidence_score"] so the
# confidence workstream can still use the precise value later.
def confidence_to_level(c, high=0.8, medium=0.5):
    if isinstance(c, str):
        return c if c in ("high", "medium", "low") else "medium"
    try:
        c = float(c)
    except (TypeError, ValueError):
        return "medium"
    if c >= high:
        return "high"
    if c >= medium:
        return "medium"
    return "low"



# --- upstream fact-name aliases ---------------------------------------------
# The dictionary/matching rules expect certain fact names that upstream
# ingestion currently emits under a different name. This is a thin translation
# layer so existing upstream data is picked up WITHOUT changing ingestion or the
# dictionary. Only add an entry when it is genuinely the SAME thing under another
# name (verified against the ingestion source), never to force-fit unrelated
# facts. Each upstream name maps to ONE canonical name the rules expect.
#
# Verified against commit 64c14ec:
#   lane_centreline_candidate is the CAD lane-centreline geometry the rules look
#   for under lane_centreline_geometry_from_cad. The rules also reference
#   lane_centreline_nodes_from_cad for the node list; both are served by the same
#   upstream fact, so we map to the geometry name (the engine derives nodes from
#   the same geometry via transform).
FACT_NAME_ALIASES = {
    "lane_centreline_candidate": "lane_centreline_geometry_from_cad",
    "phase_candidate": "phase_label_from_controller_config",
    "control_candidate": "movement_phase_mapping_from_controller_config",
}


def _apply_alias(name):
    return FACT_NAME_ALIASES.get(name, name)


def _fact_name(fact):
    raw = fact.get("fact_name") or fact.get("fact_type") or ""
    return _apply_alias(raw)


def _site_id_fact(extracted):
    if not isinstance(extracted, dict):
        return None
    site_id = extracted.get("site_id")
    if not site_id:
        site = extracted.get("site") or {}
        if isinstance(site, dict):
            site_id = site.get("id") or site.get("site_id")
    if not site_id:
        return None
    return {
        "fact_id": "site_id_official_intersection_id",
        "fact_name": "official_intersection_id_from_cad",
        "payload": {"value": str(site_id)},
        "confidence": "high",
        "source_file": "site_id",
    }


# --- geometry shape normalisation (Plan B: unified payload contract) --------
# Different upstream parsers wrap lane/line geometry differently:
#   CAD : payload["geometry"] = [[x, y], [x, y], ...]        (bare point list)
#   PDF : payload["geometry"] = {"points": [[x, y], ...], "x0": .., "top": ..}
#   some: payload["geometry"] = {"coordinates": [...]}  / {"vertices": [...]}
# The transform chains expect a bare point list. When the shape differs, a chain
# can iterate dict KEYS and crash (e.g. "could not convert string to float: 'g'"
# from the key "geometry"). This normaliser unifies any recognised geometry shape
# into a bare [[x, y], ...] list, so EVERY geometry field is robust — not just the
# ones we patched reactively. It is intentionally conservative: if it can't make
# sense of the shape, it leaves the payload untouched (no guessing, no data loss).
_GEOMETRY_KEYS = ("geometry", "polyline", "vertices", "points", "coordinates")
_POINT_LIST_KEYS = ("points", "vertices", "coordinates", "polyline", "geometry")


def _looks_like_point_list(v):
    return (isinstance(v, (list, tuple)) and v
            and all(isinstance(p, (list, tuple)) and len(p) >= 2 for p in v))


def _normalize_geometry(payload):
    """Best-effort: turn payload['geometry'] (any recognised shape) into a bare
    [[x, y], ...] point list. Returns payload unchanged if nothing to do."""
    if not isinstance(payload, dict):
        return payload
    for gkey in _GEOMETRY_KEYS:
        if gkey not in payload:
            continue
        g = payload[gkey]
        # already a bare point list -> done
        if _looks_like_point_list(g):
            payload[gkey] = [list(p[:2]) for p in g]
            return payload
        # nested dict like {"points": [...]} / {"vertices": [...]} -> dig in
        if isinstance(g, dict):
            for pk in _POINT_LIST_KEYS:
                if pk in g and _looks_like_point_list(g[pk]):
                    payload[gkey] = [list(p[:2]) for p in g[pk]]
                    return payload
            # bbox-style {x0, top, x1, bottom} -> two corner points (last resort)
            if all(k in g for k in ("x0", "top", "x1", "bottom")):
                payload[gkey] = [[g["x0"], g["top"]], [g["x1"], g["bottom"]]]
                return payload
        # unrecognised shape: leave untouched (no guessing)
        return payload
    return payload



def _unwrap_payload(fact):
    """Return a dict payload usable by transforms.
    Canonical shape is payload={"value": X}; older parsers used a top-level
    `value`. We normalise so the engine/transforms receive X directly, wrapped
    in a dict if X isn't already one. Sibling keys placed alongside `value`
    (instance keys, movement_id, etc.) are PRESERVED so routing can use them."""
    payload = fact.get("payload")
    siblings = {}
    if isinstance(payload, dict) and "value" in payload:
        value = payload["value"]
        siblings = {k: v for k, v in payload.items() if k != "value"}
    elif "value" in fact:
        value = fact["value"]
    elif isinstance(payload, dict):
        value = payload            # already a usable dict
    else:
        value = payload
    if isinstance(value, dict):
        result = dict(value)
    else:
        result = {"value": value}
    # carry across instance keys / movement_id / etc. without clobbering value data
    for k, v in siblings.items():
        result.setdefault(k, v)
    # Plan B: unify geometry shape so every geometry field is robust
    result = _normalize_geometry(result)
    return result


def flatten_facts(extracted):
    """Pull facts out of the nested ingestion output into a flat list."""
    if isinstance(extracted, list):
        return [dict(f) for f in extracted]
    flat = []
    for source in extracted.get("source_files", []):
        for fact in source.get("extracted_facts", []):
            item = dict(fact)
            item.setdefault("source_file", source.get("source_file"))
            item.setdefault("file_type", source.get("file_type"))
            flat.append(item)
    # some pipelines may already provide a flat "facts"/"extracted_facts" list
    if not flat:
        for key in ("facts", "extracted_facts"):
            if isinstance(extracted.get(key), list):
                return [dict(f) for f in extracted[key]]
    return flat


def build_scope_map(assignments):
    """fact_id -> {intersection_ref, lane_ref} from the assignment output."""
    if not assignments:
        return {}
    scope = {}
    for a in assignments.get("assigned_facts", []):
        fid = a.get("fact_id")
        ts = a.get("target_scope") or {}
        if fid:
            scope[fid] = {k: v for k, v in {
                "intersection_ref": ts.get("intersection_ref"),
                "lane_ref": ts.get("lane_ref"),
                "approach_ref": ts.get("approach_ref"),
                "connection_ref": ts.get("connection_ref"),
                "node_ref": ts.get("node_ref"),
            }.items() if v is not None}
    return scope


def _point_xy(point):
    if isinstance(point, dict) and "x" in point and "y" in point:
        return [float(point["x"]), float(point["y"])]
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        return [float(point[0]), float(point[1])]
    return None


def _point_list(value):
    if isinstance(value, dict):
        for key in ("geometry", "polyline", "vertices", "points", "coordinates"):
            if key in value:
                return _point_list(value[key])
        return None
    if not isinstance(value, list):
        return None
    points = []
    for point in value:
        xy = _point_xy(point)
        if xy is not None:
            points.append(xy)
    return points or None


def _centroid_xy(item):
    if not isinstance(item, dict):
        return None
    centroid = item.get("centroid")
    if centroid is not None:
        return _point_xy(centroid)
    return None


def _cad_center(assignments):
    points = []
    for key in ("approaches", "lanes"):
        for item in (assignments or {}).get(key, []) or []:
            point = _centroid_xy(item)
            if point is not None:
                points.append(point)
    if not points:
        return None
    return [
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    ]


def _distance(a, b):
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _direction_from_geometry(polyline, center, tolerance=1.0):
    points = _point_list(polyline)
    if not points or len(points) < 2 or center is None:
        return None
    start_distance = _distance(points[0], center)
    end_distance = _distance(points[-1], center)
    if abs(start_distance - end_distance) <= tolerance:
        return None
    return "ingress" if end_distance < start_distance else "egress"


def _raw_fact_payload(fact):
    payload = fact.get("payload")
    if isinstance(payload, dict) and "value" in payload:
        return payload["value"]
    return payload


def _fact_lookup(facts):
    return {fact.get("fact_id"): fact for fact in facts if fact.get("fact_id")}


def _stop_line_lanes(assignments):
    lanes = set()
    for item in (assignments or {}).get("assigned_facts", []) or []:
        if item.get("fact_name") != "stop_line_from_cad":
            continue
        scope = item.get("target_scope") or {}
        lane_ref = scope.get("lane_ref")
        if lane_ref:
            lanes.add(lane_ref)
    return lanes


def _approaches_with_stop_lines(assignments, stop_line_lanes):
    approaches = set()
    for lane in (assignments or {}).get("lanes", []) or []:
        if lane.get("lane_ref") in stop_line_lanes and lane.get("approach_ref"):
            approaches.add(lane["approach_ref"])
    return approaches


def _lane_source_geometries(lane, facts_by_id):
    ids = []
    if lane.get("source_fact_id"):
        ids.append(lane["source_fact_id"])
    ids.extend(lane.get("clustered_from") or [])
    for fact_id in ids:
        fact = facts_by_id.get(fact_id)
        if not fact:
            continue
        points = _point_list(_raw_fact_payload(fact))
        if points:
            yield points


def _approach_assignment_payloads(assignments, source_facts=None):
    if not assignments:
        return []
    facts_by_id = _fact_lookup(source_facts or [])
    stop_line_lanes = _stop_line_lanes(assignments)
    approaches_with_stop_lines = _approaches_with_stop_lines(assignments, stop_line_lanes)
    center = _cad_center(assignments)
    payloads = []
    for lane in assignments.get("lanes", []) or []:
        lane_ref = lane.get("lane_ref")
        approach_ref = lane.get("approach_ref")
        if not lane_ref or not approach_ref:
            continue
        payload = {
            "intersection_ref": lane.get("intersection_ref", "intersection_1"),
            "lane_ref": lane_ref,
            "approach_ref": approach_ref,
            "value": approach_ref,
        }
        if lane.get("direction") in {"ingress", "egress", "both"}:
            payload["direction"] = lane["direction"]
            payload["direction_basis"] = lane.get("lane_semantic_basis", "assignment_lane_direction")
        elif lane_ref in stop_line_lanes:
            payload["direction"] = "ingress"
            payload["direction_basis"] = "cad_stop_line"
        else:
            for polyline in _lane_source_geometries(lane, facts_by_id):
                direction = _direction_from_geometry(polyline, center)
                if direction:
                    payload["direction"] = direction
                    payload["direction_basis"] = "geometry_relative_to_cad_center"
                    break
            if "direction" not in payload and approach_ref in approaches_with_stop_lines:
                payload["direction"] = "egress"
                payload["direction_basis"] = "approach_stop_line_complement"
        if lane.get("requires_context_match"):
            payload["requires_context_match"] = True
        payload["_source_file"] = lane.get("source_file", "geometry_assignment")
        payloads.append(payload)
    return payloads


def build_approach_assignment_facts(assignments, source_facts=None):
    """Expose assignment-stage lane->approach grouping to matching.

    Geometry assignment has already grouped lanes into approaches. Matching rules
    need a normal fact to use that result; otherwise approach_ref stays trapped
    in geometry_assignments.partial.json and cannot populate MAPEM fields.
    """
    facts = []
    for payload in _approach_assignment_payloads(assignments, source_facts):
        lane_ref = payload["lane_ref"]
        source_file = payload.pop("_source_file", "geometry_assignment")
        facts.append({
            "fact_id": f"approach_assignment_{lane_ref}",
            "fact_name": "approach_assignment_candidate_from_cad",
            "payload": payload,
            "confidence": "high",
            "source_file": source_file,
        })
    return facts


def build_lane_prototype_facts(assignments):
    facts = []
    for lane in (assignments or {}).get("lanes", []) or []:
        lane_ref = lane.get("lane_ref")
        geometry = lane.get("geometry")
        if not lane_ref or not geometry:
            continue
        base_payload = {
            "intersection_ref": lane.get("intersection_ref", "intersection_1"),
            "lane_ref": lane_ref,
            "geometry": geometry,
            "direction": lane.get("direction"),
            "lane_type": lane.get("lane_type", "vehicle"),
            "label": lane.get("lane_type", "vehicle"),
            "value": geometry,
            "connection_basis": lane.get("lane_semantic_basis"),
        }
        if lane.get("approach_ref"):
            base_payload["approach_ref"] = lane["approach_ref"]
        facts.append({
            "fact_id": f"lane_prototype_geometry_{lane_ref}",
            "fact_name": "lane_geometry_candidate_from_cad",
            "payload": base_payload,
            "confidence": "high",
            "source_file": lane.get("source_file", "geometry_assignment"),
        })
        for node_index, point in enumerate(geometry, start=1):
            facts.append({
                "fact_id": f"lane_prototype_node_{lane_ref}_{node_index}",
                "fact_name": "lane_node_candidate_from_assignment",
                "payload": {
                    "intersection_ref": lane.get("intersection_ref", "intersection_1"),
                    "lane_ref": lane_ref,
                    "node_ref": f"{lane_ref}_node_{node_index}",
                    "x": point[0],
                    "y": point[1],
                    "value": {"x": point[0], "y": point[1]},
                },
                "confidence": "high",
                "source_file": lane.get("source_file", "geometry_assignment"),
            })
        facts.append({
            "fact_id": f"lane_prototype_use_{lane_ref}",
            "fact_name": "lane_use_label_from_cad",
            "payload": {
                "intersection_ref": lane.get("intersection_ref", "intersection_1"),
                "lane_ref": lane_ref,
                "lane_type": lane.get("lane_type", "vehicle"),
                "label": _lane_use_label(lane),
                "value": _lane_use_label(lane),
            },
            "confidence": "high",
            "source_file": lane.get("source_file", "geometry_assignment"),
        })
    return facts


def _lane_use_label(lane):
    if lane.get("use_label"):
        return lane["use_label"]
    lane_type = str(lane.get("lane_type", "vehicle")).lower()
    if lane_type in {"crosswalk", "crosswalklane"}:
        return "toucan pedestrian cycle crossing"
    return lane.get("lane_type", "vehicle")


def build_movement_direction_facts(assignments):
    facts = []
    for index, mapping in enumerate((assignments or {}).get("movement_lane_mappings", []) or [], start=1):
        maneuver = mapping.get("maneuver")
        lane_ref = mapping.get("lane_ref")
        target_lane_ref = mapping.get("target_lane_ref")
        if not maneuver or not lane_ref or not target_lane_ref:
            continue
        connection_ref = f"connection_{lane_ref}_to_{target_lane_ref}"
        facts.append({
            "fact_id": f"movement_direction_{index}_{lane_ref}_to_{target_lane_ref}",
            "fact_name": "movement_direction_candidate_from_cad",
            "payload": {
                "intersection_ref": mapping.get("intersection_ref", "intersection_1"),
                "lane_ref": lane_ref,
                "connection_ref": connection_ref,
                "target_lane_ref": target_lane_ref,
                "movement_ref": mapping.get("movement_ref"),
                "movement": maneuver,
                "maneuver": maneuver,
                "value": maneuver,
            },
            "confidence": confidence_to_level(mapping.get("confidence", "medium")),
            "source_file": mapping.get("source_file", "geometry_assignment"),
        })
    return facts


def build_connection_candidate_facts(assignments, source_facts=None, max_distance_m=120.0):
    """Create conservative movement-to-lane connection candidates.

    Prefer movement_lane_mappings because MAPEM connectsTo represents a movement
    from an ingress lane to an egress lane. Fall back to one geometry-only nearest
    egress connection per ingress lane when no usable movement evidence exists.
    """
    payloads = _approach_assignment_payloads(assignments, source_facts)
    lane_items = {
        lane.get("lane_ref"): lane
        for lane in (assignments or {}).get("lanes", []) or []
        if lane.get("lane_ref")
    }
    ingress = [p for p in payloads if p.get("direction") == "ingress"]
    egress = [p for p in payloads if p.get("direction") == "egress"]
    if not ingress:
        return []

    source_by_movement = _movement_source_payloads(source_facts or [])
    movement_facts = _movement_connection_candidate_facts(
        assignments or {},
        ingress,
        egress,
        lane_items,
        source_by_movement,
        max_distance_m,
    )
    if movement_facts:
        return movement_facts
    if not egress:
        return []

    facts = []
    for src in ingress:
        src_lane = lane_items.get(src["lane_ref"], {})
        best = _nearest_egress(src_lane, egress, lane_items)
        if best is None or best[0] > max_distance_m:
            continue
        distance, dst = best
        connection_ref = f"connection_{src['lane_ref']}_to_{dst['lane_ref']}"
        facts.append({
            "fact_id": f"lane_connection_{src['lane_ref']}_to_{dst['lane_ref']}",
            "fact_name": "lane_connection_candidate_from_cad",
            "payload": {
                "intersection_ref": src.get("intersection_ref", "intersection_1"),
                "lane_ref": src["lane_ref"],
                "connection_ref": connection_ref,
                "target_lane_ref": dst["lane_ref"],
                "target_approach_ref": dst.get("approach_ref"),
                "distance_m": distance,
                "value": dst["lane_ref"],
                "connection_basis": "nearest_confirmed_egress_centroid",
                "requires_context_match": True,
            },
            "confidence": "medium",
            "source_file": src.get("_source_file", "geometry_assignment"),
        })
    return facts


def _movement_source_payloads(source_facts):
    by_ref = {}
    for fact in source_facts or []:
        payload = _unwrap_payload(fact)
        if not isinstance(payload, dict):
            continue
        movement_ref = payload.get("movement_ref")
        if not movement_ref:
            continue
        by_ref.setdefault(str(movement_ref), []).append(payload)
    return by_ref


def _movement_connection_candidate_facts(
    assignments,
    ingress,
    egress,
    lane_items,
    source_by_movement,
    max_distance_m,
):
    ingress_refs = {item["lane_ref"] for item in ingress}
    egress_refs = {item["lane_ref"] for item in egress}
    facts = []
    seen_connection_refs = set()
    for mapping in assignments.get("movement_lane_mappings", []) or []:
        movement_ref = mapping.get("movement_ref")
        lane_ref = mapping.get("lane_ref")
        if not movement_ref or not lane_ref or lane_ref not in ingress_refs:
            continue
        src_lane = lane_items.get(lane_ref, {})
        target_lane_ref = (
            mapping.get("target_lane_ref")
            or mapping.get("egress_lane_ref")
            or mapping.get("connecting_lane_ref")
        )
        distance = None
        if target_lane_ref:
            if target_lane_ref not in lane_items:
                continue
            src_centroid = _centroid_xy(src_lane)
            dst_centroid = _centroid_xy(lane_items.get(target_lane_ref, {}))
            if src_centroid is not None and dst_centroid is not None:
                distance = _distance(src_centroid, dst_centroid)
        else:
            if not egress_refs:
                continue
            best = _nearest_egress(src_lane, egress, lane_items)
            if best is None or best[0] > max_distance_m:
                continue
            distance, dst = best
            target_lane_ref = dst["lane_ref"]

        base_ref = f"connection_{lane_ref}_to_{target_lane_ref}"
        connection_ref = base_ref
        if connection_ref in seen_connection_refs:
            connection_ref = f"{base_ref}_{_safe_ref_suffix(movement_ref)}"
        seen_connection_refs.add(connection_ref)

        source_payloads = source_by_movement.get(str(movement_ref), [])
        phase_refs = _mapping_phase_refs(mapping, source_payloads)
        payload = {
            "intersection_ref": mapping.get("intersection_ref") or _lane_intersection_ref(src_lane),
            "lane_ref": lane_ref,
            "connection_ref": connection_ref,
            "target_lane_ref": target_lane_ref,
            "movement_ref": movement_ref,
            "phase_refs": phase_refs,
            "value": target_lane_ref,
            "connection_basis": mapping.get("assignment_method", "movement_lane_mapping"),
            "requires_context_match": bool(mapping.get("requires_context_match")),
        }
        target_approach_ref = _lane_approach_ref(lane_items.get(target_lane_ref, {}))
        if target_approach_ref:
            payload["target_approach_ref"] = target_approach_ref
        if distance is not None:
            payload["distance_m"] = distance
        maneuver = _movement_maneuver(mapping, source_payloads)
        if maneuver:
            payload["maneuver"] = maneuver
        signal_group = mapping.get("signal_group") or mapping.get("signalGroup")
        if signal_group is not None:
            payload["signalGroup"] = signal_group
        movement_text = mapping.get("movement_text") or _first_value(source_payloads, "movement_text")
        if movement_text:
            payload["movement_text"] = movement_text
        facts.append({
            "fact_id": f"lane_connection_{lane_ref}_to_{target_lane_ref}_{_safe_ref_suffix(movement_ref)}",
            "fact_name": "lane_connection_candidate_from_cad",
            "payload": payload,
            "confidence": confidence_to_level(mapping.get("confidence", "medium")),
            "source_file": mapping.get("source_file") or "geometry_assignment",
        })
    return facts


def _nearest_egress(src_lane, egress, lane_items):
    src_centroid = _centroid_xy(src_lane)
    if src_centroid is None:
        return None
    best = None
    for dst in egress:
        dst_lane = lane_items.get(dst["lane_ref"], {})
        dst_centroid = _centroid_xy(dst_lane)
        if dst_centroid is None:
            continue
        distance = _distance(src_centroid, dst_centroid)
        if best is None or distance < best[0]:
            best = (distance, dst)
    return best


def _mapping_phase_refs(mapping, source_payloads):
    refs = [str(ref) for ref in mapping.get("phase_refs", []) or [] if ref]
    for payload in source_payloads:
        phase_ref = payload.get("phase_ref")
        if phase_ref:
            refs.append(str(phase_ref))
    return sorted(set(refs))


def _movement_maneuver(mapping, source_payloads):
    return (
        mapping.get("maneuver")
        or _first_value(source_payloads, "maneuver")
        or _first_value(source_payloads, "arrow_direction_candidate")
        or _first_value(source_payloads, "movement")
    )


def _first_value(payloads, key):
    for payload in payloads:
        value = payload.get(key)
        if value:
            return value
    return None


def _lane_intersection_ref(lane):
    return lane.get("intersection_ref") or "intersection_1"


def _lane_approach_ref(lane):
    return lane.get("approach_ref")


def _safe_ref_suffix(value):
    text = "".join(ch if ch.isalnum() else "_" for ch in str(value).lower()).strip("_")
    return text or "movement"


def build_movement_to_lane(assignments, movement_map=None, source_facts=None):
    """ref -> {intersection_ref, lane_ref, requires_context_match}, where ref is a
    movement_ref OR a phase_ref.

    Phase/label facts can't carry lane_ref (it's an internal id assignment
    creates) but they carry a movement_ref / phase_ref. assignment now emits a
    `movement_lane_mappings` list ({movement_ref, lane_ref, phase_refs[],
    requires_context_match, ...}); we index it by BOTH the movement_ref and each
    of its phase_refs so a phase fact can resolve via either. Sources, in order:
      1. assignment's `movement_lane_mappings` (primary);
      2. legacy `lanes[].movement_id` (back-compat);
      3. an explicit movement_map file (override / fill-in).
    Mappings flagged `requires_context_match` are kept but marked provisional.
    Returns {} if nothing available — phase facts then degrade gracefully.
    """
    table = {}
    connected_lane_refs = _connected_source_lane_refs(source_facts or [])
    movement_connections = _movement_connection_index(source_facts or [])

    if assignments:
        # 1. primary: movement_lane_mappings
        movement_mappings = assignments.get("movement_lane_mappings", [])
        resolved_lane_refs = {}
        occupied_lane_refs = set()
        for index, m in enumerate(movement_mappings):
            lane_ref = m.get("lane_ref")
            if not lane_ref:
                connected_candidates = [
                    str(ref)
                    for ref in (m.get("candidate_lane_refs") or [])
                    if ref is not None and str(ref) in connected_lane_refs
                ]
                if len(set(connected_candidates)) == 1:
                    lane_ref = connected_candidates[0]
            if lane_ref:
                lane_ref = str(lane_ref)
                resolved_lane_refs[index] = lane_ref
                occupied_lane_refs.add(lane_ref)

        for index, m in enumerate(movement_mappings):
            if index in resolved_lane_refs:
                continue
            connected_candidates = [
                str(ref)
                for ref in (m.get("candidate_lane_refs") or [])
                if ref is not None and str(ref) in connected_lane_refs
            ]
            remaining = sorted(set(connected_candidates) - occupied_lane_refs)
            if len(remaining) == 1:
                resolved_lane_refs[index] = remaining[0]
                occupied_lane_refs.add(remaining[0])

        for index, m in enumerate(movement_mappings):
            lane_ref = resolved_lane_refs.get(index)
            if not lane_ref:
                continue
            target = {
                "intersection_ref": m.get("intersection_ref"),
                "lane_ref": lane_ref,
                "requires_context_match": bool(m.get("requires_context_match") or m.get("candidate_lane_refs")),
            }
            connection_ref = movement_connections.get(str(m.get("movement_ref")))
            if connection_ref:
                target["connection_ref"] = connection_ref
            mv = m.get("movement_ref")
            if mv is not None:
                table[str(mv)] = target
            for ph in m.get("phase_refs", []) or []:
                phase_target = dict(target)
                phase_connection_ref = movement_connections.get(str(ph))
                if phase_connection_ref:
                    phase_target["connection_ref"] = phase_connection_ref
                table.setdefault(str(ph), phase_target)

        # 2. legacy: movement_id carried on assigned lanes
        for lane in assignments.get("lanes", []):
            mv = lane.get("movement_id") or lane.get("movement")
            if mv is not None and lane.get("lane_ref"):
                table.setdefault(str(mv), {
                    "intersection_ref": lane.get("intersection_ref"),
                    "lane_ref": lane.get("lane_ref"),
                    "requires_context_match": False,
                })

    # 3. explicit map file overrides / fills in
    if movement_map:
        for ref, target in movement_map.items():
            if isinstance(target, dict):
                table[str(ref)] = {
                    "intersection_ref": target.get("intersection_ref"),
                    "lane_ref": target.get("lane_ref"),
                    "requires_context_match": bool(target.get("requires_context_match", False)),
                }
            else:  # bare lane_ref string
                entry = table.get(str(ref), {"requires_context_match": False})
                entry["lane_ref"] = target
                table[str(ref)] = entry

    return table


def _connected_source_lane_refs(source_facts):
    lane_refs = set()
    for fact in source_facts or []:
        if _fact_name(fact) != "lane_connection_candidate_from_cad":
            continue
        payload = _unwrap_payload(fact)
        if not isinstance(payload, dict):
            continue
        lane_ref = payload.get("lane_ref")
        if lane_ref:
            lane_refs.add(str(lane_ref))
    return lane_refs


def _movement_connection_index(source_facts):
    index = {}
    for fact in source_facts or []:
        if _fact_name(fact) != "lane_connection_candidate_from_cad":
            continue
        payload = _unwrap_payload(fact)
        if not isinstance(payload, dict):
            continue
        connection_ref = payload.get("connection_ref")
        if not connection_ref:
            continue
        movement_ref = payload.get("movement_ref")
        if movement_ref:
            index[str(movement_ref)] = connection_ref
        for phase_ref in payload.get("phase_refs", []) or []:
            index.setdefault(str(phase_ref), connection_ref)
    return index


def _route_refs(fact, payload):
    """Candidate refs to route a phase/label fact by, in order: movement_ref,
    movement_id, movement, then phase_ref. (assignment's semantic step may add
    phase_ref; controller config may carry a movement_ref.)"""
    refs = []
    for src in (payload, fact, fact.get("payload") or {}):
        if isinstance(src, dict):
            for key in ("movement_ref", "movement_id", "movement", "phase_ref"):
                v = src.get(key)
                if v is not None and str(v) not in refs:
                    refs.append(str(v))
    return refs


def _inject_nongeometry_scope(fact, payload, movement_to_lane):
    """Route phase/label facts to a lane via movement_ref / phase_ref -> lane_ref.

    Uses assignment's movement_lane_mappings (indexed by movement_ref and
    phase_ref). If a mapping is flagged requires_context_match, the lane_ref is
    still injected but marked provisional so downstream treats it as needing
    confirmation rather than certain. Facts with no ref, or an unmapped one, stay
    intersection-scoped rather than being guessed.
    """
    refs = _route_refs(fact, payload)
    if not refs:
        return payload
    for ref in refs:
        target = movement_to_lane.get(ref)
        if target and target.get("lane_ref"):
            payload["lane_ref"] = target["lane_ref"]
            if target.get("connection_ref"):
                payload["connection_ref"] = target["connection_ref"]
            if target.get("intersection_ref") and "intersection_ref" not in payload:
                payload["intersection_ref"] = target["intersection_ref"]
            if target.get("requires_context_match"):
                payload["_lane_ref_provisional"] = True   # needs context confirmation
            return payload
    # had a ref but none mapped — keep visible for debugging
    payload.setdefault("_unmapped_movement_ref", refs[0])
    return payload


def adapt(extracted, assignments=None, movement_map=None,
          high=0.8, medium=0.5):
    facts = build_lane_prototype_facts(assignments)
    facts.extend(build_movement_direction_facts(assignments))
    facts.extend(flatten_facts(extracted))
    site_fact = _site_id_fact(extracted)
    if site_fact and not any(_fact_name(f) == "official_intersection_id_from_cad" for f in facts):
        facts.insert(0, site_fact)
    facts.extend(build_approach_assignment_facts(assignments, facts))
    facts.extend(build_connection_candidate_facts(assignments, facts))
    scope_map = build_scope_map(assignments)
    movement_to_lane = build_movement_to_lane(assignments, movement_map, facts)
    out = []
    for i, fact in enumerate(facts):
        name = _fact_name(fact)
        payload = _unwrap_payload(fact)
        fid = fact.get("fact_id") or f"f{i:05d}"

        # inject instance keys from geometry assignment (matched by fact_id)
        if fid in scope_map:
            payload.update(scope_map[fid])
        else:
            # non-geometry (phase/label): route via movement_id -> lane_ref
            payload = _inject_nongeometry_scope(fact, payload, movement_to_lane)

        # preserve the original float confidence for the confidence workstream
        raw_conf = fact.get("confidence")
        if isinstance(raw_conf, (int, float)):
            payload.setdefault("_confidence_score", raw_conf)

        out.append({
            "fact_id": fid,
            "fact_name": name,
            "payload": payload,
            "confidence": confidence_to_level(raw_conf, high, medium),
            "source_file": fact.get("source_file") or fact.get("evidence_location", ""),
        })
    return {"facts": out}


def main(argv=None):
    p = argparse.ArgumentParser(description="Adapt ingestion/assignment output for the matching engine")
    p.add_argument("--facts", required=True, help="extracted_facts(.partial).json")
    p.add_argument("--assignments", default=None, help="geometry_assignments.partial.json (optional)")
    p.add_argument("--movement-map", default=None,
                   help="movement_id -> lane_ref map (json, optional); bridges phase facts to lanes")
    p.add_argument("--out", required=True, help="output facts.json for the engine")
    p.add_argument("--high", type=float, default=0.8, help="confidence >= high -> 'high'")
    p.add_argument("--medium", type=float, default=0.5, help="confidence >= medium -> 'medium'")
    args = p.parse_args(argv)

    extracted = json.load(open(args.facts, encoding="utf-8"))
    assignments = json.load(open(args.assignments, encoding="utf-8")) if args.assignments else None
    movement_map = json.load(open(args.movement_map, encoding="utf-8")) if args.movement_map else None

    result = adapt(extracted, assignments, movement_map, args.high, args.medium)
    json.dump(result, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    n = len(result["facts"])
    scoped = sum(1 for f in result["facts"]
                 if "lane_ref" in f["payload"])
    unmapped = sum(1 for f in result["facts"]
                   if "_unmapped_movement_ref" in f["payload"])
    provisional = sum(1 for f in result["facts"]
                      if f["payload"].get("_lane_ref_provisional"))
    print(f"[ok] wrote {args.out}: {n} facts ({scoped} with lane_ref, "
          f"{provisional} provisional/requires-context, {unmapped} with an unmapped ref)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
