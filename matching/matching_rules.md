# MAPEM Field Matching — Documentation

> How the matching stage turns extracted facts into MAPEM field values. This is
> the companion guide to `matching_rules.yaml`, `matching_engine.py`,
> `transform_pipelines.yaml`, `transforms.py` (+ overlay) and `conflict_rules.md`.

---

## 1. What matching does

Matching is a **site-agnostic engine** that maps extracted facts to MAPEM 3.2.0
fields according to rules defined in the MAPEM dictionary. For each field it
selects evidence by **population mode** and **source priority (P1–F)**, preserving
full source provenance and conflict information, and outputs `mapped_evidence.json`
for downstream evidence fusion and confidence scoring.

The whole thing is data-driven: rules are generated from the dictionary, and
priority, conflict tolerances, and grouping logic are all configurable.

```
MAPEM_Dictionary.xlsx ──(build_rules_from_dict.py)──▶ matching_rules.yaml
                                                            │
extracted_facts.json ─┐                                     │
site_config_<site>.yaml ─┼──▶ matching_engine.py ◀───────────┘
transform_pipelines.yaml ┘        │   ▲
transforms.py (+overlay) ─────────┘   │
                                      ▼
                              mapped_evidence.json
```

---

## 2. Source of truth: the dictionary

`matching_rules.yaml` is **generated** from `MAPEM_Dictionary.xlsx` — never
hand-edit its `fields` section. To change facts/priorities, edit the xlsx and run:

```bash
python build_rules_from_dict.py MAPEM_Dictionary.xlsx matching_rules.yaml
```

Profile knowledge the dictionary doesn't carry (constant values, c_roads_mandatory
flags, forbidden elements, config defaults, priority ranks, group logic, conflict
tolerances) lives in the generator's hand-authored OVERLAY.

---

## 3. Rule anatomy (a field in `matching_rules.yaml`)

```yaml
- target: mapData.intersections[].refPoint.lat   # MAPEM element path ([] = repeats)
  population_mode: geometry_derived               # how the value is obtained
  c_roads_mandatory: false                        # profile-required (ASN.1-optional)
  sources:                                        # candidate evidence
    - fact_name: lane_centreline_geometry_from_cad
      source_category: site_plans_and_cad_files
      subtype: cad_drawing
      fact_group: lane_geometry                   # grouping unit (see §6)
      priority: P1                                # P1<P2<P3<F
    - fact_name: coordinate_reference_system_evidence_from_cad
      fact_group: coordinate_reference
      priority: P2
```

Transforms are NOT here — they live in `transform_pipelines.yaml` (§5).

---

## 4. Population modes (how a field gets its value)

| population_mode | how the engine fills it |
|---|---|
| `constant` | fixed profile value from the overlay (protocolVersion=2, messageID=5) |
| `client_configured` | from `site_config` (e.g. stationID, region); may fall back to facts |
| `project_managed` | lifecycle counter (msgIssueRevision, intersection revision) |
| `system_generated` | assigned after extraction (LaneID auto-number) |
| `directly_extracted` | read from one source + transform (id.id) |
| `geometry_derived` | computed from spatial evidence + transform (refPoint, approaches, delta) |
| `evidence_fused` | combined multi-source evidence (laneType, signalGroup, connectingLane) |
| `must_exist` | synthetic container check (intersections, connectsTo) |

---

## 5. Transform pipelines (separate file)

`transform_pipelines.yaml` maps a source — by `target` glob + `fact_name` glob —
to an ordered chain of transform names from `transforms.py`'s `TRANSFORMS` registry
(loaded via `transforms_overlay.py`). The engine passes the chosen fact's `payload`
as the initial value into the first transform.

```yaml
- target: "*.refPoint.lat"
  fact_name: "*"
  transform: [polygon_centroid, bng_to_wgs84_OSTN15, take_lat, wgs84_to_int_1e7]
```

Context kwargs available to transforms that declare them (signature-aware):
`ref_point`, `dummy_phase_set`, `phase_order`, `scope`, `resolved`.

Payload shapes each fact must carry are specified in `payload_contract.md`.
If a transform is missing, errors, or a payload shape mismatches, the engine
degrades that field to `pending_transform` (it never crashes the run).

> **OSTN15 note:** `bng_to_wgs84_OSTN15` only delivers sub-metre accuracy if the
> OSTN15 grid is installed; otherwise pyproj silently uses a ~metre transform. The
> engine surfaces a `warnings` entry if the grid is missing — see
> `OSTN15_setup.md`.

---

## 6. Group logic: within-group OR, across-group AND

A field can require several `fact_group`s. The engine treats them as:

- **Within a fact_group → OR** — candidate sources compete; the best priority wins.
- **Across fact_groups → AND** — every required group must yield a winner, else the
  field is `manual_review` (`missing_groups` lists the gap).
- **Geometry groups are alternatives** — `lane_geometry` and `road_layout_geometry`
  collapse into one logical `geometry` slot (OR among themselves).

Config in `matching_rules.yaml → group_logic`. Multi-group fields:
`refPoint.lat/long`, `nodeList.delta` (geometry + coordinate_reference);
`connectingLane.lane` (connection_topology + movement_semantics);
`signalGroup` (signal_control_semantics + connection_topology).

Cross-lane fields (`ingressApproach`/`egressApproach`, `connectingLane.lane`) are
resolved by an engine prepass that clusters lane centrelines into approaches and
pairs ingress↔egress by geometry, storing results for per-lane transforms.

---

## 7. Priority (P1–F)

`priority_ranks: {P1: 1, P2: 2, P3: 3, F: 9}` in the YAML — edit to retune globally.
P1 is the first-choice source; F is fallback/future (participates, ranked last).
Site-level `priority_overrides` in `site_config` win over the rule-file label.
The selection logic is isolated in `SourceSelector` / `_effective_priority` (swappable).

---

## 8. Conflict & confidence

For each field the engine emits a `conflict` variable (candidate counts, agreement/
disagreement under per-type tolerances, priority spread, grouping result). It is the
input to the confidence function. Tolerances are data
(`matching_rules.yaml → conflict_detection`). Full spec: `conflict_rules.md`.

Ownership: the engine PRODUCES conflict (class `ConflictDetector`); the confidence
teammate writes a `ConfidencePolicy` that CONSUMES it.

---

## 9. Forbidden elements & two mandatory layers

`forbidden` (in the YAML) lists C-Roads prohibitions (lane-level maneuvers;
sharedWith bits 1 and 9; regional when roadSegments is used) — the engine reports
any that appear.

"Mandatory" has two layers: **ASN.1-mandatory** (the encoder enforces) and
**C-Roads-mandatory** (ASN.1-optional but profile-required — the engine must
self-enforce; flagged `c_roads_mandatory: true`, e.g. id.region, ingress/egress
Approach, connectsTo, signalGroup, intersections).

---

## 10. Output: `mapped_evidence.json`

One record per field: `target_path`, `value`, `population_mode`, `rule_applied`,
`source_facts`, `transforms_run`, `priority_used`, `confidence`, `conflict`,
`corroborating`, `status` (ok | manual_review | forbidden | pending_transform),
`notes`. Plus top-level `manual_review_items`, `validation_report`,
`forbidden_elements`, `warnings`, `summary`.

---

## 11. Run it

```bash
python matching_engine.py \
  --rules matching_rules.yaml \
  --facts extracted_facts.<site>.json \
  --config site_config_<site>.yaml \
  --transforms transforms_overlay \
  --pipelines transform_pipelines.yaml \
  --out mapped_evidence.json
```

`--pipelines` defaults to `transform_pipelines.yaml` next to the rules;
`--transforms` defaults to `transforms` (use `transforms_overlay` for the fixed
stubs + approach/connecting-lane resolution).

---

## 12. Files at a glance

| File | Role | Hand-edit? |
|---|---|---|
| `MAPEM_Dictionary.xlsx` | source of truth (facts + priority) | yes |
| `build_rules_from_dict.py` | generator + overlay | yes (overlay) |
| `matching_rules.yaml` | generated rules | no (regenerate) |
| `transform_pipelines.yaml` | per-source transform chains | yes |
| `transforms.py` | transform functions (teammate) | teammate |
| `transforms_overlay.py` | fixes/additions over transforms.py | yes |
| `site_config_<site>.yaml` | per-site human input | yes |
| `matching_engine.py` | the engine | yes |
| `payload_contract.md` | parser→transform payload shapes | ref |
| `conflict_rules.md` | conflict variable + tolerances | ref |

---

## 13. Status & next steps

Done: rules from xlsx, population-mode dispatch, P1–F priority, AND grouping,
conflict variable, transform integration (real values for id/refPoint/laneType/
signalGroup/approaches), graceful degradation, OSTN15 detection.

Pending (mostly external): OSTN15 grid install; parser payloads per contract;
real `extracted_facts.json` + end-to-end test; confidence function from teammate;
tolerance tuning; downstream schema sign-off with evidence fusion.
