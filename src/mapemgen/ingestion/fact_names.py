from __future__ import annotations

from pathlib import Path


TEXT_FACT_NAMES: dict[str, dict[str, str]] = {
    "phase_candidate": {
        "ram_8tx": "phase_label_from_ram_8tx",
        "utc_form": "phase_label_from_utc_form",
        "controller_config": "phase_label_from_controller_config",
    },
    "stage_candidate": {
        "ram_8tx": "stage_phase_relationship_from_ram_8tx",
        "utc_form": "stage_phase_relationship_from_utc_form",
        "controller_config": "stage_phase_relationship_from_controller_config",
    },
    "intergreen_candidate": {
        "ram_8tx": "stage_phase_relationship_from_ram_8tx",
        "utc_form": "stage_phase_relationship_from_utc_form",
        "controller_config": "stage_phase_relationship_from_controller_config",
    },
    "timing_candidate": {
        "ram_8tx": "stage_phase_relationship_from_ram_8tx",
        "utc_form": "stage_phase_relationship_from_utc_form",
        "controller_config": "stage_phase_relationship_from_controller_config",
    },
    "ram_override_candidate": {
        "ram_8tx": "movement_phase_mapping_from_ram_8tx",
    },
}

CAD_FACT_NAMES: dict[str, str] = {
    "lane_candidate": "lane_geometry_candidate_from_cad",
    "stop_line_candidate": "stop_line_from_cad",
    "crossing_candidate": "lane_facility_geometry_candidate_from_cad",
    "signal_head_candidate": "lane_facility_geometry_candidate_from_cad",
    "cad_geometry_candidate": "lane_geometry_candidate_from_cad",
    "cad_text_label": "lane_use_label_from_cad",
}

GIS_FACT_NAMES: dict[str, dict[str, str]] = {
    "junction_centre_candidate": {
        "open_street_map": "junction_centre_from_open_street_map",
        "ordnance_survey": "junction_centre_from_ordnance_survey",
    },
    "gis_geometry_candidate": {
        "open_street_map": "lane_geometry_candidate_from_open_street_map",
        "ordnance_survey": "lane_geometry_candidate_from_ordnance_survey",
    },
}


def apply_dictionary_fact_name(fact: dict, source_file: str) -> dict:
    fact_type = str(fact.get("fact_type", ""))
    source_role = _source_role(source_file, str(fact.get("evidence_location", "")))
    canonical = _canonical_fact_name(fact_type, source_role)
    if canonical is None or canonical == fact_type:
        return fact
    renamed = dict(fact)
    renamed["fact_type"] = canonical
    renamed["legacy_fact_type"] = fact_type
    renamed["source_role"] = source_role
    return renamed


def _canonical_fact_name(fact_type: str, source_role: str) -> str | None:
    if source_role in {"ram_8tx", "utc_form", "controller_config"}:
        return TEXT_FACT_NAMES.get(fact_type, {}).get(source_role)
    if source_role == "cad_drawing":
        return CAD_FACT_NAMES.get(fact_type)
    if source_role in {"open_street_map", "ordnance_survey"}:
        return GIS_FACT_NAMES.get(fact_type, {}).get(source_role)
    return None


def _source_role(source_file: str, evidence_location: str) -> str:
    lowered = f"{source_file} {evidence_location}".lower()
    suffix = Path(source_file).suffix.lower()
    if ".dwg" in lowered or ".dxf" in lowered or suffix in {".dwg", ".dxf"}:
        return "cad_drawing"
    if suffix == ".8tx" or "ramdata" in lowered or "ram_" in lowered:
        return "ram_8tx"
    if suffix == ".docx" and ("utc" in lowered or "utcform" in lowered):
        return "utc_form"
    if suffix == ".pdf" and any(token in lowered for token in ("2500", "config", "configuration")):
        return "controller_config"
    if suffix == ".osm" or "openstreetmap" in lowered or "open_street_map" in lowered:
        return "open_street_map"
    if suffix in {".json", ".geojson", ".shp", ".gpkg"} or any(
        token in lowered for token in ("ordnance", "os-", "os_", "topo", "topographic")
    ):
        return "ordnance_survey"
    return "unknown"
