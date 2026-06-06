"""GIS extraction and georeferencing helpers."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable


def extract_gis_facts(path: str | Path) -> list[dict]:
    target = Path(path)
    suffix = target.suffix.lower()
    if suffix in {".json", ".geojson"}:
        return _extract_geojson(target)
    if suffix == ".osm":
        return _extract_osm(target)
    if suffix in {".shp", ".gpkg"}:
        return _extract_fiona(target)
    raise ValueError(f"Unsupported GIS file type: {suffix or '<none>'}")


def bng_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise RuntimeError("BNG conversion requires the 'pyproj' package.") from exc
    transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(easting, northing)
    return lat, lon


def _extract_geojson(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    features = data.get("features", []) if data.get("type") == "FeatureCollection" else [data]
    facts: list[dict] = []
    points: list[tuple[float, float]] = []
    for index, feature in enumerate(features, start=1):
        properties = feature.get("properties") or {}
        name = properties.get("name") or properties.get("ref")
        if name:
            facts.append(_fact("road_direction_from_ordnance_survey", name, f"feature {index} properties.name", 0.85))
        geometry = feature.get("geometry")
        if geometry:
            facts.append(_fact("lane_geometry_candidate_from_ordnance_survey", geometry, f"feature {index} geometry", 0.75))
            points.extend(_coordinate_pairs(geometry.get("coordinates", [])))
    return facts + _bounds_and_centre(points, "GeoJSON geometries")


def _extract_osm(path: Path) -> list[dict]:
    root = ET.parse(path).getroot()
    nodes = {
        node.attrib["id"]: (float(node.attrib["lon"]), float(node.attrib["lat"]))
        for node in root.findall("node")
    }
    facts: list[dict] = []
    for way in root.findall("way"):
        tags = {tag.attrib.get("k"): tag.attrib.get("v") for tag in way.findall("tag")}
        if tags.get("name"):
            facts.append(_fact("road_direction_from_open_street_map", tags["name"], f"way {way.attrib.get('id')} tag name", 0.85))
    return facts + _bounds_and_centre(list(nodes.values()), "OSM nodes", "open_street_map")


def _extract_fiona(path: Path) -> list[dict]:
    try:
        import fiona
    except ImportError as exc:
        raise RuntimeError("Shapefile and GeoPackage extraction requires the 'fiona' package.") from exc
    facts: list[dict] = []
    points: list[tuple[float, float]] = []
    with fiona.open(path) as source:
        for index, feature in enumerate(source, start=1):
            properties = dict(feature.get("properties") or {})
            name = properties.get("name") or properties.get("ref")
            if name:
                facts.append(_fact("road_direction_from_ordnance_survey", name, f"feature {index} properties.name", 0.85))
            geometry = feature.get("geometry")
            if geometry:
                geometry_dict = dict(geometry)
                facts.append(_fact("lane_geometry_candidate_from_ordnance_survey", geometry_dict, f"feature {index} geometry", 0.75))
                points.extend(_coordinate_pairs(geometry_dict.get("coordinates", [])))
    return facts + _bounds_and_centre(points, "GIS geometries")


def _coordinate_pairs(value: object) -> Iterable[tuple[float, float]]:
    if isinstance(value, (list, tuple)) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
        yield float(value[0]), float(value[1])
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _coordinate_pairs(child)


def _bounds_and_centre(points: list[tuple[float, float]], location: str, source_role: str = "ordnance_survey") -> list[dict]:
    if not points:
        return []
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    bounds = {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}
    centre = {"lon": (bounds["min_x"] + bounds["max_x"]) / 2, "lat": (bounds["min_y"] + bounds["max_y"]) / 2}
    centre_type = (
        "junction_centre_from_open_street_map"
        if source_role == "open_street_map"
        else "junction_centre_from_ordnance_survey"
    )
    return [_fact("coordinate_bounds", bounds, location, 0.9), _fact(centre_type, centre, location, 0.6)]


def _fact(fact_type: str, value: object, location: str, confidence: float) -> dict:
    return {"fact_type": fact_type, "value": value, "evidence_location": location, "confidence": confidence}
