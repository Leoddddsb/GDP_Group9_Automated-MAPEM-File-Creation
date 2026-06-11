"""
build_rules_from_dict_v3.py
===========================
Generates the v3 matching_rules.yaml from:
  - MAPEM_Dictionary_v3.xlsx  (the per-field source list the team maintains)
  - generator_overlay.json    (global config + transform map + field extras)

The big YAML is never hand-edited. To change facts/priorities, edit the Excel;
to change scoring/tolerances/transforms, edit the overlay JSON. Then re-run:

    python build_rules_from_dict_v3.py MAPEM_Dictionary_v3.xlsx generator_overlay.json matching_rules.yaml
"""
import json
import sys
from collections import OrderedDict

import openpyxl
import yaml

XLSX = sys.argv[1] if len(sys.argv) > 1 else "MAPEM_Dictionary_v3.xlsx"
OVERLAY = sys.argv[2] if len(sys.argv) > 2 else "generator_overlay.json"
OUT = sys.argv[3] if len(sys.argv) > 3 else "matching_rules.yaml"

ov = json.load(open(OVERLAY, encoding="utf-8"))
field_extras = ov.get("field_extras", {})
transform_map = ov.get("transform_map", {})

# --- read Excel → group rows by MAPEM element -------------------------------
wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb["Source Priority (Fact Level)"]
rows = list(ws.iter_rows(values_only=True))
hdr = list(rows[0])
ci = {h: i for i, h in enumerate(hdr)}

fields = OrderedDict()
for r in rows[1:]:
    if not r or r[ci["MAPEM Element"]] is None:
        continue
    target = str(r[ci["MAPEM Element"]]).strip()
    pm = (r[ci["Population mode"]] or "").strip()
    f = fields.setdefault(target, {"target": target, "population_mode": pm,
                                   "sources": []})
    fn = r[ci["Fact Name"]]
    if fn and str(fn).strip() != "N/A":
        fn = str(fn).strip()
        src = {
            "fact_name": fn,
            "priority": (r[ci["Priority"]] or "").strip(),
            "fact_group": (r[ci["Required Fact Group"]] or "").strip(),
        }
        chain = transform_map.get(f"{target}||{fn}")
        if chain:
            src["transform"] = chain
        f["sources"].append(src)


# --- apply per-field extras + split overrides out of sources ----------------
def finalise_field(target, f):
    extras = field_extras.get(target, {})
    out = {"target": target, "population_mode": f["population_mode"]}
    # ordering: c_roads_mandatory near top if present
    if extras.get("c_roads_mandatory"):
        out["c_roads_mandatory"] = True
    for k in ("value", "confidence", "config_key", "fallback_config_key",
              "initial", "auto_start", "default_value", "optional", "applies_when",
              "note"):
        if k in extras:
            out[k] = extras[k]
    # 'overrides' fields (default mode): facts live under overrides, not sources
    if "overrides" in extras:
        out["overrides"] = extras["overrides"]
    elif f["sources"]:
        out["sources"] = f["sources"]
    return out


field_list = [finalise_field(t, f) for t, f in fields.items()]

# --- assemble the v3 document -----------------------------------------------
doc = OrderedDict()
doc["version"] = ov.get("version", "3.0")
doc["schema_for"] = ov.get("schema_for")
doc["selection_policy"] = ov.get("selection_policy")
doc["config"] = ov.get("config")
doc["scoring"] = ov.get("scoring")
doc["conflict_detection"] = ov.get("conflict_detection")
doc["object_scope"] = ov.get("object_scope")
doc["group_logic"] = ov.get("group_logic")
doc["transforms"] = ov.get("transforms_doc")
doc["fields"] = field_list
doc["forbidden"] = ov.get("forbidden")
doc["expected_output_schema"] = ov.get("expected_output_schema")
doc = OrderedDict((k, v) for k, v in doc.items() if v is not None)


class OD(yaml.SafeDumper):
    pass


OD.add_representer(OrderedDict, lambda dr, data: dr.represent_mapping(
    "tag:yaml.org,2002:map", data.items()))

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("# GENERATED from MAPEM_Dictionary_v3.xlsx + generator_overlay.json\n")
    fh.write("# Edit the xlsx (facts) or the overlay json (scoring/transforms),\n")
    fh.write("# then re-run build_rules_from_dict_v3.py. Do NOT hand-edit this file.\n\n")
    yaml.dump(doc, fh, Dumper=OD, sort_keys=False, allow_unicode=True,
              default_flow_style=False, width=100)

print(f"[ok] wrote {OUT}: {len(field_list)} fields")
