from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LANE_DEFINING_TIERS = [
    {
        "lane_geometry_candidate_from_cad",
    },
    {
        "lane_geometry_candidate_from_ordnance_survey",
    },
    {
        "lane_line_candidate_from_pdf_vector",
        "lane_line_candidate_from_pdf_cv",
    },
    {
        "cad_arrow_block_candidate",
    },
]

LANE_FACT_NAMES = set().union(*LANE_DEFINING_TIERS)
PDF_LANE_MERGE_DISTANCE = 2.0
PDF_LANE_ANGLE_TOLERANCE_DEG = 20.0
MAX_PDF_LANE_CLUSTERS = 50
CAD_LANE_LAYER_KEYWORDS = (
    "lane",
)
CAD_NON_LANE_LAYER_KEYWORDS = (
    "duct",
    "loop",
    "intergreen",
    "detector",
    "signal",
    "head",
    "cross",
    "kerb",
    "text",
    "label",
)

ASSIGNABLE_GEOMETRY_FACT_NAMES = {
    "lane_geometry_candidate_from_cad",
    "lane_facility_geometry_candidate_from_cad",
    "cad_geometry_candidate",
    "cad_text_label",
    "cad_block_reference",
    "cad_movement_label_candidate",
    "cad_arrow_block_candidate",
    "cad_signal_head_candidate",
    "cad_pole_candidate",
    "cad_pedestrian_facility_candidate",
    "cad_lane_use_label_candidate",
    "lane_geometry_candidate_from_ordnance_survey",
    "stop_line_from_cad",
    "stop_line_candidate_from_pdf_vector",
    "stop_line_candidate_from_pdf_cv",
    "crossing_candidate_from_pdf_vector",
    "signal_head_symbol_candidate_from_pdf_vector",
    "signal_head_symbol_candidate_from_pdf_cv",
    "road_marking_candidate_from_pdf_vector",
    "road_marking_candidate_from_pdf_cv",
    "arrow_candidate_from_pdf_vector",
    "lane_line_candidate_from_pdf_vector",
    "lane_line_candidate_from_pdf_cv",
}

INTERSECTION_CENTRE_FACT_NAMES = {
    "junction_centre_from_ordnance_survey",
    "junction_centre_from_open_street_map",
}

SEMANTIC_FACT_NAME_PATTERNS = (
    "phase",
    "stage",
    "stream",
    "detector",
    "signal",
    "label",
    "road_name",
    "movement",
    "scoot",
    "timing",
    "intergreen",
    "control",
)


@dataclass(frozen=True)
class GeometryItem:
    fact: dict[str, Any]
    centroid: tuple[float, float]
    bounds: dict[str, float]
    coordinate_space: str
    page_ref: str | None = None


@dataclass(frozen=True)
class LaneItem:
    lane_ref: str
    intersection_ref: str
    item: GeometryItem
    lane_index: int


def assign_geometry_to_lanes(extracted_facts: dict[str, Any]) -> dict[str, Any]:
    """Assign geometry facts to intersection and lane scopes.

    This stage does not map facts to MAPEM fields. It only adds spatial scope
    references that later matching/fusion can use.
    """

    facts = _flatten_facts(extracted_facts)
    intersections = _build_intersections(extracted_facts, facts)
    lane_items, lane_tier = _build_lanes(facts, intersections)
    if _add_semantic_movement_lane_proxies(facts, intersections, lane_items) and lane_tier == -1:
        lane_tier = 4
    assigned_facts = _assign_facts(facts, intersections, lane_items)
    semantic_assignments = _assign_semantic_facts(facts, intersections)
    movement_lane_mappings = _build_movement_lane_mappings(facts, lane_items, assigned_facts)
    return {
        "site_id": str(extracted_facts.get("site_id", "")),
        "intersections": intersections,
        "lanes": [_lane_output(lane) for lane in lane_items],
        "assigned_facts": assigned_facts,
        "semantic_assignments": semantic_assignments,
        "movement_lane_mappings": movement_lane_mappings,
        "lane_source_tier": lane_tier,
        "unassigned_fact_count": _unassigned_geometry_count(facts, assigned_facts),
        "unassigned_geometry_fact_count": _unassigned_geometry_count(facts, assigned_facts),
        "unassigned_semantic_fact_count": _unassigned_semantic_count(facts, semantic_assignments),
        "notes": [
            "Geometry assignment adds intersection_ref and lane_ref to spatial facts.",
            "Semantic assignment adds phase_ref, stage_ref, detector_ref, signal_group_ref, approach_ref, or label_ref to non-geometry facts when the reference is directly visible.",
            "Non-geometry facts are not forced onto a lane; lane_ref remains null unless a reliable geometry anchor is available.",
            "It does not choose MAPEM fields or build SiteModel.",
            "PDF page-space geometry is assigned only within the same PDF page coordinate space.",
            "Lanes are defined by the highest-priority available source: CAD, then Ordnance Survey, then PDF fallback.",
            "When PDF is the only lane source, similar lane-line segments are clustered into lane corridors.",
            f"PDF fallback lane creation is suppressed when more than {MAX_PDF_LANE_CLUSTERS} lane clusters are found.",
            "Movement-to-lane mappings are emitted only when lane movement labels are directly available; otherwise the movement is marked for later context matching.",
            "If no geometry source can resolve a structured movement, assignment creates a low-confidence semantic lane proxy so every movement can carry a lane_ref while still requiring context match.",
        ],
    }


def _flatten_facts(extracted_facts: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for source in extracted_facts.get("source_files", []):
        for fact in source.get("extracted_facts", []):
            item = dict(fact)
            item.setdefault("source_file", source.get("source_file"))
            item.setdefault("file_type", source.get("file_type"))
            facts.append(item)
    return facts


def _build_intersections(extracted_facts: dict[str, Any], facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    centres = [fact for fact in facts if fact.get("fact_name") in INTERSECTION_CENTRE_FACT_NAMES]
    intersections: list[dict[str, Any]] = []
    for index, fact in enumerate(centres, start=1):
        value = _fact_value(fact)
        point = _point_from_mapping(value)
        if point is None:
            continue
        intersections.append(
            {
                "intersection_ref": f"intersection_{index}",
                "source": fact.get("fact_name"),
                "centroid": {"x": point[0], "y": point[1]},
                "source_fact_id": fact.get("fact_id"),
                "confidence": fact.get("confidence"),
            }
        )
    if intersections:
        return intersections
    return [
        {
            "intersection_ref": "intersection_1",
            "source": "site_folder_default",
            "centroid": None,
            "source_fact_id": None,
            "confidence": 0.3,
            "note": "No explicit junction centre fact was available; all geometry is assigned to the default site intersection.",
        }
    ]


def _select_lane_tier(facts: list[dict[str, Any]]) -> tuple[set[str] | None, int]:
    for tier_index, tier in enumerate(LANE_DEFINING_TIERS):
        if any(fact.get("fact_name") in tier and _can_define_lane(fact) for fact in facts):
            return tier, tier_index
    return None, -1


def _build_lanes(facts: list[dict[str, Any]], intersections: list[dict[str, Any]]) -> tuple[list[LaneItem], int]:
    for tier_index, tier in enumerate(LANE_DEFINING_TIERS):
        if not any(fact.get("fact_name") in tier and _can_define_lane(fact) for fact in facts):
            continue
        items: list[GeometryItem] = []
        for fact in facts:
            if fact.get("fact_name") not in tier:
                continue
            if not _can_define_lane(fact):
                continue
            item = _geometry_item(fact)
            if item is not None:
                items.append(item)

        if tier_index == 2:
            items = _cluster_pdf_lane_lines(items, intersections)
            if len(items) > MAX_PDF_LANE_CLUSTERS:
                continue

        lanes: list[LaneItem] = []
        for item in items:
            intersection_ref = _nearest_intersection_ref(item, intersections)
            lane_index = len(lanes) + 1
            lanes.append(
                LaneItem(
                    lane_ref=f"lane_{lane_index}",
                    intersection_ref=intersection_ref,
                    item=item,
                    lane_index=lane_index,
                )
            )
        if lanes:
            return lanes, tier_index
    return [], -1


def _add_semantic_movement_lane_proxies(
    facts: list[dict[str, Any]],
    intersections: list[dict[str, Any]],
    lanes: list[LaneItem],
) -> bool:
    if any(not _is_fallback_lane_proxy(lane) for lane in lanes):
        return False
    covered_refs = set(_lane_movement_index(lanes))
    covered_arrow_hints = set(_lane_arrow_maneuver_index(lanes))
    added = False
    seen: set[str] = set()
    for fact in facts:
        movement_ref = _movement_ref(fact)
        if movement_ref is None or movement_ref in seen or movement_ref in covered_refs:
            continue
        arrow_hint = _movement_arrow_hint(fact)
        if arrow_hint is not None and arrow_hint in covered_arrow_hints:
            seen.add(movement_ref)
            continue
        item = _semantic_movement_lane_item(fact, intersections, len(lanes) + 1)
        if item is None:
            continue
        lane_index = len(lanes) + 1
        lanes.append(
            LaneItem(
                lane_ref=f"lane_{lane_index}",
                intersection_ref=_nearest_intersection_ref(item, intersections),
                item=item,
                lane_index=lane_index,
            )
        )
        seen.add(movement_ref)
        added = True
    return added


def _is_fallback_lane_proxy(lane: LaneItem) -> bool:
    return lane.item.fact.get("fact_name") in {"cad_arrow_block_candidate", "semantic_movement_lane_proxy"}


def _semantic_movement_lane_item(
    fact: dict[str, Any],
    intersections: list[dict[str, Any]],
    lane_index: int,
) -> GeometryItem | None:
    value = _fact_value(fact)
    if not isinstance(value, dict):
        return None
    movement_ref = _movement_ref(fact)
    if movement_ref is None:
        return None
    centroid = _semantic_lane_centroid(intersections, lane_index)
    proxy_value = {
        "movement_ref": movement_ref,
        "movement_text": value.get("movement_text"),
        "road_name": value.get("road_name"),
        "direction": value.get("direction"),
        "maneuver": value.get("maneuver"),
        "phase_ref": value.get("phase_ref"),
        "geometry": {"x": centroid[0], "y": centroid[1]},
        "requires_context_match": True,
        "proxy_reason": "structured_movement_without_geometry",
    }
    proxy_fact = {
        "fact_id": "semantic_lane_proxy_" + stable_assignment_id(movement_ref),
        "fact_name": "semantic_movement_lane_proxy",
        "payload": {"value": proxy_value},
        "source_file": fact.get("source_file"),
        "evidence_location": fact.get("evidence_location"),
        "confidence": min(float(fact.get("confidence") or 0.5), 0.5),
    }
    return GeometryItem(
        fact=proxy_fact,
        centroid=centroid,
        bounds={"min_x": centroid[0], "min_y": centroid[1], "max_x": centroid[0], "max_y": centroid[1]},
        coordinate_space="semantic_movement",
        page_ref=None,
    )


def _semantic_lane_centroid(intersections: list[dict[str, Any]], lane_index: int) -> tuple[float, float]:
    centroid = intersections[0].get("centroid") if intersections else None
    if isinstance(centroid, dict) and isinstance(centroid.get("x"), (int, float)) and isinstance(centroid.get("y"), (int, float)):
        return float(centroid["x"]) + lane_index, float(centroid["y"])
    return float(lane_index), 0.0


def _can_define_lane(fact: dict[str, Any]) -> bool:
    fact_name = str(fact.get("fact_name") or "")
    if fact_name == "lane_geometry_candidate_from_cad":
        return _is_cad_lane_layer(fact)
    if fact_name == "cad_arrow_block_candidate":
        return _cad_arrow_lane_hint(fact) is not None
    return fact_name in LANE_FACT_NAMES


def _is_cad_lane_layer(fact: dict[str, Any]) -> bool:
    layer = _cad_layer_name(fact)
    if not layer:
        value = _fact_value(fact)
        return isinstance(value, dict) and any(value.get(key) for key in ("movement_ref", "movement_text", "label", "road_name"))
    lowered = layer.lower()
    if any(keyword in lowered for keyword in CAD_NON_LANE_LAYER_KEYWORDS):
        return False
    return any(keyword in lowered for keyword in CAD_LANE_LAYER_KEYWORDS)


def _cad_layer_name(fact: dict[str, Any]) -> str | None:
    location = str(fact.get("evidence_location") or "")
    match = re.search(r"\blayer\s+([^>]+)$", location, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"\blayer\s+(.+?)(?:\s+->|$)", location, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _cluster_pdf_lane_lines(items: list[GeometryItem], intersections: list[dict[str, Any]]) -> list[GeometryItem]:
    grouped: dict[tuple[str, str, str | None], list[GeometryItem]] = {}
    for item in items:
        key = (_nearest_intersection_ref(item, intersections), item.coordinate_space, item.page_ref)
        grouped.setdefault(key, []).append(item)
    clustered: list[GeometryItem] = []
    for group in grouped.values():
        clustered.extend(_cluster_lane_line_group(group))
    return clustered


def _cluster_lane_line_group(
    items: list[GeometryItem],
    merge_distance: float = PDF_LANE_MERGE_DISTANCE,
    angle_tolerance: float = PDF_LANE_ANGLE_TOLERANCE_DEG,
) -> list[GeometryItem]:
    clusters: list[dict[str, Any]] = []
    for item in items:
        angle = _segment_orientation(item)
        placed = False
        for cluster in clusters:
            if _angle_close(angle, cluster["angle"], angle_tolerance) and _distance(item.centroid, cluster["centroid"]) <= merge_distance:
                cluster["members"].append(item)
                cluster["centroid"] = _mean_centroid(cluster["members"])
                cluster["angle"] = _mean_angle(cluster["members"])
                placed = True
                break
        if not placed:
            clusters.append({"members": [item], "centroid": item.centroid, "angle": angle})
    return [_merge_lane_cluster(cluster["members"]) for cluster in clusters]


def _segment_orientation(item: GeometryItem) -> float:
    points = _geometry_item_points(item)
    if len(points) < 2:
        return 0.0
    dx = points[-1][0] - points[0][0]
    dy = points[-1][1] - points[0][1]
    if dx == 0 and dy == 0:
        return 0.0
    return math.degrees(math.atan2(dy, dx)) % 180.0


def _geometry_item_points(item: GeometryItem) -> list[tuple[float, float]]:
    value = _fact_value(item.fact)
    if isinstance(value, dict) and isinstance(value.get("geometry"), dict):
        value = value["geometry"]
    return _geometry_points(value)


def _angle_close(first: float, second: float, tolerance: float) -> bool:
    difference = abs(first - second) % 180.0
    return min(difference, 180.0 - difference) <= tolerance


def _mean_centroid(items: list[GeometryItem]) -> tuple[float, float]:
    return (
        sum(item.centroid[0] for item in items) / len(items),
        sum(item.centroid[1] for item in items) / len(items),
    )


def _mean_angle(items: list[GeometryItem]) -> float:
    return sum(_segment_orientation(item) for item in items) / len(items)


def _merge_lane_cluster(items: list[GeometryItem]) -> GeometryItem:
    bounds = {
        "min_x": min(item.bounds["min_x"] for item in items),
        "min_y": min(item.bounds["min_y"] for item in items),
        "max_x": max(item.bounds["max_x"] for item in items),
        "max_y": max(item.bounds["max_y"] for item in items),
    }
    base = items[0]
    merged_fact = dict(base.fact)
    member_ids = [item.fact.get("fact_id") for item in items]
    merged_fact["fact_id"] = "lane_cluster_" + stable_assignment_id(*member_ids)
    merged_fact["clustered_from"] = member_ids
    return GeometryItem(
        fact=merged_fact,
        centroid=_mean_centroid(items),
        bounds=bounds,
        coordinate_space=base.coordinate_space,
        page_ref=base.page_ref,
    )


def _assign_facts(
    facts: list[dict[str, Any]],
    intersections: list[dict[str, Any]],
    lanes: list[LaneItem],
) -> list[dict[str, Any]]:
    assigned: list[dict[str, Any]] = []
    lane_index = _lane_index(lanes)
    for fact in facts:
        if fact.get("fact_name") not in ASSIGNABLE_GEOMETRY_FACT_NAMES:
            continue
        item = _geometry_item(fact)
        if item is None:
            continue
        intersection_ref = _nearest_intersection_ref(item, intersections)
        lane = _nearest_lane(item, lane_index, intersection_ref)
        assignment = {
            "fact_id": fact.get("fact_id"),
            "fact_name": fact.get("fact_name"),
            "source_file": fact.get("source_file"),
            "evidence_location": fact.get("evidence_location"),
            "confidence": fact.get("confidence"),
            "target_scope": {
                "intersection_ref": intersection_ref,
                "lane_ref": lane.lane_ref if lane is not None else None,
            },
            "geometry_summary": {
                "centroid": {"x": item.centroid[0], "y": item.centroid[1]},
                "bounds": item.bounds,
                "coordinate_space": item.coordinate_space,
            },
            "assignment_method": "nearest_lane_centroid" if lane is not None else "intersection_only",
            "distance_to_lane": _distance(item.centroid, lane.item.centroid) if lane is not None else None,
        }
        if item.page_ref is not None:
            assignment["geometry_summary"]["page_ref"] = item.page_ref
        assigned.append(assignment)
    return assigned


def _assign_semantic_facts(facts: list[dict[str, Any]], intersections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assigned: list[dict[str, Any]] = []
    for fact in facts:
        if not _is_semantic_fact(fact):
            continue
        target_scope = _semantic_target_scope(fact, intersections)
        if target_scope is None:
            continue
        assignment = {
            "assignment_id": stable_assignment_id(fact.get("fact_id"), target_scope),
            "fact_id": fact.get("fact_id"),
            "fact_name": fact.get("fact_name"),
            "source_file": fact.get("source_file"),
            "evidence_location": fact.get("evidence_location"),
            "confidence": fact.get("confidence"),
            "target_scope": target_scope,
            "assignment_method": _semantic_assignment_method(target_scope),
            "assignment_basis": "direct_text_reference" if len(target_scope) > 2 else "source_level_semantic_context",
        }
        assigned.append(assignment)
    return assigned


def _build_movement_lane_mappings(
    facts: list[dict[str, Any]],
    lanes: list[LaneItem],
    assigned_facts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    movement_facts = [fact for fact in facts if _movement_ref(fact)]
    if not movement_facts:
        return []

    lane_index = _lane_movement_index(lanes)
    lane_arrow_index = _lane_arrow_maneuver_index(lanes)
    lane_by_ref = {lane.lane_ref: lane for lane in lanes}
    assignment_by_fact_id = {assignment.get("fact_id"): assignment for assignment in assigned_facts}
    mappings: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for fact in movement_facts:
        movement_ref = _movement_ref(fact)
        if movement_ref is None:
            continue
        lane = lane_index.get(movement_ref)
        assignment_method = _movement_lane_assignment_method(lane) if lane else "needs_context_match"
        if lane is None and fact.get("fact_name") == "cad_movement_label_candidate":
            assignment = assignment_by_fact_id.get(fact.get("fact_id"))
            lane_ref = ((assignment or {}).get("target_scope") or {}).get("lane_ref")
            lane = lane_by_ref.get(lane_ref)
            if lane is not None:
                assignment_method = "cad_movement_label_nearest_lane"
        if lane is None:
            arrow_hint = _movement_arrow_hint(fact)
            if arrow_hint is not None:
                lane = lane_arrow_index.get(arrow_hint)
                if lane is not None:
                    assignment_method = "cad_signal_arrow_direction_match"
        key = (movement_ref, lane.lane_ref if lane else None)
        if key in seen:
            continue
        seen.add(key)
        payload = _fact_value(fact)
        mapping = {
            "movement_ref": movement_ref,
            "lane_ref": lane.lane_ref if lane else None,
            "intersection_ref": lane.intersection_ref if lane else None,
            "phase_refs": _phase_refs_for_movement(movement_ref, movement_facts),
            "source_fact_id": fact.get("fact_id"),
            "source_fact_name": fact.get("fact_name"),
            "source_file": fact.get("source_file"),
            "evidence_location": fact.get("evidence_location"),
            "confidence": fact.get("confidence"),
            "movement_text": payload.get("movement_text") if isinstance(payload, dict) else None,
            "assignment_method": assignment_method,
            "requires_context_match": lane is None or assignment_method in {"cad_signal_arrow_direction_match", "semantic_movement_lane_proxy"},
        }
        if lane is None:
            mapping["unmatched_reason"] = "no_lane_movement_label"
        mappings.append(mapping)
    matched_movement_refs = {mapping["movement_ref"] for mapping in mappings if mapping.get("lane_ref")}
    return [
        mapping
        for mapping in mappings
        if mapping.get("lane_ref") or mapping["movement_ref"] not in matched_movement_refs
    ]


def _lane_movement_index(lanes: list[LaneItem]) -> dict[str, LaneItem]:
    index: dict[str, LaneItem] = {}
    for lane in lanes:
        for movement_ref in _lane_movement_refs(lane):
            index.setdefault(movement_ref, lane)
    return index


def _lane_movement_refs(lane: LaneItem) -> list[str]:
    value = _fact_value(lane.item.fact)
    labels: list[str] = []
    if isinstance(value, dict):
        for key in ("movement_ref", "movement_text", "label", "road_name"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                labels.append(candidate)
    if isinstance(value, str):
        labels.append(value)
    refs = []
    for label in labels:
        if label.startswith("movement_"):
            refs.append(label)
        else:
            slug = _slug_token(label)
            if slug:
                refs.append("movement_" + slug)
    return refs


def _movement_lane_assignment_method(lane: LaneItem | None) -> str:
    if lane is None:
        return "needs_context_match"
    if lane.item.fact.get("fact_name") == "semantic_movement_lane_proxy":
        return "semantic_movement_lane_proxy"
    return "lane_label_movement_match"


def _lane_arrow_maneuver_index(lanes: list[LaneItem]) -> dict[str, LaneItem]:
    index: dict[str, LaneItem] = {}
    for lane in lanes:
        hint = _cad_arrow_lane_hint(lane.item.fact)
        if hint is not None:
            index.setdefault(hint, lane)
    return index


def _cad_arrow_lane_hint(fact: dict[str, Any]) -> str | None:
    value = _fact_value(fact)
    if not isinstance(value, dict):
        return None
    if value.get("semantic_type") not in {None, "signal_arrow", "arrow"}:
        return None
    direction = str(value.get("arrow_direction_candidate") or "").lower()
    if direction in {"left", "left_turn"}:
        return "left_turn"
    if direction in {"right", "right_turn"}:
        return "right_turn"
    if direction in {"ahead", "straight", "through"}:
        return "ahead"
    return None


def _movement_arrow_hint(fact: dict[str, Any]) -> str | None:
    value = _fact_value(fact)
    if not isinstance(value, dict):
        return None
    maneuver = str(value.get("maneuver") or "").lower()
    if maneuver in {"left", "left_turn"}:
        return "left_turn"
    if maneuver in {"right", "right_turn"}:
        return "right_turn"
    if maneuver in {"ahead", "straight", "through"}:
        return "ahead"
    movement_text = str(value.get("movement_text") or "")
    lowered = movement_text.lower()
    if "right" in lowered:
        return "right_turn"
    if "left" in lowered:
        return "left_turn"
    if "ahead" in lowered or "straight" in lowered:
        return "ahead"
    return None


def _movement_ref(fact: dict[str, Any]) -> str | None:
    value = _fact_value(fact)
    if isinstance(value, dict) and isinstance(value.get("movement_ref"), str):
        return value["movement_ref"]
    return None


def _phase_refs_for_movement(movement_ref: str, movement_facts: list[dict[str, Any]]) -> list[str]:
    phase_refs = []
    for fact in movement_facts:
        value = _fact_value(fact)
        if not isinstance(value, dict):
            continue
        if value.get("movement_ref") == movement_ref and isinstance(value.get("phase_ref"), str):
            phase_refs.append(value["phase_ref"])
    return sorted(set(phase_refs))


def _is_semantic_fact(fact: dict[str, Any]) -> bool:
    fact_name = str(fact.get("fact_name") or "")
    if fact_name in ASSIGNABLE_GEOMETRY_FACT_NAMES or fact_name in INTERSECTION_CENTRE_FACT_NAMES:
        return False
    return any(pattern in fact_name for pattern in SEMANTIC_FACT_NAME_PATTERNS)


def _semantic_target_scope(fact: dict[str, Any], intersections: list[dict[str, Any]]) -> dict[str, str | None] | None:
    text = _fact_text(fact)
    fact_name = str(fact.get("fact_name") or "")
    scope: dict[str, str | None] = {
        "intersection_ref": intersections[0]["intersection_ref"],
        "lane_ref": None,
    }
    if phase_ref := _phase_ref(text):
        scope["phase_ref"] = phase_ref
    if stage_ref := _stage_ref(text):
        scope["stage_ref"] = stage_ref
    if detector_ref := _detector_ref(text):
        scope["detector_ref"] = detector_ref
    if signal_group_ref := _signal_group_ref(text):
        scope["signal_group_ref"] = signal_group_ref
    if "road_name" in fact_name:
        if approach_ref := _approach_ref(text):
            scope["approach_ref"] = approach_ref
    if "label" in fact_name and len(scope) == 2 and not any(keyword in fact_name for keyword in ("phase", "stage", "stream")):
        if label_ref := _label_ref(text):
            scope["label_ref"] = label_ref
    if len(scope) == 2 and not any(keyword in fact_name for keyword in ("phase", "stage", "detector", "signal", "stream", "timing", "intergreen", "control", "movement", "scoot")):
        return None
    return scope


def _semantic_assignment_method(target_scope: dict[str, str | None]) -> str:
    semantic_keys = set(target_scope) - {"intersection_ref", "lane_ref"}
    if not semantic_keys:
        return "intersection_semantic_scope"
    return "semantic_reference_extraction"


def _geometry_item(fact: dict[str, Any]) -> GeometryItem | None:
    value = _fact_value(fact)
    if isinstance(value, dict) and isinstance(value.get("geometry"), (dict, list)):
        value = value["geometry"]
    points = _geometry_points(value)
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    centroid = (sum(xs) / len(xs), sum(ys) / len(ys))
    bounds = {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}
    return GeometryItem(
        fact=fact,
        centroid=centroid,
        bounds=bounds,
        coordinate_space=_coordinate_space(fact),
        page_ref=_page_ref(fact),
    )


def _geometry_points(value: Any) -> list[tuple[float, float]]:
    if isinstance(value, list):
        points = [_point_from_sequence(item) for item in value]
        return [point for point in points if point is not None]
    if not isinstance(value, dict):
        return []
    if value.get("type") and "coordinates" in value:
        return _geojson_points(value.get("coordinates"))
    if isinstance(value.get("points"), list):
        points = [_point_from_sequence(item) for item in value["points"]]
        points = [point for point in points if point is not None]
        if points:
            return points
    line_points = _line_or_box_points(value)
    if line_points:
        return line_points
    point = _point_from_mapping(value)
    return [point] if point is not None else []


def _line_or_box_points(value: dict[str, Any]) -> list[tuple[float, float]]:
    if all(key in value for key in ("x1", "y1", "x2", "y2")):
        return [(float(value["x1"]), float(value["y1"])), (float(value["x2"]), float(value["y2"]))]
    if all(key in value for key in ("x0", "top", "x1", "bottom")):
        return [(float(value["x0"]), float(value["top"])), (float(value["x1"]), float(value["bottom"]))]
    if all(key in value for key in ("min_x", "min_y", "max_x", "max_y")):
        return [(float(value["min_x"]), float(value["min_y"])), (float(value["max_x"]), float(value["max_y"]))]
    return []


def _geojson_points(value: Any) -> list[tuple[float, float]]:
    point = _point_from_sequence(value)
    if point is not None:
        return [point]
    points: list[tuple[float, float]] = []
    if isinstance(value, (list, tuple)):
        for child in value:
            points.extend(_geojson_points(child))
    return points


def _point_from_sequence(value: Any) -> tuple[float, float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        if isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
            return float(value[0]), float(value[1])
    return None


def _point_from_mapping(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("lon"), (int, float)) and isinstance(value.get("lat"), (int, float)):
        return float(value["lon"]), float(value["lat"])
    if isinstance(value.get("x"), (int, float)) and isinstance(value.get("y"), (int, float)):
        return float(value["x"]), float(value["y"])
    return None


def _nearest_intersection_ref(item: GeometryItem, intersections: list[dict[str, Any]]) -> str:
    candidates = [
        (intersection["intersection_ref"], intersection.get("centroid"))
        for intersection in intersections
        if isinstance(intersection.get("centroid"), dict)
    ]
    if not candidates:
        return intersections[0]["intersection_ref"]
    return min(
        candidates,
        key=lambda candidate: _distance(item.centroid, (float(candidate[1]["x"]), float(candidate[1]["y"]))),
    )[0]


def _lane_index(lanes: list[LaneItem]) -> dict[tuple[str, str, str | None], list[LaneItem]]:
    index: dict[tuple[str, str, str | None], list[LaneItem]] = {}
    for lane in lanes:
        key = (lane.intersection_ref, lane.item.coordinate_space, lane.item.page_ref)
        index.setdefault(key, []).append(lane)
    return index


def _nearest_lane(
    item: GeometryItem,
    lane_index: dict[tuple[str, str, str | None], list[LaneItem]],
    intersection_ref: str,
) -> LaneItem | None:
    candidates = lane_index.get((intersection_ref, item.coordinate_space, item.page_ref), [])
    if not candidates:
        return None
    return min(candidates, key=lambda lane: _distance(item.centroid, lane.item.centroid))


def _coordinate_space(fact: dict[str, Any]) -> str:
    fact_name = str(fact.get("fact_name", ""))
    if fact_name == "semantic_movement_lane_proxy":
        return "semantic_movement"
    if "_pdf_" in fact_name or fact_name.startswith("pdf_"):
        return "pdf_page"
    if "_ordnance_survey" in fact_name or "_open_street_map" in fact_name:
        return "geographic_or_gis"
    return "cad_modelspace"


def _page_ref(fact: dict[str, Any]) -> str | None:
    if _coordinate_space(fact) != "pdf_page":
        return None
    source = str(fact.get("source_file") or "")
    page = None
    location = str(fact.get("evidence_location") or "")
    marker = "page "
    if marker in location:
        tail = location.split(marker, 1)[1]
        digits = []
        for char in tail:
            if char.isdigit():
                digits.append(char)
            else:
                break
        if digits:
            page = "".join(digits)
    return f"{source}#page={page or 'unknown'}"


def _fact_value(fact: dict[str, Any]) -> Any:
    return (fact.get("payload") or {}).get("value")


def _fact_text(fact: dict[str, Any]) -> str:
    value = _fact_value(fact)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "label", "movement_text", "name", "value"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
    if value is None:
        return ""
    return str(value)


def _phase_ref(text: str) -> str | None:
    match = re.search(r"\bphase\s+([A-Z0-9]{1,3})\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    token = _semantic_token(match.group(1))
    return f"phase_{token}" if token else None


def _stage_ref(text: str) -> str | None:
    match = re.search(r"\bstage\s+([A-Z0-9]{1,3})\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    token = _semantic_token(match.group(1))
    return f"stage_{token}" if token else None


def _detector_ref(text: str) -> str | None:
    match = re.search(r"\b(?:detector\s+)?(D\s*[0-9]{1,3}[A-Z]?)\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    token = _semantic_token(match.group(1))
    return f"detector_{token}" if token else None


def _signal_group_ref(text: str) -> str | None:
    match = re.search(r"\b(?:signal\s*group|sg)\s*([A-Z0-9]{1,4})\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    token = _semantic_token(match.group(1))
    return f"signal_group_{token}" if token else None


def _approach_ref(text: str) -> str | None:
    token = _slug_token(text)
    return f"approach_{token}" if token else None


def _label_ref(text: str) -> str | None:
    token = _slug_token(text)
    return f"label_{token}" if token else None


def _semantic_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", value).upper()


def _slug_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _lane_output(lane: LaneItem) -> dict[str, Any]:
    output = {
        "lane_ref": lane.lane_ref,
        "intersection_ref": lane.intersection_ref,
        "lane_index": lane.lane_index,
        "source_fact_id": lane.item.fact.get("fact_id"),
        "source_fact_name": lane.item.fact.get("fact_name"),
        "source_file": lane.item.fact.get("source_file"),
        "coordinate_space": lane.item.coordinate_space,
        "page_ref": lane.item.page_ref,
        "centroid": {"x": lane.item.centroid[0], "y": lane.item.centroid[1]},
        "bounds": lane.item.bounds,
        "clustered_from": lane.item.fact.get("clustered_from"),
    }
    if lane_semantic_hint := _cad_arrow_lane_hint(lane.item.fact):
        output["lane_semantic_hint"] = lane_semantic_hint
        output["lane_semantic_basis"] = "cad_signal_arrow_direction"
        output["requires_context_match"] = True
    value = _fact_value(lane.item.fact)
    if isinstance(value, dict) and lane.item.fact.get("fact_name") == "semantic_movement_lane_proxy":
        for key in ("movement_ref", "movement_text", "road_name", "direction", "maneuver", "phase_ref"):
            if value.get(key) is not None:
                output[key] = value.get(key)
        output["lane_semantic_basis"] = "structured_movement_without_geometry"
        output["requires_context_match"] = True
    return output


def _unassigned_geometry_count(facts: list[dict[str, Any]], assigned_facts: list[dict[str, Any]]) -> int:
    assigned_ids = {fact.get("fact_id") for fact in assigned_facts}
    count = 0
    for fact in facts:
        if fact.get("fact_name") in ASSIGNABLE_GEOMETRY_FACT_NAMES and fact.get("fact_id") not in assigned_ids:
            count += 1
    return count


def _unassigned_semantic_count(facts: list[dict[str, Any]], semantic_assignments: list[dict[str, Any]]) -> int:
    assigned_ids = {fact.get("fact_id") for fact in semantic_assignments}
    count = 0
    for fact in facts:
        if _is_semantic_fact(fact) and fact.get("fact_id") not in assigned_ids:
            count += 1
    return count


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def stable_assignment_id(*parts: object) -> str:
    encoded = "|".join(str(part) for part in parts)
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:12]


def default_assignment_output_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / "geometry_assignments.partial.json"
