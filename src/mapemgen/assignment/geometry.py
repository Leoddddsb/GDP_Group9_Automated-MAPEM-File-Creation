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
CAD_LANE_MERGE_DISTANCE = 3.0
CAD_LANE_ANGLE_TOLERANCE_DEG = 20.0
APPROACH_LANE_PERPENDICULAR_DISTANCE = 15.0
APPROACH_LANE_CENTROID_DISTANCE = 140.0
NEARBY_CONFIRMED_APPROACH_ADOPTION_DISTANCE = 140.0
OUT_OF_SCOPE_CONFIRMED_CONTEXT_DISTANCE = 180.0
CAD_LANE_LAYER_KEYWORDS = (
    "lane",
)
CAD_TOPOGRAPHIC_SOURCE_PATTERNS = (
    "os-topo",
    "os_topo",
    "topo",
)
CAD_BACKGROUND_OR_NON_VEHICLE_LANE_PATTERNS = (
    "cycle",
    "coloured",
    "colored",
    "footway",
    "r_cl",
    "osbase",
    "exbase",
    "topo",
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
LANE_VALIDATION_GROUPS_BY_FACT_NAME = {
    "stop_line_from_cad": "stop_line",
    "cad_signal_head_candidate": "signal_head",
    "signal_geometry_candidate_from_cad": "signal_geometry",
    "cad_arrow_block_candidate": "arrow",
    "cad_movement_label_candidate": "movement_label",
    "cad_lane_use_label_candidate": "lane_text",
    "cad_pole_candidate": "pole",
    "road_marking_candidate_from_cad": "road_marking",
}
LANE_CONFIRMATION_GROUPS = {
    "stop_line",
    "signal_head",
    "signal_geometry",
    "arrow",
    "movement_label",
    "lane_text",
    "road_text",
    "cad_block",
    "pole",
    "road_marking",
}
MIN_LANE_CONFIRMATION_GROUPS = 2
MAX_LANE_VALIDATION_EVIDENCE_FACT_IDS = 20
MAX_NEAREST_LANE_VALIDATION_CANDIDATES = 5
CAD_MARKING_LANE_MIN_LENGTH = 20.0
CAD_MARKING_LANE_MERGE_DISTANCE = 20.0
CAD_MARKING_LANE_ANCHOR_DISTANCE = 45.0
CAD_MARKING_LANE_MIN_ANCHOR_GROUPS = 2

ASSIGNABLE_GEOMETRY_FACT_NAMES = {
    "lane_geometry_candidate_from_cad",
    "lane_facility_geometry_candidate_from_cad",
    "cad_geometry_candidate",
    "cad_context_geometry_candidate",
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
    "road_marking_candidate_from_cad",
    "crossing_candidate_from_cad",
    "signal_geometry_candidate_from_cad",
    "detector_loop_candidate_from_cad",
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


@dataclass(frozen=True)
class ApproachItem:
    approach_ref: str
    intersection_ref: str
    lane_refs: list[str]
    coordinate_space: str
    page_ref: str | None
    source_file: str | None
    centroid: tuple[float, float]
    bounds: dict[str, float]
    angle: float


def assign_geometry_to_lanes(extracted_facts: dict[str, Any]) -> dict[str, Any]:
    """Assign geometry facts to intersection and lane scopes.

    This stage does not map facts to MAPEM fields. It only adds spatial scope
    references that later matching/fusion can use.
    """

    facts = _flatten_facts(extracted_facts)
    intersections = _build_intersections(extracted_facts, facts)
    site_id = str(extracted_facts.get("site_id", ""))
    facts = _add_anchored_cad_marking_lane_candidates(facts, site_id)
    lane_items, lane_tier = _build_lanes(facts, intersections, site_id)
    if _add_semantic_movement_lane_proxies(facts, intersections, lane_items, site_id) and lane_tier == -1:
        lane_tier = 4
    approach_items = _build_approaches(lane_items)
    lane_approach_refs = _lane_approach_ref_index(approach_items)
    assigned_facts = _assign_facts(facts, intersections, lane_items, lane_approach_refs)
    semantic_assignments = _assign_semantic_facts(facts, intersections)
    movement_lane_mappings = _build_movement_lane_mappings(facts, lane_items, assigned_facts)
    lane_validations, approach_validations = _validate_lane_context(lane_items, approach_items, assigned_facts, facts)
    lane_outputs = [_lane_output(lane, lane_validations.get(lane.lane_ref)) for lane in lane_items]
    approach_outputs = [_approach_output(approach, approach_validations.get(approach.approach_ref)) for approach in approach_items]
    return {
        "site_id": str(extracted_facts.get("site_id", "")),
        "intersections": intersections,
        "approaches": approach_outputs,
        "lanes": lane_outputs,
        "assigned_facts": assigned_facts,
        "semantic_assignments": semantic_assignments,
        "movement_lane_mappings": movement_lane_mappings,
        "assignment_method_audit": _build_assignment_method_audit(
            lane_outputs,
            assigned_facts,
            semantic_assignments,
            movement_lane_mappings,
        ),
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
            "Heuristic CAD lanes are marked as confirmed only when two or more independent CAD context evidence groups are assigned to the same lane.",
            "Parallel heuristic CAD lanes in the same CAD modelspace are grouped into approaches; confirmed approach context can confirm all lanes in that approach.",
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


def _add_anchored_cad_marking_lane_candidates(facts: list[dict[str, Any]], site_id: str) -> list[dict[str, Any]]:
    additions: list[dict[str, Any]] = []
    anchor_items: list[tuple[GeometryItem, str]] = []
    for fact in facts:
        group = _lane_validation_group(fact)
        if group is None or group == "road_marking":
            continue
        item = _geometry_item(fact)
        if item is not None:
            anchor_items.append((item, group))

    for fact in facts:
        if fact.get("fact_name") != "road_marking_candidate_from_cad":
            continue
        if not _is_cad_lane_source_allowed(fact, site_id):
            continue
        item = _geometry_item(fact)
        if item is None or _geometry_item_length(item) < CAD_MARKING_LANE_MIN_LENGTH:
            continue
        groups = _nearby_anchor_groups(item, anchor_items)
        if len(groups) < CAD_MARKING_LANE_MIN_ANCHOR_GROUPS:
            continue
        additions.append(_promoted_cad_marking_lane_fact(fact, groups))
    return [*facts, *additions]


def _nearby_anchor_groups(item: GeometryItem, anchors: list[tuple[GeometryItem, str]]) -> set[str]:
    groups: set[str] = set()
    for anchor, group in anchors:
        if anchor.fact.get("source_file") != item.fact.get("source_file"):
            continue
        if anchor.coordinate_space != item.coordinate_space:
            continue
        if anchor.page_ref != item.page_ref:
            continue
        if _distance(item.centroid, anchor.centroid) <= CAD_MARKING_LANE_ANCHOR_DISTANCE:
            groups.add(group)
    return groups


def _promoted_cad_marking_lane_fact(fact: dict[str, Any], anchor_groups: set[str]) -> dict[str, Any]:
    value = _fact_value(fact)
    geometry = value.get("geometry") if isinstance(value, dict) else value
    layer = value.get("layer") if isinstance(value, dict) else _cad_layer_name(fact)
    promoted = dict(fact)
    promoted["fact_id"] = "promoted_lane_" + stable_assignment_id(fact.get("fact_id"), fact.get("evidence_location"))
    promoted["fact_name"] = "lane_geometry_candidate_from_cad"
    promoted["payload"] = {
        "value": {
            "geometry": geometry,
            "layer": layer,
            "semantic_type": "lane_centreline_candidate",
            "recognition_basis": "anchored_cad_road_marking_lane_candidate",
            "requires_context_match": True,
            "promoted_from_fact_id": fact.get("fact_id"),
            "anchor_groups": sorted(anchor_groups),
        }
    }
    promoted["confidence"] = min(float(fact.get("confidence") or 0.6), 0.65)
    return promoted


def _geometry_item_length(item: GeometryItem) -> float:
    points = _geometry_item_points(item)
    length = 0.0
    for first, second in zip(points, points[1:]):
        length += _distance(first, second)
    return length


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


def _select_lane_tier(facts: list[dict[str, Any]], site_id: str = "") -> tuple[set[str] | None, int]:
    for tier_index, tier in enumerate(LANE_DEFINING_TIERS):
        if any(fact.get("fact_name") in tier and _can_define_lane(fact, site_id) for fact in facts):
            return tier, tier_index
    return None, -1


def _build_lanes(facts: list[dict[str, Any]], intersections: list[dict[str, Any]], site_id: str = "") -> tuple[list[LaneItem], int]:
    for tier_index, tier in enumerate(LANE_DEFINING_TIERS):
        if not any(fact.get("fact_name") in tier and _can_define_lane(fact, site_id) for fact in facts):
            continue
        items: list[GeometryItem] = []
        for fact in facts:
            if fact.get("fact_name") not in tier:
                continue
            if not _can_define_lane(fact, site_id):
                continue
            item = _geometry_item(fact)
            if item is not None:
                items.append(item)

        if tier_index == 0:
            items = _cluster_heuristic_cad_lane_lines(items, intersections)

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


def _build_approaches(lanes: list[LaneItem]) -> list[ApproachItem]:
    groups: list[list[LaneItem]] = []
    for lane in lanes:
        placed = False
        for group in groups:
            if _lane_fits_approach_group(lane, group):
                group.append(lane)
                placed = True
                break
        if not placed:
            groups.append([lane])

    approaches: list[ApproachItem] = []
    for index, group in enumerate(groups, start=1):
        bounds = {
            "min_x": min(lane.item.bounds["min_x"] for lane in group),
            "min_y": min(lane.item.bounds["min_y"] for lane in group),
            "max_x": max(lane.item.bounds["max_x"] for lane in group),
            "max_y": max(lane.item.bounds["max_y"] for lane in group),
        }
        centroid = (
            sum(lane.item.centroid[0] for lane in group) / len(group),
            sum(lane.item.centroid[1] for lane in group) / len(group),
        )
        approaches.append(
            ApproachItem(
                approach_ref=f"approach_{index}",
                intersection_ref=group[0].intersection_ref,
                lane_refs=[lane.lane_ref for lane in group],
                coordinate_space=group[0].item.coordinate_space,
                page_ref=group[0].item.page_ref,
                source_file=group[0].item.fact.get("source_file"),
                centroid=centroid,
                bounds=bounds,
                angle=_mean_angle([lane.item for lane in group]),
            )
        )
    return approaches


def _lane_fits_approach_group(lane: LaneItem, group: list[LaneItem]) -> bool:
    sample = group[0]
    if lane.intersection_ref != sample.intersection_ref:
        return False
    if lane.item.coordinate_space != sample.item.coordinate_space:
        return False
    if lane.item.page_ref != sample.item.page_ref:
        return False
    if lane.item.fact.get("source_file") != sample.item.fact.get("source_file"):
        return False
    if not _angle_close(_segment_orientation(lane.item), _mean_angle([item.item for item in group]), CAD_LANE_ANGLE_TOLERANCE_DEG):
        return False
    return any(_lanes_are_same_approach(lane, candidate) for candidate in group)


def _lanes_are_same_approach(first: LaneItem, second: LaneItem) -> bool:
    if _distance(first.item.centroid, second.item.centroid) > APPROACH_LANE_CENTROID_DISTANCE:
        return False
    return _perpendicular_lane_distance(first.item, second.item) <= APPROACH_LANE_PERPENDICULAR_DISTANCE


def _perpendicular_lane_distance(first: GeometryItem, second: GeometryItem) -> float:
    angle = math.radians(_segment_orientation(first))
    normal = (-math.sin(angle), math.cos(angle))
    dx = second.centroid[0] - first.centroid[0]
    dy = second.centroid[1] - first.centroid[1]
    return abs(dx * normal[0] + dy * normal[1])


def _lane_approach_ref_index(approaches: list[ApproachItem]) -> dict[str, str]:
    index: dict[str, str] = {}
    for approach in approaches:
        for lane_ref in approach.lane_refs:
            index[lane_ref] = approach.approach_ref
    return index


def _add_semantic_movement_lane_proxies(
    facts: list[dict[str, Any]],
    intersections: list[dict[str, Any]],
    lanes: list[LaneItem],
    site_id: str = "",
) -> bool:
    if any(not _is_fallback_lane_proxy(lane) for lane in lanes):
        return False
    covered_refs = set(_lane_movement_index(lanes))
    covered_arrow_hints = set(_lane_arrow_maneuver_index(lanes))
    added = False
    seen: set[str] = set()
    for fact in facts:
        if _is_disallowed_cad_semantic_lane_source(fact, site_id):
            continue
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


def _is_disallowed_cad_semantic_lane_source(fact: dict[str, Any], site_id: str) -> bool:
    if fact.get("fact_name") != "cad_movement_label_candidate":
        return False
    return not _is_cad_lane_source_allowed(fact, site_id)


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


def _can_define_lane(fact: dict[str, Any], site_id: str = "") -> bool:
    fact_name = str(fact.get("fact_name") or "")
    if fact_name == "lane_geometry_candidate_from_cad":
        return _is_cad_lane_source_allowed(fact, site_id) and _is_cad_lane_layer(fact)
    if fact_name == "cad_arrow_block_candidate":
        return _is_cad_lane_source_allowed(fact, site_id) and _cad_arrow_lane_hint(fact) is not None
    return fact_name in LANE_FACT_NAMES


def _is_cad_lane_source_allowed(fact: dict[str, Any], site_id: str) -> bool:
    source_file = str(fact.get("source_file") or "")
    if _is_topographic_cad_source(source_file):
        return False
    if not _cad_source_matches_site(source_file, site_id):
        return False
    layer = _cad_layer_name(fact) or ""
    if _is_background_or_non_vehicle_lane_layer(layer):
        return False
    value = _fact_value(fact)
    if isinstance(value, dict):
        payload_layer = str(value.get("layer") or "")
        if _is_background_or_non_vehicle_lane_layer(payload_layer):
            return False
    return True


def _is_topographic_cad_source(source_file: str) -> bool:
    name = Path(source_file).name.lower()
    return any(pattern in name for pattern in CAD_TOPOGRAPHIC_SOURCE_PATTERNS)


def _cad_source_matches_site(source_file: str, site_id: str) -> bool:
    normalized_site = _normalized_site_token(site_id)
    if not normalized_site:
        return True
    name = Path(source_file).name
    tokens = [_normalized_site_token(match.group(1)) for match in re.finditer(r"(?<!\d)(T?\d{3,4}L?)(?!\d)", name, flags=re.IGNORECASE)]
    tokens = [token for token in tokens if token]
    return not tokens or normalized_site in tokens


def _normalized_site_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()
    if token.startswith("T") and token[1:].isdigit():
        token = token[1:]
    if token.endswith("L") and token[:-1].isdigit():
        return token
    return token


def _is_background_or_non_vehicle_lane_layer(layer: str) -> bool:
    lowered = layer.lower()
    return any(pattern in lowered for pattern in CAD_BACKGROUND_OR_NON_VEHICLE_LANE_PATTERNS)


def _is_cad_lane_layer(fact: dict[str, Any]) -> bool:
    value = _fact_value(fact)
    if isinstance(value, dict) and value.get("semantic_type") == "lane_centreline_candidate":
        return True
    layer = _cad_layer_name(fact)
    if not layer:
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


def _cluster_heuristic_cad_lane_lines(items: list[GeometryItem], intersections: list[dict[str, Any]]) -> list[GeometryItem]:
    explicit_items = [item for item in items if not _is_heuristic_cad_lane_item(item)]
    layer_heuristic_items = [item for item in items if _cad_lane_recognition_basis(item) == "cad_layer_geometry_heuristic"]
    marking_heuristic_items = [item for item in items if _cad_lane_recognition_basis(item) == "anchored_cad_road_marking_lane_candidate"]
    if not layer_heuristic_items and not marking_heuristic_items:
        return explicit_items
    clustered: list[GeometryItem] = list(explicit_items)
    for group in _cad_lane_item_groups(layer_heuristic_items, intersections):
        clustered.extend(
            _cluster_lane_line_group(
                group,
                merge_distance=CAD_LANE_MERGE_DISTANCE,
                angle_tolerance=CAD_LANE_ANGLE_TOLERANCE_DEG,
            )
        )
    for group in _cad_lane_item_groups(marking_heuristic_items, intersections):
        clustered.extend(
            _cluster_lane_line_group(
                group,
                merge_distance=CAD_MARKING_LANE_MERGE_DISTANCE,
                angle_tolerance=CAD_LANE_ANGLE_TOLERANCE_DEG,
            )
        )
    return clustered


def _cad_lane_item_groups(items: list[GeometryItem], intersections: list[dict[str, Any]]) -> list[list[GeometryItem]]:
    grouped: dict[tuple[str, str], list[GeometryItem]] = {}
    for item in items:
        key = (_nearest_intersection_ref(item, intersections), item.coordinate_space)
        grouped.setdefault(key, []).append(item)
    return list(grouped.values())


def _cad_lane_recognition_basis(item: GeometryItem) -> str | None:
    value = _fact_value(item.fact)
    if not isinstance(value, dict):
        return None
    basis = value.get("recognition_basis")
    return str(basis) if basis is not None else None


def _is_heuristic_cad_lane_item(item: GeometryItem) -> bool:
    return (
        item.fact.get("fact_name") == "lane_geometry_candidate_from_cad"
        and _cad_lane_recognition_basis(item) in {"cad_layer_geometry_heuristic", "anchored_cad_road_marking_lane_candidate"}
    )


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
    if isinstance(value, dict) and isinstance(value.get("geometry"), (dict, list)):
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
    lane_approach_refs: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    assigned: list[dict[str, Any]] = []
    lane_index = _lane_index(lanes)
    lane_approach_refs = lane_approach_refs or {}
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
                "approach_ref": lane_approach_refs.get(lane.lane_ref) if lane is not None else None,
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


def _build_assignment_method_audit(
    lanes: list[dict[str, Any]],
    assigned_facts: list[dict[str, Any]],
    semantic_assignments: list[dict[str, Any]],
    movement_lane_mappings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    confirmed_lanes = [lane for lane in lanes if lane.get("lane_validation_status") == "cad_context_confirmed"]
    unconfirmed_lanes = [lane for lane in lanes if lane.get("lane_validation_status") == "needs_context_match"]
    approach_confirmed_lanes = [
        lane
        for lane in confirmed_lanes
        if lane.get("lane_confirmation_basis") == "approach_context_validation"
    ]
    cad_movement_mappings = [
        mapping
        for mapping in movement_lane_mappings
        if mapping.get("assignment_method") == "cad_movement_label_nearest_lane"
    ]
    semantic_bridge_mappings = [
        mapping
        for mapping in movement_lane_mappings
        if mapping.get("lane_ref") and mapping.get("phase_refs")
    ]
    arrow_mappings = [
        mapping
        for mapping in movement_lane_mappings
        if mapping.get("assignment_method") == "cad_signal_arrow_direction_match"
    ]
    semantic_proxy_mappings = [
        mapping
        for mapping in movement_lane_mappings
        if mapping.get("assignment_method") == "semantic_movement_lane_proxy"
    ]
    pdf_lane_assignments = [
        assignment
        for assignment in assigned_facts
        if ((assignment.get("geometry_summary") or {}).get("coordinate_space") == "pdf_page")
        and ((assignment.get("target_scope") or {}).get("lane_ref"))
    ]
    pdf_unmatched = [
        assignment
        for assignment in assigned_facts
        if ((assignment.get("geometry_summary") or {}).get("coordinate_space") == "pdf_page")
        and not ((assignment.get("target_scope") or {}).get("lane_ref"))
    ]
    gis_unmatched = [
        assignment
        for assignment in assigned_facts
        if ((assignment.get("geometry_summary") or {}).get("coordinate_space") == "geographic_or_gis")
        and not ((assignment.get("target_scope") or {}).get("lane_ref"))
    ]

    return [
        {
            "method": "cad_context_validation",
            "status": "effective" if confirmed_lanes else "no_confirmed_lanes",
            "matched_count": len(confirmed_lanes),
            "candidate_count": len(confirmed_lanes) + len(unconfirmed_lanes),
            "examples": [_lane_audit_example(lane) for lane in confirmed_lanes[:3]],
            "notes": "Confirms heuristic CAD lanes using stop lines, signal heads, arrows, CAD blocks/text, poles, and road markings assigned to the same lane or the same confirmed approach in the same CAD modelspace.",
        },
        {
            "method": "cad_approach_context_validation",
            "status": "effective" if approach_confirmed_lanes else "no_approach_confirmed_lanes",
            "matched_count": len(approach_confirmed_lanes),
            "candidate_count": len(confirmed_lanes) + len(unconfirmed_lanes),
            "examples": [_lane_audit_example(lane) for lane in approach_confirmed_lanes[:3]],
            "notes": "Groups nearby parallel CAD lanes into approaches and uses shared approach context to confirm lanes that do not each have independent context evidence.",
        },
        {
            "method": "cad_movement_label_nearest_lane",
            "status": "effective_but_review_labels" if cad_movement_mappings else "no_cad_movement_label_matches",
            "matched_count": len(cad_movement_mappings),
            "candidate_count": len([m for m in movement_lane_mappings if m.get("source_fact_name") == "cad_movement_label_candidate"]),
            "examples": [_movement_audit_example(mapping) for mapping in cad_movement_mappings[:3]],
            "notes": "Uses CAD movement text with modelspace coordinates. Review examples because CAD legends/keys can look like movement labels.",
        },
        {
            "method": "semantic_movement_to_cad_lane_bridge",
            "status": "effective" if semantic_bridge_mappings else "no_phase_movement_lane_bridge",
            "matched_count": len(semantic_bridge_mappings),
            "candidate_count": len(movement_lane_mappings),
            "examples": [_movement_audit_example(mapping) for mapping in semantic_bridge_mappings[:3]],
            "notes": "Works when controller/UTC movement_ref can be connected to an assigned CAD movement label or lane label, preserving phase_refs.",
        },
        {
            "method": "cad_signal_arrow_direction_match",
            "status": "fallback_effective" if arrow_mappings else "no_arrow_direction_matches",
            "matched_count": len(arrow_mappings),
            "candidate_count": len(movement_lane_mappings),
            "examples": [_movement_audit_example(mapping) for mapping in arrow_mappings[:3]],
            "notes": "Fallback only. Directional arrow can support left/right/ahead movement but still requires context review.",
        },
        {
            "method": "semantic_movement_lane_proxy",
            "status": "fallback_used" if semantic_proxy_mappings else "not_used",
            "matched_count": len(semantic_proxy_mappings),
            "candidate_count": len(movement_lane_mappings),
            "examples": [_movement_audit_example(mapping) for mapping in semantic_proxy_mappings[:3]],
            "notes": "Last-resort stable lane_ref for movements without geometry. It is not real lane geometry.",
        },
        {
            "method": "pdf_same_page_assignment",
            "status": "effective" if pdf_lane_assignments else "no_pdf_lane_same_page_matches",
            "matched_count": len(pdf_lane_assignments),
            "candidate_count": len(pdf_lane_assignments) + len(pdf_unmatched),
            "examples": [_assignment_audit_example(assignment) for assignment in pdf_lane_assignments[:3]],
            "notes": "Only assigns PDF facts to lanes in the same PDF file/page coordinate space.",
        },
        {
            "method": "pdf_to_cad_transform_required",
            "status": "blocked_without_transform" if pdf_unmatched else "not_needed",
            "matched_count": 0,
            "candidate_count": len(pdf_unmatched),
            "examples": [
                _assignment_audit_example(assignment, reason="pdf_page_without_cad_transform")
                for assignment in pdf_unmatched[:3]
            ],
            "notes": "PDF page coordinates cannot be safely assigned to CAD modelspace lanes until a PDF-to-CAD transform is available.",
        },
        {
            "method": "gis_to_cad_transform_required",
            "status": "blocked_without_transform" if gis_unmatched else "not_needed",
            "matched_count": 0,
            "candidate_count": len(gis_unmatched),
            "examples": [
                _assignment_audit_example(assignment, reason="gis_without_cad_transform")
                for assignment in gis_unmatched[:3]
            ],
            "notes": "GIS/geographic coordinates cannot be safely assigned to CAD modelspace lanes without a coordinate transform or shared reference.",
        },
    ]


def _lane_audit_example(lane: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane_ref": lane.get("lane_ref"),
        "source_file": lane.get("source_file"),
        "source_fact_name": lane.get("source_fact_name"),
        "lane_validation_status": lane.get("lane_validation_status"),
        "requires_context_match": lane.get("requires_context_match"),
        "validation_evidence_groups": lane.get("validation_evidence_groups"),
        "validation_evidence_counts": lane.get("validation_evidence_counts"),
    }


def _movement_audit_example(mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        "movement_ref": mapping.get("movement_ref"),
        "movement_text": mapping.get("movement_text"),
        "phase_refs": mapping.get("phase_refs"),
        "lane_ref": mapping.get("lane_ref"),
        "source_fact_name": mapping.get("source_fact_name"),
        "source_file": mapping.get("source_file"),
        "evidence_location": mapping.get("evidence_location"),
        "assignment_method": mapping.get("assignment_method"),
        "requires_context_match": mapping.get("requires_context_match"),
    }


def _assignment_audit_example(assignment: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
    target_scope = assignment.get("target_scope") or {}
    geometry_summary = assignment.get("geometry_summary") or {}
    example = {
        "fact_id": assignment.get("fact_id"),
        "fact_name": assignment.get("fact_name"),
        "source_file": assignment.get("source_file"),
        "evidence_location": assignment.get("evidence_location"),
        "lane_ref": target_scope.get("lane_ref"),
        "intersection_ref": target_scope.get("intersection_ref"),
        "coordinate_space": geometry_summary.get("coordinate_space"),
        "page_ref": geometry_summary.get("page_ref"),
        "assignment_method": assignment.get("assignment_method"),
    }
    if reason is not None:
        example["reason"] = reason
    return example


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
        unmatched_reason = "no_lane_movement_label"
        if lane is None and fact.get("fact_name") == "cad_movement_label_candidate":
            if _cad_movement_label_supports_lane_mapping(fact):
                assignment = assignment_by_fact_id.get(fact.get("fact_id"))
                lane_ref = ((assignment or {}).get("target_scope") or {}).get("lane_ref")
                lane = lane_by_ref.get(lane_ref)
                if lane is not None:
                    assignment_method = "cad_movement_label_nearest_lane"
            else:
                unmatched_reason = "cad_movement_label_on_key_or_notes_layer"
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
            mapping["unmatched_reason"] = unmatched_reason
        mappings.append(mapping)
    matched_movement_refs = {mapping["movement_ref"] for mapping in mappings if mapping.get("lane_ref")}
    return [
        mapping
        for mapping in mappings
        if mapping.get("lane_ref") or mapping["movement_ref"] not in matched_movement_refs
    ]


def _validate_lane_context(
    lanes: list[LaneItem],
    approaches: list[ApproachItem],
    assigned_facts: list[dict[str, Any]],
    facts: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    fact_by_id = {fact.get("fact_id"): fact for fact in facts}
    lane_by_ref = {lane.lane_ref: lane for lane in lanes}
    evidence_by_lane: dict[str, dict[str, list[dict[str, str]]]] = {
        lane.lane_ref: {group: [] for group in LANE_CONFIRMATION_GROUPS}
        for lane in lanes
        if _is_heuristic_cad_lane_item(lane.item)
    }
    if not evidence_by_lane:
        return {}, {}

    for assignment in assigned_facts:
        target_scope = assignment.get("target_scope") or {}
        lane_ref = target_scope.get("lane_ref")
        if lane_ref not in evidence_by_lane:
            continue
        lane = lane_by_ref[lane_ref]
        if assignment.get("fact_id") == lane.item.fact.get("fact_id"):
            continue
        if assignment.get("source_file") != lane.item.fact.get("source_file"):
            continue
        geometry_summary = assignment.get("geometry_summary") or {}
        if geometry_summary.get("coordinate_space") != lane.item.coordinate_space:
            continue
        fact = fact_by_id.get(assignment.get("fact_id"))
        if fact is None:
            continue
        group = _lane_validation_group(fact)
        if group is None:
            continue
        evidence_by_lane[lane_ref][group].append(
            {
                "fact_id": str(fact.get("fact_id")),
                "evidence_location": str(fact.get("evidence_location") or ""),
            }
        )

    approach_validations = _validate_approach_context(approaches, evidence_by_lane)
    approach_by_lane = {
        lane_ref: approach
        for approach in approaches
        for lane_ref in approach.lane_refs
    }
    validations: dict[str, dict[str, Any]] = {}
    nearest_candidates = _nearest_lane_validation_candidates(lane_by_ref, evidence_by_lane, assigned_facts, facts)
    for lane_ref, evidence in evidence_by_lane.items():
        groups = sorted(group for group, items in evidence.items() if items)
        fact_ids = sorted({item["fact_id"] for items in evidence.values() for item in items})
        evidence_locations = {
            item["evidence_location"]
            for items in evidence.values()
            for item in items
            if item["evidence_location"]
        }
        confirmed = (
            len(set(groups) & LANE_CONFIRMATION_GROUPS) >= MIN_LANE_CONFIRMATION_GROUPS
            and len(evidence_locations) >= MIN_LANE_CONFIRMATION_GROUPS
        )
        approach = approach_by_lane.get(lane_ref)
        approach_validation = approach_validations.get(approach.approach_ref) if approach is not None else None
        approach_confirmed = (
            approach_validation is not None
            and approach_validation.get("approach_validation_status") == "cad_context_confirmed"
        )
        final_confirmed = confirmed or approach_confirmed
        validation_groups = groups
        validation_counts = {
            group: len(items)
            for group, items in sorted(evidence.items())
            if items
        }
        validation_fact_ids = fact_ids
        if approach_confirmed and approach_validation is not None:
            validation_groups = sorted(set(groups) | set(approach_validation.get("validation_evidence_groups") or []))
            validation_counts = dict(approach_validation.get("validation_evidence_counts") or validation_counts)
            validation_fact_ids = sorted(set(fact_ids) | set(approach_validation.get("validation_evidence_fact_ids") or []))
        validations[lane_ref] = {
            "lane_validation_status": "cad_context_confirmed" if final_confirmed else "needs_context_match",
            "lane_confirmation_basis": "direct_lane_context_validation" if confirmed else "approach_context_validation" if approach_confirmed else "insufficient_context",
            "requires_context_match": not final_confirmed,
            "approach_ref": approach.approach_ref if approach is not None else None,
            "validation_evidence_groups": validation_groups,
            "validation_evidence_counts": validation_counts,
            "validation_evidence_fact_ids": validation_fact_ids[:MAX_LANE_VALIDATION_EVIDENCE_FACT_IDS],
            "validation_evidence_fact_count": len(validation_fact_ids),
        }
        if not final_confirmed:
            validations[lane_ref].update(
                {
                    "unconfirmed_reason": _lane_unconfirmed_reason(groups, evidence_locations),
                    "missing_validation_evidence_group_count": max(0, MIN_LANE_CONFIRMATION_GROUPS - len(set(groups) & LANE_CONFIRMATION_GROUPS)),
                    "nearest_validation_candidates": nearest_candidates.get(lane_ref, []),
                }
            )
    _apply_nearby_confirmed_approach_adoption(validations, nearest_candidates, approach_by_lane, approach_validations)
    _apply_distant_out_of_scope_classification(validations, nearest_candidates, approach_by_lane, approach_validations)
    return validations, approach_validations


def _apply_nearby_confirmed_approach_adoption(
    validations: dict[str, dict[str, Any]],
    nearest_candidates: dict[str, list[dict[str, Any]]],
    approach_by_lane: dict[str, ApproachItem],
    approach_validations: dict[str, dict[str, Any]],
) -> None:
    for lane_ref, validation in validations.items():
        if validation.get("lane_validation_status") != "needs_context_match":
            continue
        candidate = _nearest_confirmed_approach_candidate(
            nearest_candidates.get(lane_ref, []),
            approach_by_lane,
            approach_validations,
        )
        if candidate is None:
            continue
        approach = candidate["approach"]
        approach_validation = approach_validations.get(approach.approach_ref) or {}
        validation.update(
            {
                "lane_validation_status": "cad_context_confirmed",
                "lane_confirmation_basis": "nearby_confirmed_approach_adoption",
                "requires_context_match": False,
                "adopted_from_approach_ref": approach.approach_ref,
                "adoption_evidence_fact_id": candidate["fact_id"],
                "adoption_evidence_group": candidate["group"],
                "adoption_distance_to_lane": candidate["distance_to_lane"],
                "validation_evidence_groups": sorted(
                    set(validation.get("validation_evidence_groups") or [])
                    | set(approach_validation.get("validation_evidence_groups") or [])
                ),
                "validation_evidence_counts": dict(approach_validation.get("validation_evidence_counts") or {}),
                "validation_evidence_fact_ids": list(approach_validation.get("validation_evidence_fact_ids") or [])[
                    :MAX_LANE_VALIDATION_EVIDENCE_FACT_IDS
                ],
                "validation_evidence_fact_count": int(approach_validation.get("validation_evidence_fact_count") or 0),
            }
        )
        validation.pop("unconfirmed_reason", None)
        validation.pop("missing_validation_evidence_group_count", None)


def _nearest_confirmed_approach_candidate(
    candidates: list[dict[str, Any]],
    approach_by_lane: dict[str, ApproachItem],
    approach_validations: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    eligible: list[dict[str, Any]] = []
    for candidate in candidates:
        distance = candidate.get("distance_to_lane")
        if not isinstance(distance, (int, float)) or distance > NEARBY_CONFIRMED_APPROACH_ADOPTION_DISTANCE:
            continue
        assigned_lane_ref = candidate.get("assigned_lane_ref")
        approach = approach_by_lane.get(str(assigned_lane_ref))
        if approach is None:
            continue
        approach_validation = approach_validations.get(approach.approach_ref) or {}
        if approach_validation.get("approach_validation_status") != "cad_context_confirmed":
            continue
        item = dict(candidate)
        item["approach"] = approach
        eligible.append(item)
    if not eligible:
        return None
    return min(eligible, key=lambda item: item["distance_to_lane"])


def _apply_distant_out_of_scope_classification(
    validations: dict[str, dict[str, Any]],
    nearest_candidates: dict[str, list[dict[str, Any]]],
    approach_by_lane: dict[str, ApproachItem],
    approach_validations: dict[str, dict[str, Any]],
) -> None:
    if not any(
        validation.get("approach_validation_status") == "cad_context_confirmed"
        for validation in approach_validations.values()
    ):
        return
    for lane_ref, validation in validations.items():
        if validation.get("lane_validation_status") != "needs_context_match":
            continue
        nearest_distance = _nearest_confirmed_approach_context_distance(
            nearest_candidates.get(lane_ref, []),
            approach_by_lane,
            approach_validations,
        )
        if nearest_distance is not None and nearest_distance <= OUT_OF_SCOPE_CONFIRMED_CONTEXT_DISTANCE:
            continue
        validation.update(
            {
                "lane_validation_status": "out_of_scope_candidate",
                "lane_confirmation_basis": "distant_insufficient_context",
                "requires_context_match": True,
                "out_of_scope_reason": "distant_from_confirmed_cad_context",
            }
        )


def _nearest_confirmed_approach_context_distance(
    candidates: list[dict[str, Any]],
    approach_by_lane: dict[str, ApproachItem],
    approach_validations: dict[str, dict[str, Any]],
) -> float | None:
    distances: list[float] = []
    for candidate in candidates:
        distance = candidate.get("distance_to_lane")
        if not isinstance(distance, (int, float)):
            continue
        assigned_lane_ref = candidate.get("assigned_lane_ref")
        approach = approach_by_lane.get(str(assigned_lane_ref))
        if approach is None:
            continue
        approach_validation = approach_validations.get(approach.approach_ref) or {}
        if approach_validation.get("approach_validation_status") == "cad_context_confirmed":
            distances.append(float(distance))
    return min(distances) if distances else None


def _validate_approach_context(
    approaches: list[ApproachItem],
    evidence_by_lane: dict[str, dict[str, list[dict[str, str]]]],
) -> dict[str, dict[str, Any]]:
    validations: dict[str, dict[str, Any]] = {}
    for approach in approaches:
        evidence: dict[str, list[dict[str, str]]] = {group: [] for group in LANE_CONFIRMATION_GROUPS}
        for lane_ref in approach.lane_refs:
            for group, items in evidence_by_lane.get(lane_ref, {}).items():
                evidence[group].extend(items)
        groups = sorted(group for group, items in evidence.items() if items)
        fact_ids = sorted({item["fact_id"] for items in evidence.values() for item in items})
        evidence_locations = {
            item["evidence_location"]
            for items in evidence.values()
            for item in items
            if item["evidence_location"]
        }
        confirmed = (
            len(set(groups) & LANE_CONFIRMATION_GROUPS) >= MIN_LANE_CONFIRMATION_GROUPS
            and len(evidence_locations) >= MIN_LANE_CONFIRMATION_GROUPS
        )
        validation = {
            "approach_validation_status": "cad_context_confirmed" if confirmed else "needs_context_match",
            "requires_context_match": not confirmed,
            "validation_evidence_groups": groups,
            "validation_evidence_counts": {
                group: len(items)
                for group, items in sorted(evidence.items())
                if items
            },
            "validation_evidence_fact_ids": fact_ids[:MAX_LANE_VALIDATION_EVIDENCE_FACT_IDS],
            "validation_evidence_fact_count": len(fact_ids),
        }
        if not confirmed:
            validation.update(
                {
                    "unconfirmed_reason": _lane_unconfirmed_reason(groups, evidence_locations),
                    "missing_validation_evidence_group_count": max(0, MIN_LANE_CONFIRMATION_GROUPS - len(set(groups) & LANE_CONFIRMATION_GROUPS)),
                }
            )
        validations[approach.approach_ref] = validation
    return validations


def _nearest_lane_validation_candidates(
    lane_by_ref: dict[str, LaneItem],
    evidence_by_lane: dict[str, dict[str, list[dict[str, str]]]],
    assigned_facts: list[dict[str, Any]],
    facts: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    fact_by_id = {fact.get("fact_id"): fact for fact in facts}
    candidates: dict[str, list[dict[str, Any]]] = {lane_ref: [] for lane_ref in evidence_by_lane}
    for assignment in assigned_facts:
        fact = fact_by_id.get(assignment.get("fact_id"))
        if fact is None:
            continue
        group = _lane_validation_group(fact)
        if group is None:
            continue
        item = _geometry_item(fact)
        if item is None:
            continue
        for lane_ref, lane in lane_by_ref.items():
            if lane_ref not in evidence_by_lane:
                continue
            if assignment.get("source_file") != lane.item.fact.get("source_file"):
                continue
            if item.coordinate_space != lane.item.coordinate_space:
                continue
            distance = _distance(item.centroid, lane.item.centroid)
            candidates[lane_ref].append(
                {
                    "fact_id": fact.get("fact_id"),
                    "fact_name": fact.get("fact_name"),
                    "group": group,
                    "source_file": fact.get("source_file"),
                    "evidence_location": fact.get("evidence_location"),
                    "distance_to_lane": round(distance, 3),
                    "assigned_lane_ref": (assignment.get("target_scope") or {}).get("lane_ref"),
                }
            )
    return {
        lane_ref: sorted(items, key=lambda item: item["distance_to_lane"])[:MAX_NEAREST_LANE_VALIDATION_CANDIDATES]
        for lane_ref, items in candidates.items()
    }


def _lane_unconfirmed_reason(groups: list[str], evidence_locations: set[str]) -> str:
    if not groups:
        return "no_cad_context_evidence"
    if len(evidence_locations) < MIN_LANE_CONFIRMATION_GROUPS:
        return "insufficient_distinct_cad_entity_locations"
    return "insufficient_independent_cad_context"


def _lane_validation_group(fact: dict[str, Any]) -> str | None:
    fact_name = str(fact.get("fact_name") or "")
    if fact_name in LANE_VALIDATION_GROUPS_BY_FACT_NAME:
        return LANE_VALIDATION_GROUPS_BY_FACT_NAME[fact_name]
    if fact_name == "cad_text_label" and _cad_text_supports_lane_validation(fact):
        return "road_text"
    if fact_name == "cad_block_reference" and _cad_block_supports_lane_validation(fact):
        return "cad_block"
    return None


def _cad_text_supports_lane_validation(fact: dict[str, Any]) -> bool:
    text = _fact_text(fact)
    return re.search(
        r"\b(?:road|rd|street|st|lane|ln|avenue|ave|drive|dr|way|inbound|outbound|left|right|ahead|straight|wb|eb|nb|sb)\b",
        text,
        flags=re.IGNORECASE,
    ) is not None


def _cad_block_supports_lane_validation(fact: dict[str, Any]) -> bool:
    value = _fact_value(fact)
    if not isinstance(value, dict):
        return False
    name = str(value.get("name") or "")
    return re.search(r"(?:^|[$_\s-])(?:HD[0-9]{3}[A-Z]*|Signal|Arrow|Pole|WBPOLE)(?:$|[^a-z0-9])", name, flags=re.IGNORECASE) is not None


def _cad_movement_label_supports_lane_mapping(fact: dict[str, Any]) -> bool:
    location = str(fact.get("evidence_location") or "")
    match = re.search(r"\blayer\s+(.+)$", location, flags=re.IGNORECASE)
    layer = match.group(1).strip().lower() if match else ""
    if re.search(r"(?:^|[$_\s-])(?:key|legend|note|notes|dim|dims|title)(?:[$_\s-]|$)", layer, flags=re.IGNORECASE):
        return False
    text = _fact_text(fact)
    return len(text.split()) <= 8


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


def _approach_output(approach: ApproachItem, validation: dict[str, Any] | None = None) -> dict[str, Any]:
    output = {
        "approach_ref": approach.approach_ref,
        "intersection_ref": approach.intersection_ref,
        "lane_refs": approach.lane_refs,
        "source_file": approach.source_file,
        "coordinate_space": approach.coordinate_space,
        "page_ref": approach.page_ref,
        "centroid": {"x": approach.centroid[0], "y": approach.centroid[1]},
        "bounds": approach.bounds,
        "angle": approach.angle,
    }
    if validation is not None:
        output.update(validation)
    return output


def _lane_output(lane: LaneItem, validation: dict[str, Any] | None = None) -> dict[str, Any]:
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
    if isinstance(value, dict) and value.get("requires_context_match"):
        output["requires_context_match"] = True
    if isinstance(value, dict) and value.get("recognition_basis"):
        output["lane_semantic_basis"] = value.get("recognition_basis")
    if isinstance(value, dict) and lane.item.fact.get("fact_name") == "semantic_movement_lane_proxy":
        for key in ("movement_ref", "movement_text", "road_name", "direction", "maneuver", "phase_ref"):
            if value.get(key) is not None:
                output[key] = value.get(key)
        output["lane_semantic_basis"] = "structured_movement_without_geometry"
        output["requires_context_match"] = True
    if validation is not None:
        output.update(validation)
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
