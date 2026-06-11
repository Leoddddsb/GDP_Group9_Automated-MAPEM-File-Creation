# Payload Contract — Parser Output → Transform Input

> Defines the **shape of each fact's `payload`** so the matching engine's
> transform pipelines (`transform_pipelines.yaml`) can compute values. The engine
> hands a chosen fact's `payload` to the FIRST transform in its pipeline, so the
> payload must match what that transform expects.
>
> This is the interface between the **parser team** (produces facts) and the
> **matching engine** (consumes them). Where a fact's payload is a wrapper dict,
> a leading extractor (`take_polyline`, `take_label`) pulls the field out.

Common envelope (every fact):
```json
{ "fact_id": "...", "fact_name": "<dictionary fact name>",
  "confidence": "high|medium|low",
  "payload": { ... see per-fact below ... } }
```
Instance keys go INSIDE payload so the engine can route facts to the right
instance: `intersection_ref`, `lane_ref`, `connection_ref` (whichever apply).

---

## Per-field payload shapes

### Identity / metadata
| fact_name | payload shape | first transform | example |
|---|---|---|---|
| official_intersection_id_from_cad | string (the site code) | extract_int_from_site_code | `"337L"` → 337 |
| station_id_from_deployment_config | (from site_config, not a fact) | — | — |
| road_regulator_id_from_deployment_config | (from site_config) | — | — |

### Reference point — `refPoint.lat` / `refPoint.long`
Needs geometry **and** coordinate_reference (AND groups).
| fact_name | payload shape | example |
|---|---|---|
| lane_centreline_geometry_from_cad | list of `[E,N]` BNG points (or `{polyline:[...]}`) | `[[429157,434672],[429160,434680],...]` |
| stop_line_from_cad / approach_arm_geometry_from_cad | same point-list shape | `[[...],[...]]` |
| coordinate_reference_system_evidence_from_cad | `{ "crs": "EPSG:27700" }` | — |

Pipeline: `polygon_centroid → bng_to_wgs84_OSTN15 → take_lat/long → wgs84_to_int_1e7`.
**Coordinates must be BNG easting/northing (EPSG:27700) in metres.**

### Lane geometry — `nodeList.nodes[].delta`
| fact_name | payload shape |
|---|---|
| lane_centreline_nodes_from_cad | `{ "lane_ref": "...", "polyline": [[E,N],...] }` |
Pipeline: `as_point → relative_to_refpoint → delta_to_cm` (offsets from refPoint).

### Approaches — `ingressApproach` / `egressApproach`  ⚑ cross-lane
These are **not** computed from a single fact. The engine runs a prepass that
clusters all lane centrelines by bearing around the junction and classifies each
lane ingress/egress. So the parser must provide, **per lane**, a centreline:
| fact_name | payload shape |
|---|---|
| lane_direction_from_cad (and lane_centreline_*) | `{ "lane_ref": "L1", "polyline": [[E,N],...] }` (BNG, ordered from upstream→stopline) |

Point ordering matters: the polyline should run in the direction of travel so
ingress/egress classification is correct. The engine then sets the approach id;
no per-lane transform input beyond the polyline is needed.

### Signal group — `connectsTo[].signalGroup`
| fact_name | payload shape | example |
|---|---|---|
| phase_label_from_controller_config | phase label string (or `{phase_label:"A"}`) | `"A"` → 1 |
Dummy phases (e.g. U V W X Y Z A2) are dropped — listed in `site_config.dummy_phases`.

### Connecting lane — `connectsTo[].connectingLane.lane`  ⚑ cross-lane
Resolved by the engine prepass pairing ingress→egress lanes by geometry. Provide
lane centrelines (same shape as approaches above). Optionally a fact may carry an
explicit `{ "target_lane_id": ... }` to override geometric matching.

### Lane attributes
| fact_name | payload shape | first transform | example |
|---|---|---|---|
| lane_use_label_from_cad (→ laneType) | label string | lane_type_from_label | `"left turn"` → `"vehicle"` |
| lane_direction_from_cad (→ directionalUse) | label/bearing | directional_use_from_label | — |
| road_marking_or_sign_note_from_cad (→ sharedWith) | label string | shared_with_from_label | — |

---

## Rules of thumb for the parser

1. **Geometry → list of `[E,N]` BNG points** (metres, EPSG:27700). Wrap as
   `{lane_ref, polyline:[...]}` when the geometry belongs to a specific lane.
2. **Labels → plain strings** (phase letters, lane-use text). Wrappers OK if a
   `take_label` step is added.
3. **Always include the instance key** (`lane_ref`, `connection_ref`) so multi-
   lane / multi-connection facts route correctly.
4. **Cross-lane fields (approaches, connecting lane)**: just supply per-lane
   centrelines; the engine does the clustering/pairing.

If a payload can't match these shapes, add a leading extractor transform in
`transform_pipelines.yaml` rather than changing the engine.
