# MAPEM Matching Engine

A **site-agnostic** tool that maps extracted facts to MAPEM 3.2.0 fields. For each
field it selects evidence by population mode and source priority (P1–F), preserves
full provenance and conflict information, and outputs `mapped_evidence.json` for
downstream evidence fusion and confidence scoring. Rules are generated from the
MAPEM dictionary; priority, conflict tolerances, and grouping are all configurable.

```
MAPEM_Dictionary.xlsx ─(build_rules_from_dict.py)─▶ matching_rules.yaml ─┐
extracted_facts.<site>.json ───────────────────────────────────────────┤
site_config_<site>.yaml ────────────────────────────────────────────────┼─▶ matching_engine.py ─▶ mapped_evidence.json
transform_pipelines.yaml + transforms.py (+ overlay) ───────────────────┘
```

---

## Quick start

```bash
pip install pyyaml openpyxl pyproj

# 1. (re)generate rules from the dictionary
python build_rules_from_dict.py MAPEM_Dictionary.xlsx matching_rules.yaml

# 2. scaffold a site config (then fill the TBD fields)
python init_site.py 337L --name "Rodley Roundabout" --authority "Leeds City Council"

# 3. run matching
python matching_engine.py \
  --rules    matching_rules.yaml \
  --facts    extracted_facts.337L.json \
  --config   site_config_337L.yaml \
  --transforms transforms_overlay \
  --pipelines  transform_pipelines.yaml \
  --out      mapped_evidence.json
```

`--pipelines` defaults to `transform_pipelines.yaml` beside the rules.
`--transforms` defaults to `transforms`; use **`transforms_overlay`** for the
fixed stubs + approach / connecting-lane resolution.

---

## Files

| File | Role | Edit? |
|---|---|---|
| `MAPEM_Dictionary.xlsx` | source of truth: facts + priority | ✎ team |
| `build_rules_from_dict.py` | generator (xlsx → rules) + overlay of profile knowledge | ✎ overlay |
| `matching_rules.yaml` | generated rules (fields, priority_ranks, group_logic, conflict_detection, config, forbidden) | ✗ regenerate |
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

**Add / change a fact or its priority** → edit `MAPEM_Dictionary.xlsx`, rerun
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
