"""
build_rules_from_dict.py
========================
Generates matching_rules.yaml from MAPEM_Dictionary.xlsx (the source of truth).

The dictionary's "Source Priority (Fact Level)" sheet provides, per MAPEM element:
  population mode, and a list of (source_category, subtype, fact_group, fact_name,
  priority) candidate sources.

This script merges that with a small hand-authored OVERLAY for knowledge the
dictionary does not carry (constant values, c_roads_mandatory flags, forbidden
elements, config defaults), and writes matching_rules.yaml.

Re-run this whenever MAPEM_Dictionary.xlsx changes — rules stay in sync.

    python build_rules_from_dict.py MAPEM_Dictionary.xlsx matching_rules.yaml
"""
import sys
from collections import OrderedDict

import openpyxl
import yaml


# -----------------------------------------------------------------------------
# OVERLAY — profile knowledge NOT present in the dictionary.
# Keyed by MAPEM element path (exactly as in the dictionary).
# -----------------------------------------------------------------------------
OVERLAY = {
    "header.protocolVersion":                          {"const_value": 2},
    "header.messageID":                                {"const_value": 5},
    "header.stationID":                                {"config_key": "station_id"},
    "mapData.msgIssueRevision":                        {"project_initial": 1},
    "mapData.intersections[].id.region":               {"config_key": "region_code",
                                                        "c_roads_mandatory": True},
    "mapData.intersections[].revision":                {"project_initial": 1},
    "mapData.intersections[].laneSet[].LaneID":        {"auto_start": 1},
    "mapData.intersections[].laneSet[].ingressApproach": {"c_roads_mandatory": True},
    "mapData.intersections[].laneSet[].egressApproach":  {"c_roads_mandatory": True},
    "mapData.intersections[].laneSet[].connectsTo[].signalGroup": {"c_roads_mandatory": True},
}

# Synthetic container rules (ASN.1 optional but C-Roads required); not in dict.
CONTAINER_RULES = [
    {
        "target": "mapData.intersections",
        "population_mode": "must_exist",
        "c_roads_mandatory": True,
        "note": "ASN.1 OPTIONAL, but a signalised-junction MAPEM must carry "
                "a non-empty intersections list (C-Roads).",
        "sources": [],
    },
    {
        "target": "mapData.intersections[].laneSet[].connectsTo",
        "population_mode": "must_exist",
        "applies_when": "lane.directionalUse contains ingress",
        "c_roads_mandatory": True,
        "note": "ASN.1 OPTIONAL, but every ingress lane must connect "
                "(handbook §3.3.5). Engine enforces; encoder will not.",
        "sources": [],
    },
]

FORBIDDEN = [
    {"target": "mapData.intersections[].laneSet[].maneuvers",
     "reason": "C-Roads §3.3.3: lane-level maneuvers prohibited; use "
               "connectsTo.connectingLane.maneuver."},
    {"target": "mapData.intersections[].laneSet[].laneAttributes.sharedWith.bit_1",
     "name": "multipleLanesTreatedAsOneLane",
     "reason": "C-Roads: shall not be used."},
    {"target": "mapData.intersections[].laneSet[].laneAttributes.sharedWith.bit_9",
     "name": "pedestrianTraffic",
     "reason": "C-Roads: use bit 6 (pedestriansTraffic)."},
    {"target": "mapData.intersections[].regional",
     "conditional": "when roadSegments is used",
     "reason": "C-Roads: regional shall not be used when roadSegments is used."},
]

CONFIG_DEFAULTS = {
    "protocol_version": 2,
    "message_id_mapem": 5,
    "default_station_id": 100,
    "region_code": 50050,        # TBD: 50 + Leeds authority code
    "default_lane_width_m": 3.5,
    "crs_source": "EPSG:27700",
    "crs_target": "EPSG:4326",
    "bng_to_wgs84": "OSTN15",
}

PRIORITY_RANKS = {"P1": 1, "P2": 2, "P3": 3, "F": 9}

# Group logic: how the fact_groups under one MAPEM element combine.
#   policy all_required  -> every logical group must be satisfied (AND)
#   alternative_sets     -> fact_groups that are mutually OR (any one satisfies
#                           that logical slot). Geometry sources are alternatives:
#                           lane geometry OR road-layout geometry both locate a point.
GROUP_LOGIC = {
    "policy": "all_required",
    "description": "Each fact_group is required (AND). Groups inside an "
                   "alternative set are OR — satisfying any one satisfies that "
                   "logical slot. Within a group, sources are OR (priority pick).",
    "alternative_sets": {
        "geometry": ["lane_geometry", "road_layout_geometry"],
    },
}

# Conflict-detection tolerances. EDIT THESE during debugging — they are data,
# not code. The engine reads them to decide whether two candidate values for the
# same field "agree" (corroborate) or "disagree" (conflict).
CONFLICT_DETECTION = {
    "tolerances": {
        "coordinate":  {"method": "ground_distance_m", "tolerance": 2.0,
                        "note": "lat/long; compared as ground distance in metres"},
        "node_delta":  {"method": "ground_distance_m", "tolerance": 1.0,
                        "note": "lane geometry nodes; tighter than refPoint"},
        "integer_id":  {"method": "exact", "tolerance": 0,
                        "note": "signalGroup/LaneID/region/id; must match exactly"},
        "enum":        {"method": "exact",
                        "note": "laneType/directionalUse; no notion of 'close'"},
        "angle":       {"method": "angular_deg", "tolerance": 15.0,
                        "note": "approach/maneuver bearings; degrees"},
        "default":     {"method": "exact",
                        "note": "fallback: require exact equality"},
    },
    # field path (glob) -> tolerance type above
    "field_type_map": {
        "*.refPoint.lat": "coordinate",
        "*.refPoint.long": "coordinate",
        "*.nodeList.nodes[].delta": "node_delta",
        "*.signalGroup": "integer_id",
        "*.LaneID": "integer_id",
        "*.id.region": "integer_id",
        "*.id.id": "integer_id",
        "*.laneType": "enum",
        "*.directionalUse": "enum",
        "*.sharedWith": "enum",
        "*.ingressApproach": "angle",
        "*.egressApproach": "angle",
    },
}

POP_MODE_DEFS = {
    "constant": "Fixed by the MAPEM profile; no extraction.",
    "client_configured": "Provided/confirmed by client or deployment config.",
    "project_managed": "Maintained by the MAPEM lifecycle/versioning process.",
    "directly_extracted": "Read directly from official source content.",
    "geometry_derived": "Computed/inferred from spatial/geometry evidence.",
    "system_generated": "Assigned by the prototype after objects are extracted.",
    "evidence_fused": "Requires combined evidence from multiple source types.",
}


def build(xlsx_path, out_path):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    sp = wb["Source Priority (Fact Level)"]
    rows = list(sp.iter_rows(values_only=True))
    header = rows[0]
    # column indices (robust to ordering)
    col = {name: i for i, name in enumerate(header)}
    iE = col.get("MAPEM Element", 0)
    iPM = col.get("Population mode", 1)
    iFG = col.get("Required Fact Group", 2)
    iSC = col.get("Source Category", 3)
    iST = col.get("Subtype", 4)
    iFN = col.get("Fact Name", 5)
    iPR = col.get("Priority", 6)

    # group rows by element, preserving order
    fields = OrderedDict()
    for r in rows[1:]:
        if not r or r[iE] is None:
            continue
        elem = str(r[iE]).strip()
        pm = str(r[iPM]).strip() if r[iPM] else ""
        f = fields.setdefault(elem, {
            "target": elem,
            "population_mode": pm,
            "sources": [],
        })
        # non-source population modes have a single N/A row
        sc = (r[iSC] or "").strip() if r[iSC] else ""
        if sc and sc != "N/A":
            f["sources"].append({
                "fact_name": (r[iFN] or "").strip(),
                "source_category": sc,
                "subtype": (r[iST] or "").strip(),
                "fact_group": (r[iFG] or "").strip(),
                "priority": (r[iPR] or "").strip(),
                "transform": [],   # TODO Task 2: fill transform pipeline per fact
            })

    # apply overlay
    field_list = []
    for elem, f in fields.items():
        ov = OVERLAY.get(elem, {})
        if "const_value" in ov:
            f["population_mode"] = "constant"
            f["value"] = ov["const_value"]
        if "config_key" in ov:
            f["config_key"] = ov["config_key"]
        if "project_initial" in ov:
            f["initial"] = ov["project_initial"]
        if "auto_start" in ov:
            f["auto_start"] = ov["auto_start"]
        if ov.get("c_roads_mandatory"):
            f["c_roads_mandatory"] = True
        field_list.append(f)

    # insert container rules near their relatives (append; order non-critical)
    field_list.extend(CONTAINER_RULES)

    doc = OrderedDict()
    doc["version"] = "2.0"
    doc["schema_for"] = "MAPEM 3.2.0 (C-Roads profile)"
    doc["source_of_truth"] = "MAPEM_Dictionary.xlsx (Fact + Source Priority sheets)"
    doc["generated_by"] = "build_rules_from_dict.py — DO NOT hand-edit fields; edit the xlsx and regenerate"
    doc["priority_ranks"] = PRIORITY_RANKS
    doc["group_logic"] = GROUP_LOGIC
    doc["population_modes"] = POP_MODE_DEFS
    doc["config"] = CONFIG_DEFAULTS
    doc["conflict_detection"] = CONFLICT_DETECTION
    doc["fields"] = field_list
    doc["forbidden"] = FORBIDDEN
    doc["conflict_resolution"] = {
        "primary_rule": "priority_label_order",
        "description": "Among candidate sources for a field, pick the one whose "
                       "priority label ranks best (P1<P2<P3<F via priority_ranks). "
                       "Ties broken by source order. Others become corroborating.",
        "fallback": "manual_review",
        "log_destination": "validation_report.json",
    }
    doc["expected_output_schema"] = {
        "type": "list of per-field records",
        "record": ["target_path", "value", "population_mode", "rule_applied",
                   "source_facts", "transforms_run", "priority_used",
                   "confidence", "corroborating", "status", "notes"],
    }

    # dump preserving insertion order
    class OD(yaml.SafeDumper):
        pass
    OD.add_representer(OrderedDict,
                       lambda d, data: d.represent_mapping(
                           "tag:yaml.org,2002:map", data.items()))

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("# ============================================================\n")
        fh.write("# matching_rules.yaml — GENERATED from MAPEM_Dictionary.xlsx\n")
        fh.write("# Do NOT hand-edit the 'fields' section. Edit the xlsx and run\n")
        fh.write("#   python build_rules_from_dict.py MAPEM_Dictionary.xlsx matching_rules.yaml\n")
        fh.write("# Hand-authored overlay (constants, c_roads_mandatory, forbidden,\n")
        fh.write("# config) lives in build_rules_from_dict.py.\n")
        fh.write("# ============================================================\n\n")
        yaml.dump(doc, fh, Dumper=OD, sort_keys=False, allow_unicode=True,
                  default_flow_style=False, width=100)

    print(f"[ok] wrote {out_path}")
    print(f"     fields={len(field_list)}  "
          f"(incl. {len(CONTAINER_RULES)} container rules)")
    # quick stats
    n_sources = sum(len(f.get("sources", [])) for f in field_list)
    from collections import Counter
    pr = Counter()
    for f in field_list:
        for s in f.get("sources", []):
            pr[s["priority"]] += 1
    print(f"     total candidate sources={n_sources}  by priority={dict(pr)}")


if __name__ == "__main__":
    xlsx = sys.argv[1] if len(sys.argv) > 1 else "MAPEM_Dictionary.xlsx"
    out = sys.argv[2] if len(sys.argv) > 2 else "matching_rules.yaml"
    build(xlsx, out)
