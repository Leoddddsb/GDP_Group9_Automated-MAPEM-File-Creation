from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LANE_FACT_NAMES = {
    "lane_geometry_candidate_from_cad",
    "lane_facility_geometry_candidate_from_cad",
    "lane_geometry_candidate_from_ordnance_survey",
    "lane_line_candidate_from_pdf_vector",
    "lane_line_candidate_from_pdf_cv",
}

ASSIGNABLE_GEOMETRY_FACT_NAMES = {
    "lane_geometry_candidate_from_cad",
    "lane_facility_geometry_candidate_from_cad",
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
    lane_items = _build_lanes(facts, intersections)
    assigned_facts = _assign_facts(facts, intersections, lane_items)
    return {
        "site_id": str(extracted_facts.get("site_id", "")),
        "intersections": intersections,
        "lanes": [_lane_output(lane) for lane in lane_items],
        "assigned_facts": assigned_facts,
        "unassigned_fact_count": _unassigned_geometry_count(facts, assigned_facts),
        "notes": [
            "Geometry assignment adds intersection_ref and lane_ref only.",
            "It does not choose MAPEM fields or build SiteModel.",
            "PDF page-space geometry is assigned only within the same PDF page coordinate space.",
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


def _build_lanes(facts: list[dict[str, Any]], intersections: list[dict[str, Any]]) -> list[LaneItem]:
    lanes: list[LaneItem] = []
    for fact in facts:
        if fact.get("fact_name") not in LANE_FACT_NAMES:
            continue
        item = _geometry_item(fact)
        if item is None:
            continue
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
    return lanes


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


def _geometry_item(fact: dict[str, Any]) -> GeometryItem | None:
    value = _fact_value(fact)
    if isinstance(value, dict) and isinstance(value.get("geometry"), dict):
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


def _lane_output(lane: LaneItem) -> dict[str, Any]:
    return {
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
    }


def _unassigned_geometry_count(facts: list[dict[str, Any]], assigned_facts: list[dict[str, Any]]) -> int:
    assigned_ids = {fact.get("fact_id") for fact in assigned_facts}
    count = 0
    for fact in facts:
        if fact.get("fact_name") in ASSIGNABLE_GEOMETRY_FACT_NAMES and fact.get("fact_id") not in assigned_ids:
            count += 1
    return count


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def stable_assignment_id(*parts: object) -> str:
    encoded = "|".join(str(part) for part in parts)
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:12]


def default_assignment_output_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / "geometry_assignments.partial.json"
