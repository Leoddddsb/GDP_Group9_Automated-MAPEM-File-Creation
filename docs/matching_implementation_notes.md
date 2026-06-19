# Matching Implementation Notes

This note records the matching-side fixes added during the 573L debugging pass.
It covers the code changes that must be preserved when teammate versions of the
matching rules, generator overlay, or transform overlay are refreshed.

## Files Updated

- `src/mapemgen/matching/matching_rules.yaml`
- `src/mapemgen/matching/generator_overlay.json`
- `src/mapemgen/matching/transforms_overlay.py`
- `src/mapemgen/matching/matching_engine.py`
- `src/mapemgen/matching/ingest_adapter.py` was not replaced by the teammate files and should keep its existing adapter fixes.

## Intersection ID

`ingest_adapter.py` injects `official_intersection_id_from_cad` from the extracted `site_id`.
For example, `573L` becomes the MAPEM intersection id `573` through the matching transform
`extract_int_from_site_code` / `extract_int_from_identifier`.

This avoids `id.id = null` when the source files do not contain a clean explicit MAPEM
intersection id fact.

## Approach Assignment

The assignment stage emits `approach_assignment_candidate_from_cad` facts per lane.
These must remain valid sources for:

- `mapData.intersections[].laneSet[].ingressApproach`
- `mapData.intersections[].laneSet[].egressApproach`
- `mapData.intersections[].laneSet[].laneAttributes.directionalUse`

The current logic is:

- A lane with a CAD stop line is treated as `ingress`.
- If an approach has one or more stop-line lanes, other lanes in the same approach can be treated as `egress` using `direction_basis = approach_stop_line_complement`.
- If no explicit direction or reliable prepass direction exists, the approach field remains unresolved rather than guessing.
- A lane must not receive both `ingressApproach` and `egressApproach`.

The generator overlay must keep these transform mappings:

```json
"mapData.intersections[].laneSet[].ingressApproach||approach_assignment_candidate_from_cad": [
  "approach_id_ingress"
],
"mapData.intersections[].laneSet[].egressApproach||approach_assignment_candidate_from_cad": [
  "approach_id_egress"
]
```

## Directional Use

`transforms_overlay.py` overrides `directional_use_from_label` for payload dictionaries:

- If payload has `direction: ingress`, output `ingress`.
- If payload has `direction: egress`, output `egress`.
- If payload has no explicit direction, output `unknown`.

This is necessary because the base transform sees text such as `approach_ref` and can
misclassify every lane as ingress.

`matching_engine.py` also protects `laneAttributes.directionalUse` selection:

- If explicit values `10`, `01`, or `11` exist, `00` unknown candidates cannot win only by majority.
- If all candidates are unknown, `00` is still allowed.

## RefPoint And CRS

The teammate overlay adds `junction_centre_lat` and `junction_centre_long`.
`matching_engine._analyze_lanes()` now computes `resolved["junction_centre"]` from the
CAD lane geometry prepass and converts it from BNG to WGS84 integer degrees.

This allows the rules to populate:

- `mapData.intersections[].refPoint.lat`
- `mapData.intersections[].refPoint.long`

from one junction-level centre instead of repeatedly choosing individual lane centroids.

## Transform Compatibility Fixes

The overlay also keeps compatibility wrappers for:

- `relative_to_refpoint`: accepts a WGS84 `refPoint` and converts it back to BNG before computing CAD offsets.
- `choose_node_xy_precision`: accepts either a single offset or a list of offsets.
- `approach_id_ingress` / `approach_id_egress`: first respect explicit payload `direction`, then fall back to prepass results.

These wrappers avoid `pending_transform` caused by payload shape mismatches.

## OSTN15 Grid Setup

The MAPEM environment uses British National Grid `EPSG:27700` to WGS84 `EPSG:4326`
conversion. Install the OSTN15 grid into the active virtual environment so pyproj can use
the best UK transformation.

Command used in this environment:

```powershell
.\mapem313\Scripts\python.exe -m pyproj sync --file uk_os_OSTN15_NTv2_OSGBtoETRS.tif --target-directory C:\Users\leovo\Desktop\GDP\mapem313\Lib\site-packages\pyproj\proj_dir\share\proj
```

The file should exist at:

```text
C:\Users\leovo\Desktop\GDP\mapem313\Lib\site-packages\pyproj\proj_dir\share\proj\uk_os_OSTN15_NTv2_OSGBtoETRS.tif
```

Verify:

```powershell
@'
from pyproj.transformer import TransformerGroup
g = TransformerGroup("EPSG:27700", "EPSG:4326")
print("OSTN15 best_available:", g.best_available)
print("unavailable operations:", len(g.unavailable_operations))
'@ | .\mapem313\Scripts\python.exe -
```

Expected:

```text
OSTN15 best_available: True
unavailable operations: 0
```

After installation, matching should no longer print the missing grid warning:

```text
Best transformation is not available due to missing Grid(...uk_os_OSTN15_NTv2_OSGBtoETRS.tif...)
```

If `mapem313` is deleted or rebuilt, rerun the `pyproj sync` command.

## 573L Verification Snapshot

After merging teammate files and preserving the fixes above, 573L produced:

```text
matching: fields=236 ok=226 manual_review=10 pending_transform=0
fusion: leaves=235 accepted=147 provisional=0 gaps=88 conflicts=35 consistency_errors=0
lanes: 32
ingressApproach: 11
egressApproach: 7
lanes with both ingress/egress: 0
directionalUse: 10 -> 11, 01 -> 7, 00 -> 14
connectsTo: 0
```

`connectsTo` remains unresolved because assignment still lacks reliable
`movement_lane_mappings`, `semantic_assignments`, or `lane_connection_candidate_*` evidence.
