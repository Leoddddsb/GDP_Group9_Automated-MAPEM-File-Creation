from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from pyproj import Transformer


Point = tuple[float, float]
LatLon = dict[str, float]
_BNG_TO_WGS84_TRANSFORMER = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)


class TransformError(ValueError):
    """Raised when a transform cannot be applied safely."""


@dataclass(frozen=True)
class CoordinateReferenceAssessment:
    status: str
    crs: str | None
    area_hint: str | None
    confidence: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "crs": self.crs,
            "area_hint": self.area_hint,
            "confidence": self.confidence,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Basic identity and constant transforms
# ---------------------------------------------------------------------------


def protocol_version(value: int | None = None) -> int:
    return 2 if value is None else int(value)


def mapem_message_id(value: int | None = None) -> int:
    return 5 if value is None else int(value)


def project_revision(value: int | None = None, default: int = 1) -> int:
    revision = default if value is None else int(value)
    if revision < 0:
        raise TransformError("Revision must be non-negative.")
    return revision


def extract_digits(value: Any) -> int:
    match = re.search(r"\d+", str(value))
    if not match:
        raise TransformError(f"No digits found in {value!r}.")
    return int(match.group(0))


def extract_int_from_site_code(value: Any) -> int:
    """Convert an official site code such as '337L' or 'T1003' to an integer ID."""

    return extract_digits(value)


def normalise_identifier(value: Any) -> str:
    text = normalise_text(value)
    if not text:
        raise TransformError("Identifier is empty.")
    return text


def take_lat(value: Mapping[str, Any] | Sequence[Any]) -> float:
    point = as_lat_lon(value)
    return point["lat"]


def take_long(value: Mapping[str, Any] | Sequence[Any]) -> float:
    point = as_lat_lon(value)
    return point["lon"]


# ---------------------------------------------------------------------------
# Coordinate reference and coordinate conversion transforms
# ---------------------------------------------------------------------------


def as_point(value: Mapping[str, Any] | Sequence[Any]) -> Point:
    if isinstance(value, Mapping):
        for x_key, y_key in (
            ("x", "y"),
            ("east", "north"),
            ("easting", "northing"),
            ("east_m", "north_m"),
        ):
            if x_key in value and y_key in value:
                return float(value[x_key]), float(value[y_key])
        if "geometry" in value:
            return as_point(value["geometry"])
        raise TransformError(f"Cannot read point coordinates from keys {list(value)}.")
    if len(value) < 2:
        raise TransformError("Point sequence must contain at least two values.")
    return float(value[0]), float(value[1])


def as_lat_lon(value: Mapping[str, Any] | Sequence[Any]) -> LatLon:
    if isinstance(value, Mapping):
        if "lat" in value and "lon" in value:
            return {"lat": float(value["lat"]), "lon": float(value["lon"])}
        if "lat" in value and "long" in value:
            return {"lat": float(value["lat"]), "lon": float(value["long"])}
        if "latitude" in value and "longitude" in value:
            return {"lat": float(value["latitude"]), "lon": float(value["longitude"])}
    point = as_point(value)
    return {"lat": point[1], "lon": point[0]}


def coordinate_bounds(points: Iterable[Mapping[str, Any] | Sequence[Any]]) -> dict[str, float]:
    parsed = [as_point(point) for point in points]
    if not parsed:
        raise TransformError("Cannot calculate bounds for an empty point set.")
    xs = [point[0] for point in parsed]
    ys = [point[1] for point in parsed]
    return {
        "min_x": min(xs),
        "min_y": min(ys),
        "max_x": max(xs),
        "max_y": max(ys),
        "centre_x": (min(xs) + max(xs)) / 2.0,
        "centre_y": (min(ys) + max(ys)) / 2.0,
        "point_count": len(parsed),
    }


def assess_coordinate_reference(
    points: Iterable[Mapping[str, Any] | Sequence[Any]],
    min_bng_share: float = 0.20,
) -> CoordinateReferenceAssessment:
    """Assess whether CAD/GIS coordinates can be treated as British National Grid."""

    parsed = [as_point(point) for point in points]
    if not parsed:
        return CoordinateReferenceAssessment(
            status="unknown",
            crs=None,
            area_hint=None,
            confidence=0.0,
            reason="No coordinate points were available.",
        )

    total = len(parsed)
    leeds = [p for p in parsed if _in_leeds_bng(*p)]
    bath = [p for p in parsed if _in_bath_bng(*p)]
    local = [p for p in parsed if abs(p[0]) < 10000 and abs(p[1]) < 10000]

    if len(leeds) / total >= min_bng_share:
        return CoordinateReferenceAssessment(
            status="georeferenced",
            crs="EPSG:27700",
            area_hint="leeds_bng",
            confidence=min(0.95, 0.5 + len(leeds) / total),
            reason=f"{len(leeds)} of {total} points fall in the expected Leeds BNG range.",
        )
    if len(bath) / total >= min_bng_share:
        return CoordinateReferenceAssessment(
            status="georeferenced",
            crs="EPSG:27700",
            area_hint="bath_bng",
            confidence=min(0.95, 0.5 + len(bath) / total),
            reason=f"{len(bath)} of {total} points fall in the expected Bath/BANES BNG range.",
        )
    if len(local) / total >= 0.80:
        return CoordinateReferenceAssessment(
            status="local_coordinates",
            crs=None,
            area_hint=None,
            confidence=min(0.95, len(local) / total),
            reason=f"{len(local)} of {total} points look like local drawing coordinates.",
        )
    return CoordinateReferenceAssessment(
        status="unknown",
        crs=None,
        area_hint=None,
        confidence=0.30,
        reason="Coordinate ranges are mixed or do not match expected BNG/local patterns.",
    )


def bng_to_wgs84_OSTN15(point: Mapping[str, Any] | Sequence[Any]) -> LatLon:
    """Convert EPSG:27700 east/north metres to WGS84 lat/lon using pyproj."""

    east, north = as_point(point)
    lon, lat = _BNG_TO_WGS84_TRANSFORMER.transform(east, north)
    return {"lat": float(lat), "lon": float(lon)}


def wgs84_to_int_1e7(value: float) -> int:
    return int(round(float(value) * 10_000_000))


def relative_to_refpoint(
    point: Mapping[str, Any] | Sequence[Any],
    ref_point: Mapping[str, Any] | Sequence[Any],
) -> Point:
    """Return east/north metre offsets from a reference point."""

    if _looks_like_lat_lon(point) and _looks_like_lat_lon(ref_point):
        p = as_lat_lon(point)
        r = as_lat_lon(ref_point)
        return _lat_lon_offset_m(p["lat"], p["lon"], r["lat"], r["lon"])
    x, y = as_point(point)
    rx, ry = as_point(ref_point)
    return x - rx, y - ry


def delta_to_cm(offset: Mapping[str, Any] | Sequence[Any]) -> dict[str, int]:
    x, y = as_point(offset)
    return {"x": int(round(x * 100)), "y": int(round(y * 100))}


def choose_node_xy_precision(offsets: Iterable[Mapping[str, Any] | Sequence[Any]]) -> str:
    max_abs_cm = 0
    for offset in offsets:
        cm = delta_to_cm(offset)
        max_abs_cm = max(max_abs_cm, abs(cm["x"]), abs(cm["y"]))
    if max_abs_cm <= 511:
        return "node-XY1"
    if max_abs_cm <= 1023:
        return "node-XY2"
    if max_abs_cm <= 2047:
        return "node-XY3"
    if max_abs_cm <= 3277:
        return "node-XY4"
    if max_abs_cm <= 16383:
        return "node-XY5"
    if max_abs_cm <= 32767:
        return "node-XY6"
    return "node-LatLon"


# ---------------------------------------------------------------------------
# Geometry transforms
# ---------------------------------------------------------------------------


def polyline_centroid(polyline: Iterable[Mapping[str, Any] | Sequence[Any]]) -> Point:
    points = [as_point(point) for point in polyline]
    if not points:
        raise TransformError("Cannot calculate centroid for an empty polyline.")
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def polygon_centroid(polygon: Iterable[Mapping[str, Any] | Sequence[Any]]) -> Point:
    points = [as_point(point) for point in polygon]
    if len(points) < 3:
        return polyline_centroid(points)
    if points[0] != points[-1]:
        points.append(points[0])
    area2 = 0.0
    cx = 0.0
    cy = 0.0
    for first, second in zip(points, points[1:]):
        cross = first[0] * second[1] - second[0] * first[1]
        area2 += cross
        cx += (first[0] + second[0]) * cross
        cy += (first[1] + second[1]) * cross
    if abs(area2) < 1e-9:
        return polyline_centroid(points[:-1])
    return cx / (3.0 * area2), cy / (3.0 * area2)


def sample_polyline_at_intervals(
    polyline: Iterable[Mapping[str, Any] | Sequence[Any]],
    spacing_m: float = 5.0,
    min_nodes: int = 2,
    max_nodes: int = 12,
) -> list[Point]:
    points = [as_point(point) for point in polyline]
    if len(points) < 2:
        raise TransformError("A lane polyline must contain at least two points.")
    length = _polyline_length(points)
    if length == 0:
        raise TransformError("A lane polyline has zero length.")
    target_count = max(min_nodes, min(max_nodes, int(math.ceil(length / spacing_m)) + 1))
    return sample_polyline_by_count(points, target_count)


def sample_polyline_by_count(
    polyline: Iterable[Mapping[str, Any] | Sequence[Any]],
    count: int,
) -> list[Point]:
    points = [as_point(point) for point in polyline]
    if count < 2:
        raise TransformError("Polyline sample count must be at least 2.")
    length = _polyline_length(points)
    if length == 0:
        return [points[0] for _ in range(count)]
    distances = [i * length / (count - 1) for i in range(count)]
    return [_point_at_distance(points, distance) for distance in distances]


def compute_centerline_from_edges(
    left_edge: Iterable[Mapping[str, Any] | Sequence[Any]],
    right_edge: Iterable[Mapping[str, Any] | Sequence[Any]],
    max_nodes: int = 12,
) -> list[Point]:
    left = [as_point(point) for point in left_edge]
    right = [as_point(point) for point in right_edge]
    if len(left) < 2 or len(right) < 2:
        raise TransformError("Both lane edges must contain at least two points.")
    count = min(max_nodes, max(2, min(len(left), len(right))))
    left_sampled = sample_polyline_by_count(left, count)
    right_sampled = sample_polyline_by_count(right, count)
    return [
        ((left_point[0] + right_point[0]) / 2.0, (left_point[1] + right_point[1]) / 2.0)
        for left_point, right_point in zip(left_sampled, right_sampled)
    ]


def direction_relative_to_refpoint(
    lane_polyline: Iterable[Mapping[str, Any] | Sequence[Any]],
    ref_point: Mapping[str, Any] | Sequence[Any],
    tolerance_m: float = 1.0,
) -> str:
    points = [as_point(point) for point in lane_polyline]
    if len(points) < 2:
        return "unknown"
    ref = as_point(ref_point)
    start_distance = distance(points[0], ref)
    end_distance = distance(points[-1], ref)
    if abs(start_distance - end_distance) <= tolerance_m:
        return "unknown"
    return "ingress" if end_distance < start_distance else "egress"


def cluster_by_direction(
    lanes: Iterable[Iterable[Mapping[str, Any] | Sequence[Any]]],
    ref_point: Mapping[str, Any] | Sequence[Any],
    bearing_tolerance_deg: float = 25.0,
) -> list[int]:
    ref = as_point(ref_point)
    clusters: list[float] = []
    assignments: list[int] = []
    for lane in lanes:
        midpoint = polyline_centroid(lane)
        bearing = bearing_degrees(ref, midpoint)
        for index, cluster_bearing in enumerate(clusters, start=1):
            if abs(angle_delta(bearing, cluster_bearing)) <= bearing_tolerance_deg:
                assignments.append(index)
                break
        else:
            clusters.append(bearing)
            assignments.append(len(clusters))
    return assignments


def assign_approach_id(cluster_id: int) -> int:
    if int(cluster_id) < 1:
        raise TransformError("Approach IDs must be positive.")
    return int(cluster_id)


def pair_ingress_egress_by_geometry(
    ingress_lanes: Iterable[Mapping[str, Any]],
    egress_lanes: Iterable[Mapping[str, Any]],
    max_match_dist_m: float = 8.0,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    egress = list(egress_lanes)
    for ingress in ingress_lanes:
        source_nodes = _lane_nodes(ingress)
        if len(source_nodes) < 2:
            continue
        source_end = source_nodes[-1]
        best: tuple[float, Mapping[str, Any]] | None = None
        for target in egress:
            target_nodes = _lane_nodes(target)
            if len(target_nodes) < 2:
                continue
            match_distance = distance(source_end, target_nodes[0])
            if best is None or match_distance < best[0]:
                best = (match_distance, target)
        if best and best[0] <= max_match_dist_m:
            target = best[1]
            candidates.append(
                {
                    "source_lane_id": ingress.get("laneID", ingress.get("lane_id")),
                    "target_lane_id": target.get("laneID", target.get("lane_id")),
                    "distance_m": best[0],
                    "confidence": max(0.0, 1.0 - best[0] / max_match_dist_m),
                }
            )
    return candidates


def maneuver_from_angle_change(
    ingress_polyline: Iterable[Mapping[str, Any] | Sequence[Any]],
    egress_polyline: Iterable[Mapping[str, Any] | Sequence[Any]],
) -> str:
    ingress = [as_point(point) for point in ingress_polyline]
    egress = [as_point(point) for point in egress_polyline]
    if len(ingress) < 2 or len(egress) < 2:
        return "unknown"
    incoming = bearing_degrees(ingress[-2], ingress[-1])
    outgoing = bearing_degrees(egress[0], egress[1])
    delta = angle_delta(outgoing, incoming)
    # [STANDARD: C-Roads 3.2.0 section 3.3.5.1 connectingLane.maneuver,
    #  DE_AllowedManeuvers per SAE J2735] Maneuver semantics (straight / left /
    #  right / U-turn) are classified here from the ingress->egress heading
    #  change; the encoder later maps these to the J2735 AllowedManeuvers bits.
    if abs(delta) <= 30:
        return "straight"
    if 30 < delta <= 150:
        return "leftTurn"
    if -150 <= delta < -30:
        return "rightTurn"
    return "uTurn"


def arrow_to_maneuver(value: Any) -> str:
    """Convert a recognised stage-diagram arrow label to a MAPEM maneuver value."""

    text = normalise_text(value).lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "straight": "straight",
        "straight_up": "straight",
        "ahead": "straight",
        "through": "straight",
        "left": "leftTurn",
        "left_arrow": "leftTurn",
        "right": "rightTurn",
        "right_arrow": "rightTurn",
        "u_turn": "uTurn",
        "uturn": "uTurn",
        "u_arrow": "uTurn",
    }
    return mapping.get(text, "unknown")


# ---------------------------------------------------------------------------
# Semantic transforms
# ---------------------------------------------------------------------------


def phase_letter_to_signal_group(
    phase_label: Any,
    dummy_phase_set: Iterable[str] | None = None,
    phase_order: Sequence[str] | None = None,
) -> int | None:
    label = normalise_phase_label(phase_label)
    dummy = {normalise_phase_label(value) for value in (dummy_phase_set or [])}
    if label in dummy:
        return None
    if phase_order:
        order = [normalise_phase_label(value) for value in phase_order]
        if label not in order:
            raise TransformError(f"Phase label {label!r} is not in the configured phase order.")
        return order.index(label) + 1
    match = re.fullmatch(r"([A-Z])(\d*)", label)
    if not match:
        raise TransformError(f"Invalid phase label {phase_label!r}.")
    letter_value = ord(match.group(1)) - ord("A") + 1
    suffix = match.group(2)
    return letter_value if not suffix else 26 + int(suffix)


def normalise_phase_label(value: Any) -> str:
    text = normalise_text(value).upper().replace(" ", "")
    match = re.search(r"\b([A-Z](?:\d+)?)\b", text)
    if not match:
        raise TransformError(f"Cannot read a phase label from {value!r}.")
    return match.group(1)


def extract_phase_labels(value: Any) -> list[str]:
    text = normalise_text(value).upper()
    labels = re.findall(r"\b[A-Z](?:\d+)?\b", text)
    ignored = {"STAGE", "PHASE", "STREAM", "TYPE", "TIME", "DUMMY"}
    return [label for label in labels if label not in ignored]


def phase_type_to_lanetype(value: Any, output: str = "sitemodel") -> str:
    text = normalise_text(value).lower()
    if text in {"t", "traffic", "f", "filter", "i", "indicative", "s", "switched"}:
        return "vehicle"
    if text in {"p", "ped", "pedestrian", "puffin", "toucan", "crossing", "crosswalk"}:
        return "crosswalkLane" if output == "mapem" else "crosswalk"
    if text in {"cycle", "bike", "bicycle"}:
        return "bikeLane"
    if text in {"footway", "sidewalk", "pavement"}:
        return "sideWalk" if output == "mapem" else "sidewalk"
    if text in {"median", "island", "traffic island"}:
        return "medianLane" if output == "mapem" else "median"
    if text in {"tram", "lrt", "tracked", "trackedvehicle"}:
        return "trackedVehicle"
    if text in {"parking", "parking bay"}:
        return "parking"
    if text in {"d", "dummy"}:
        raise TransformError("Dummy phases must not be converted to laneType.")
    return "vehicle"


def layer_name_to_lanetype(value: Any, output: str = "sitemodel") -> str:
    return lane_type_from_label(value, output=output)


def lane_type_from_label(value: Any, output: str = "sitemodel") -> str:
    text = normalise_text(value).lower()
    if _contains_any(text, ("cross", "zebra", "puffin", "toucan", "ped")):
        return "crosswalkLane" if output == "mapem" else "crosswalk"
    if _contains_any(text, ("cycle", "bike")):
        return "bikeLane"
    if _contains_any(text, ("footway", "pavement", "sidewalk")):
        return "sideWalk" if output == "mapem" else "sidewalk"
    if _contains_any(text, ("median", "island", "central reserve")):
        return "medianLane" if output == "mapem" else "median"
    if _contains_any(text, ("tram", "lrt", "rail", "tracked")):
        return "trackedVehicle"
    if _contains_any(text, ("parking", "bay")):
        return "parking"
    return "vehicle"


def directional_use_from_label(value: Any) -> str:
    text = normalise_text(value).lower()
    if _contains_any(text, ("bidirectional", "two-way", "both", "pedestrian", "crosswalk")):
        return "both"
    if _contains_any(text, ("ingress", "inbound", "entry", "approach")):
        return "ingress"
    if _contains_any(text, ("egress", "outbound", "exit", "leaving")):
        return "egress"
    return "unknown"


def encode_bit_string_2(directional_use: Any) -> str:
    text = normalise_text(directional_use).lower()
    # [STANDARD: C-Roads 3.2.0 section 3.3.2.3 — Directional Use]
    # 2-bit string: ingressPath(0), egressPath(1). "10"=ingress, "01"=egress,
    # "11"=both (bidirectional), "00"=no travel (impassable / unknown).
    mapping = {
        "ingress": "10",
        "egress": "01",
        "both": "11",
        "bidirectional": "11",
        "impassable": "00",
        "unknown": "00",
    }
    if text not in mapping:
        raise TransformError(f"Unsupported directionalUse {directional_use!r}.")
    return mapping[text]


def shared_with_from_label(value: Any) -> list[str]:
    text = normalise_text(value).lower()
    users: list[str] = []
    for label, keywords in {
        "pedestrian": ("pedestrian", "footway", "pavement", "sidewalk"),
        "bicycle": ("cycle", "bike", "bicycle"),
        "bus": ("bus",),
        "taxi": ("taxi",),
        "trackedVehicle": ("tram", "lrt", "rail", "tracked"),
    }.items():
        if _contains_any(text, keywords):
            users.append(label)
    return users


def movement_from_label(value: Any) -> str:
    text = normalise_text(value).lower()
    if _contains_any(text, ("ahead", "straight", "through")):
        return "straight"
    if _contains_any(text, ("left", "nearside")):
        return "leftTurn"
    if _contains_any(text, ("right", "offside")):
        return "rightTurn"
    if _contains_any(text, ("u-turn", "uturn")):
        return "uTurn"
    return "unknown"


# ---------------------------------------------------------------------------
# Conservative text parsing for control facts
# ---------------------------------------------------------------------------


def parse_stage_phase_relationship(value: Any) -> dict[str, list[str]]:
    """Parse only explicit patterns such as 'Stage 1: A B C'."""

    text = normalise_text(value).upper()
    result: dict[str, list[str]] = {}
    for match in re.finditer(r"STAGE\s*(\d+)\s*[:=-]\s*([A-Z0-9,\s]+)", text):
        labels = extract_phase_labels(match.group(2))
        if labels:
            result[match.group(1)] = labels
    return result


def resolve_egress_lane_from_stage(*_args: Any, **_kwargs: Any) -> None:
    """Placeholder-safe transform: stage rows alone do not resolve target lanes."""

    return None


# ---------------------------------------------------------------------------
# Registry for future matching-engine integration
# ---------------------------------------------------------------------------


TRANSFORMS: dict[str, Callable[..., Any]] = {
    "protocol_version": protocol_version,
    "mapem_message_id": mapem_message_id,
    "project_revision": project_revision,
    "extract_digits": extract_digits,
    "extract_int_from_site_code": extract_int_from_site_code,
    "normalise_identifier": normalise_identifier,
    "take_lat": take_lat,
    "take_long": take_long,
    "coordinate_bounds": coordinate_bounds,
    "assess_coordinate_reference": assess_coordinate_reference,
    "bng_to_wgs84_OSTN15": bng_to_wgs84_OSTN15,
    "wgs84_to_int_1e7": wgs84_to_int_1e7,
    "relative_to_refpoint": relative_to_refpoint,
    "delta_to_cm": delta_to_cm,
    "choose_node_xy_precision": choose_node_xy_precision,
    "polyline_centroid": polyline_centroid,
    "polygon_centroid": polygon_centroid,
    "sample_polyline_at_intervals": sample_polyline_at_intervals,
    "compute_centerline_from_edges": compute_centerline_from_edges,
    "direction_relative_to_refpoint": direction_relative_to_refpoint,
    "cluster_by_direction": cluster_by_direction,
    "assign_approach_id": assign_approach_id,
    "pair_ingress_egress_by_geometry": pair_ingress_egress_by_geometry,
    "maneuver_from_angle_change": maneuver_from_angle_change,
    "arrow_to_maneuver": arrow_to_maneuver,
    "phase_letter_to_signal_group": phase_letter_to_signal_group,
    "extract_phase_labels": extract_phase_labels,
    "phase_type_to_lanetype": phase_type_to_lanetype,
    "layer_name_to_lanetype": layer_name_to_lanetype,
    "lane_type_from_label": lane_type_from_label,
    "directional_use_from_label": directional_use_from_label,
    "encode_bit_string_2": encode_bit_string_2,
    "shared_with_from_label": shared_with_from_label,
    "movement_from_label": movement_from_label,
    "parse_stage_phase_relationship": parse_stage_phase_relationship,
    "resolve_egress_lane_from_stage": resolve_egress_lane_from_stage,
}


FACT_TRANSFORM_HINTS: dict[str, tuple[str, ...]] = {
    "protocol_version": ("protocol_version",),
    "mapem_message_id": ("mapem_message_id",),
    "official_intersection_id_from_cad": ("extract_int_from_site_code",),
    "coordinate_reference_system_evidence_from_cad": ("assess_coordinate_reference",),
    "georeference_status_from_cad": ("assess_coordinate_reference",),
    "lane_centreline_nodes_from_cad": ("sample_polyline_at_intervals",),
    "lane_geometry_candidate_from_cad": ("sample_polyline_at_intervals",),
    "lane_direction_from_cad": ("direction_relative_to_refpoint",),
    "approach_assignment_candidate_from_cad": ("cluster_by_direction", "assign_approach_id"),
    "lane_use_label_from_cad": ("lane_type_from_label",),
    "lane_type_marking_or_sign_note_from_cad": ("lane_type_from_label",),
    "road_marking_or_sign_note_from_cad": ("shared_with_from_label",),
    "lane_connection_candidate_from_cad": ("pair_ingress_egress_by_geometry",),
    "target_lane_candidate_from_cad": ("pair_ingress_egress_by_geometry",),
    "movement_direction_candidate_from_cad": ("movement_from_label", "maneuver_from_angle_change"),
    "phase_label_from_controller_config": ("phase_letter_to_signal_group",),
    "stage_phase_relationship_from_controller_config": ("parse_stage_phase_relationship",),
}


def apply_transform_pipeline(value: Any, transform_names: Sequence[str], **context: Any) -> Any:
    result = value
    for name in transform_names:
        transform = TRANSFORMS[name]
        try:
            result = transform(result, **context)
        except TypeError:
            result = transform(result)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def normalise_text(value: Any) -> str:
    return " ".join(str(value).strip().split())


def distance(first: Mapping[str, Any] | Sequence[Any], second: Mapping[str, Any] | Sequence[Any]) -> float:
    x1, y1 = as_point(first)
    x2, y2 = as_point(second)
    return math.hypot(x2 - x1, y2 - y1)


def bearing_degrees(first: Mapping[str, Any] | Sequence[Any], second: Mapping[str, Any] | Sequence[Any]) -> float:
    x1, y1 = as_point(first)
    x2, y2 = as_point(second)
    return (math.degrees(math.atan2(x2 - x1, y2 - y1)) + 360.0) % 360.0


def angle_delta(angle: float, reference: float) -> float:
    return (angle - reference + 180.0) % 360.0 - 180.0


def _in_leeds_bng(x: float, y: float) -> bool:
    return 420000 <= x <= 450000 and 420000 <= y <= 460000


def _in_bath_bng(x: float, y: float) -> bool:
    return 360000 <= x <= 390000 and 150000 <= y <= 180000


def _looks_like_lat_lon(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return ("lat" in value and "lon" in value) or ("lat" in value and "long" in value)


def _lat_lon_offset_m(lat: float, lon: float, ref_lat: float, ref_lon: float) -> Point:
    mean_lat = math.radians((lat + ref_lat) / 2.0)
    north = (lat - ref_lat) * 111_320.0
    east = (lon - ref_lon) * 111_320.0 * math.cos(mean_lat)
    return east, north


def _polyline_length(points: Sequence[Point]) -> float:
    return sum(distance(first, second) for first, second in zip(points, points[1:]))


def _point_at_distance(points: Sequence[Point], target_distance: float) -> Point:
    if target_distance <= 0:
        return points[0]
    remaining = target_distance
    for first, second in zip(points, points[1:]):
        segment_length = distance(first, second)
        if remaining <= segment_length:
            ratio = 0.0 if segment_length == 0 else remaining / segment_length
            return (
                first[0] + (second[0] - first[0]) * ratio,
                first[1] + (second[1] - first[1]) * ratio,
            )
        remaining -= segment_length
    return points[-1]


def _lane_nodes(lane: Mapping[str, Any]) -> list[Point]:
    raw = lane.get("nodeList", lane.get("nodes", lane.get("centerline", [])))
    if isinstance(raw, Mapping):
        raw = raw.get("nodes", [])
    return [as_point(point) for point in raw]


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)
