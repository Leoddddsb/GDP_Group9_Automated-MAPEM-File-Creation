"""
reverse_build_dict.py
=====================
v3 matching_rules.yaml was hand-authored and diverged from the Excel dictionary
(it uses 12 facts the Excel lacks). This script reverse-engineers v3 back into:

  1. MAPEM_Dictionary_v3.xlsx     — the per-field source list (what the team
                                     maintains going forward).
  2. generator_overlay.json       — everything the Excel can't carry: the global
                                     sections (scoring, conflict_detection,
                                     object_scope, group_logic, config, forbidden),
                                     the transform map (target+fact -> chain), and
                                     per-field extras (constants, default_value,
                                     fallback_config_key, c_roads_mandatory, ...).

After this, `build_rules_from_dict.py` (v3 mode) reads the Excel + overlay and
regenerates v3 — so the big YAML is never hand-maintained again.
"""
import json
import sys

import openpyxl
import yaml

V3 = sys.argv[1] if len(sys.argv) > 1 else "matching_rules_1_.yaml"
XLSX_OUT = sys.argv[2] if len(sys.argv) > 2 else "MAPEM_Dictionary_v3.xlsx"
OVERLAY_OUT = sys.argv[3] if len(sys.argv) > 3 else "generator_overlay.json"

d = yaml.safe_load(open(V3, encoding="utf-8"))


# --- infer Source Category / Subtype from a fact_name -----------------------
def infer_source(fact_name):
    fn = fact_name or ""
    table = [
        ("_from_pdf_cv", "site_plans_and_cad_files", "pdf_cv"),
        ("_from_pdf_vector", "site_plans_and_cad_files", "pdf_vector"),
        ("_from_pdf_ocr", "site_plans_and_cad_files", "pdf_ocr"),
        ("_from_cad", "site_plans_and_cad_files", "cad_drawing"),
        ("_from_open_street_map", "gis_data", "open_street_map"),
        ("_from_ordnance_survey", "gis_data", "ordnance_survey"),
        ("_from_controller_config", "site_configuration_information", "controller_configuration_pdf"),
        ("_from_ram_8tx", "site_configuration_information", "ram_8tx"),
        ("_from_utc_form", "site_configuration_information", "utc_form_docx"),
    ]
    for suffix, cat, sub in table:
        if fn.endswith(suffix):
            return cat, sub
    specials = {
        "scn": ("site_configuration_information", "deployment_config"),
        "site_description": ("site_plans_and_cad_files", "cad_drawing"),
        "archive_member": ("site_plans_and_cad_files", "cad_archive"),
        "coordinate_bounds": ("site_plans_and_cad_files", "cad_drawing"),
        "cad_block_reference": ("site_plans_and_cad_files", "cad_drawing"),
    }
    return specials.get(fn, ("site_plans_and_cad_files", "cad_drawing"))


# --- 1. build the Excel rows + overlay --------------------------------------
rows = [["MAPEM Element", "Population mode", "Required Fact Group",
         "Source Category", "Subtype", "Fact Name", "Priority"]]

transform_map = {}     # "target||fact_name" -> [transform chain]
field_extras = {}      # target -> {extra keys not expressible in the 7 columns}

NON_SOURCE_KEYS = ("value", "confidence", "config_key", "fallback_config_key",
                   "initial", "auto_start", "default_value", "optional",
                   "c_roads_mandatory", "applies_when", "note")

for f in d["fields"]:
    target = f["target"]
    pm = f.get("population_mode", "")
    # capture per-field extras for the overlay
    extras = {k: f[k] for k in NON_SOURCE_KEYS if k in f}
    if extras:
        field_extras[target] = extras

    srcs = f.get("sources", []) + f.get("overrides", [])
    if not srcs:
        # non-source field → one N/A row so the Excel still lists the field
        rows.append([target, pm, "N/A", "N/A", "N/A", "N/A", "N/A"])
        if f.get("overrides"):
            field_extras.setdefault(target, {})["overrides"] = f["overrides"]
        continue

    for s in srcs:
        fn = s.get("fact_name", "")
        cat, sub = infer_source(fn)
        rows.append([target, pm, s.get("fact_group", ""), cat, sub, fn,
                     s.get("priority", "")])
        if s.get("transform"):
            transform_map[f"{target}||{fn}"] = s["transform"]
    # record that some fields use 'overrides' (default mode) so generator rebuilds them
    if f.get("overrides"):
        field_extras.setdefault(target, {})["overrides"] = f["overrides"]

# --- write the Excel (Source Priority sheet; minimal Intro) ------------------
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Source Priority (Fact Level)"
for r in rows:
    ws.append(r)
intro = wb.create_sheet("Intro")
intro.append(["Reverse-generated from v3 matching_rules.yaml."])
intro.append(["Maintain fact rows here; global config lives in generator_overlay.json."])
wb.save(XLSX_OUT)

# --- 2. extract the global sections for the overlay -------------------------
overlay = {
    "version": d.get("version"),
    "schema_for": d.get("schema_for"),
    "selection_policy": d.get("selection_policy"),
    "scoring": d.get("scoring"),
    "conflict_detection": d.get("conflict_detection"),
    "object_scope": d.get("object_scope"),
    "group_logic": d.get("group_logic"),
    "config": d.get("config"),
    "forbidden": d.get("forbidden"),
    "transforms_doc": d.get("transforms"),
    "expected_output_schema": d.get("expected_output_schema"),
    "transform_map": transform_map,
    "field_extras": field_extras,
}
json.dump(overlay, open(OVERLAY_OUT, "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

print(f"[ok] wrote {XLSX_OUT}: {len(rows)-1} rows")
print(f"[ok] wrote {OVERLAY_OUT}: {len(transform_map)} transform chains, "
      f"{len(field_extras)} field-extras, global sections")
