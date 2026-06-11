# MAPEM Matching Engine

A **site-agnostic** tool that maps extracted facts to MAPEM 3.2.0 fields. For each
field it selects evidence by a **weighted final score** that folds extraction
confidence, conflict agreement, and source priority into one number
(`final_score = 0.15·confidence + 0.35·agreement + 0.50·priority`; highest wins),
preserves full provenance and conflict information, and outputs `mapped_evidence.json`
for downstream evidence fusion. Confidence is part of selection, not a separate
stage. Rules are generated from the MAPEM dictionary; the scoring weights, conflict
tolerances, and grouping are all configurable.

```
MAPEM_Dictionary_v3.xlsx + generator_overlay.json ─(build_rules_from_dict_v3.py)─▶ matching_rules.yaml ┐
                                                                                  │
ingestion + geometry-assignment ─(ingest_adapter.py)─▶ facts.<site>.json ─────────┤
site_config_<site>.yaml ──────────────────────────────────────────────────────────┼─▶ matching_engine.py ─▶ mapped_evidence.json
transform_pipelines.yaml + transforms.py (+ overlay) ─────────────────────────────┘                              │
                                                                                                                 ▼
                                                                          (fusion stage)  fuse.py ─▶ fused_model.json + fusion_report.json
                                                                                                                 │
                                                                                                                 ▼
                                                                                          (encoding stage, separate module) ─▶ MAPEM file
```

`ingest_adapter.py` is the input boundary: it turns the upstream ingestion +
geometry-assignment output into the flat `facts.<site>.json` the engine consumes
(unwraps payloads, normalises confidence, injects instance keys).

`fuse.py` is the **downstream** boundary (the fusion stage, in `src/mapemgen/fusion/`):
it reads `mapped_evidence.json`, assembles the nested MAPEM-shaped model, adjudicates
each field, runs cross-field consistency checks, and emits `fused_model.json` for the
separate encoding stage. Matching and fusion connect only through the
`mapped_evidence.json` contract.

---

## Quick start

```bash
pip install pyyaml openpyxl pyproj

# 1. (re)generate rules from the dictionary
python build_rules_from_dict_v3.py MAPEM_Dictionary_v3.xlsx generator_overlay.json matching_rules.yaml

# 2. scaffold a site config (then fill the TBD fields)
python init_site.py 337L --name "Rodley Roundabout" --authority "Leeds City Council"

# 3. adapt upstream ingestion + geometry-assignment output into engine facts
python ingest_adapter.py \
  --facts       extracted_facts.337L.partial.json \
  --assignments geometry_assignments.337L.partial.json \
  --out         facts.337L.json
# --assignments is optional; without it you still get payload-unwrap + confidence
# normalisation (but no geometry instance keys).

# 4. run matching
python matching_engine.py \
  --rules    matching_rules.yaml \
  --facts    facts.337L.json \
  --config   site_config_337L.yaml \
  --transforms transforms_overlay \
  --pipelines  transform_pipelines.yaml \
  --out      mapped_evidence.json

# 5. fuse: assemble the nested MAPEM model + run consistency checks
#    (fusion stage — lives in src/mapemgen/fusion/)
python fuse.py \
  --evidence mapped_evidence.json \
  --out      fused_model.json \
  --report   fusion_report.json
```

`--pipelines` defaults to `transform_pipelines.yaml` beside the rules.
`--transforms` defaults to `transforms`; use **`transforms_overlay`** for the
fixed stubs + approach / connecting-lane resolution.

---

## Files

| File | Role | Edit? |
|---|---|---|
| `MAPEM_Dictionary_v3.xlsx` | source of truth: facts + priority (team maintains) | ✎ team |
| `generator_overlay.json` | global config: scoring, tolerances, transform map, field extras | ✎ |
| `build_rules_from_dict_v3.py` | generator (xlsx + overlay → v3 rules) | ✎ |
| `matching_rules.yaml` | generated rules (fields, priority_ranks, group_logic, conflict_detection, config, forbidden) | ✗ regenerate |
| `ingest_adapter.py` | input boundary: ingestion + assignment output → engine facts | ✎ |
| `fuse.py` | downstream fusion stage (in `src/mapemgen/fusion/`): mapped_evidence → fused_model + report | ✎ |
| `transform_pipelines.yaml` | per-source transform chains (separate from rules) | ✎ |
| `transforms.py` | transform functions | teammate |
| `transforms_overlay.py` | fixes/additions over transforms.py (loaded by engine) | ✎ |
| `site_config_<site>.yaml` | per-site human input | ✎ per site |
| `init_site.py` | scaffold a new site config | run |
| `matching_engine.py` | the engine | ✎ |
| `matching_rules.md` | how matching works (main guide) | ref |
| `payload_contract.md` | parser → transform payload shapes | ref |
| `conflict_rules.md` | conflict variable + tolerances | ref |
| `output_schema.md` | `mapped_evidence.json` contract (downstream) | ref |
| `OSTN15_setup.md` | install the OSTN15 grid for accurate coordinates | ref |

---

## How it works (one paragraph)

The engine expands each MAPEM field template into concrete instances, then for each
field gathers candidate facts, groups them by `fact_group` (**within-group OR** by
priority, **across-group AND** — every required group must yield a winner, geometry
groups being alternatives), runs the chosen source's transform pipeline to compute
the value, and records provenance + a `conflict` variable. Cross-lane fields
(approaches, connecting lane) are resolved by a prepass that clusters lane
centrelines and pairs ingress↔egress by geometry. Missing transforms, payload-shape
mismatches, or missing required groups degrade a field to `pending_transform` /
`manual_review` — the run never crashes.

---

## Common tasks

**Add / change a fact or its priority** → edit `MAPEM_Dictionary_v3.xlsx`, rerun
`build_rules_from_dict.py`. Never hand-edit `matching_rules.yaml`'s `fields`.

**Add a new site** → `python init_site.py <id> ...`, fill TBDs (region_code,
crs_source, dummy_phases are required).

**Retune priority globally** → edit `priority_ranks` in `matching_rules.yaml`.
**Per-site priority** → `priority_overrides` in that site's config.

**Change conflict tolerances** → `conflict_detection.tolerances` in
`matching_rules.yaml` (data, not code). See `conflict_rules.md`.

**Add a transform** → implement in `transforms.py` (or `transforms_overlay.py`),
register in `TRANSFORMS`, then reference it in `transform_pipelines.yaml`.

**Change which fact_groups are required / alternative** → `group_logic` in
`matching_rules.yaml`.

---

## Extension points (swappable classes in `matching_engine.py`)

- `SourceSelector` — priority/selection logic
- `ConfidencePolicy` — confidence scoring (the confidence teammate plugs in here)
- `ConflictDetector` — conflict computation + tolerances
- `InstanceResolver` — `[]` template expansion
- `TransformRunner` — pipeline execution (uses the TRANSFORMS registry)

---

## Status

**Working**: rules from xlsx, population-mode dispatch, P1–F priority, AND grouping,
conflict variable, transform integration (real values for id / refPoint / laneType /
signalGroup / approaches), input validation, OSTN15 detection, graceful degradation.

**Pending (mostly external)**: install the OSTN15 grid (`OSTN15_setup.md`); parsers
emitting payloads per `payload_contract.md`; real `extracted_facts.json` +
end-to-end test; confidence function from the teammate (plug into `ConfidencePolicy`);
tolerance tuning; downstream schema sign-off (`output_schema.md`); implement
`resolve_egress_lane_from_stage` fully where stage data is available.
