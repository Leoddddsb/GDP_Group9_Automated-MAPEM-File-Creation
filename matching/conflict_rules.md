# Conflict Detection — Calculation Rules

> Defines the `conflict` variable the matching engine emits for every field.
> This variable is the **input to the confidence function** (a `ConfidencePolicy`).
>
> **All tolerances are configuration**, in `matching_rules.yaml` →
> `conflict_detection`. Edit numbers there during debugging; no code change.

---

## 1. What "conflict" means

For one MAPEM field, several candidate sources may hit (e.g. a P1 CAD fact and a
P3 OSM fact). Each produces a value. The engine:

1. Picks the **chosen value** (highest-priority source).
2. Compares every other candidate against the chosen value.
3. Counts how many **agree** (corroborate) vs **disagree** (conflict), using a
   per-field-type tolerance.

That count + the priority info is the `conflict` variable.

---

## 2. The `conflict` variable (one per field)

The conflict variable is **flat at the top level** — every field a confidence
function needs is at the top, so a function can read `conflict["disagreement_count"]`
directly. The top-level numbers describe the **chosen value's group** (the
"primary group"). A `groups` breakdown and the AND result are also present for
richer logic.

```json
{
  "candidate_count": 3,            // sources hitting the chosen value's group
  "agreement_count": 2,            // within tolerance of the chosen value
  "disagreement_count": 1,         // outside tolerance  ← conflicts on the value
  "priority_used": "P1",           // priority label of the chosen source
  "priority_spread": ["P1","P2","P3"], // priorities across ALL hitting sources
  "max_divergence": 4.995,         // largest disagreement distance
  "divergence_unit": "m",          // m | deg | null (exact types)
  "tolerance_applied": 2.0,        // tolerance used for this field type
  "field_type": "coordinate",      // which tolerance rule applied
  "pending": false,                // true if values not computable yet

  // --- grouping detail (optional to use) ---
  "primary_group": "geometry",
  "all_required_groups_satisfied": true,
  "missing_groups": [],            // required fact_groups with no hit (AND)
  "total_candidate_count": 4,      // across ALL groups (incl. AND inputs)
  "groups": {                      // per-group conflict (same fields as above)
    "geometry": { "candidate_count": 3, "agreement_count": 2, ... },
    "coordinate_reference": { "candidate_count": 1, ... }
  }
}
```

For **single-group fields** (most fields) the top level simply mirrors that one
group. For **multi-group fields** the top level mirrors the primary group, and
`groups` / `missing_groups` expose the rest.

When transforms are not yet implemented, `pending=true` and the value-dependent
fields (`agreement_count`, `disagreement_count`, `max_divergence`) are `null`;
the count/priority/spread fields are always available.

> **Ownership.** The engine PRODUCES this variable (class `ConflictDetector` in
> matching_engine.py performs the coordinate/node_delta/integer_id/enum/angle
> tolerance comparison). A confidence function does NOT need to recompute conflict
> — it CONSUMES this variable. See §5.

---

## 2a. Grouping: within-group OR, across-group AND

A MAPEM field can require evidence from several fact_groups. The engine treats
them as: **within a fact_group, sources compete (OR — priority pick); across
fact_groups, all are required (AND)**. Geometry groups (`lane_geometry`,
`road_layout_geometry`) collapse into one logical `geometry` slot (OR among
themselves). Config lives in `matching_rules.yaml → group_logic`.

Consequence for conflict:
- **Conflict is computed WITHIN a group** — candidates there compete for the
  same value, so "agree vs disagree" is meaningful.
- **Across groups is AND** — they supply complementary information (e.g. geometry
  + coordinate system), not rival values, so they are not compared against each
  other. If a required group has no hit, the field is `manual_review` and
  `missing_groups` lists it.

Multi-group fields: `refPoint.lat/long` (geometry + coordinate_reference),
`nodeList.delta` (geometry + coordinate_reference), `connectingLane.lane`
(connection_topology + movement_semantics), `signalGroup`
(signal_control_semantics + connection_topology).

---

## 3. Calculation procedure (per field)

```
1. Collect every source that hit (fact present + in scope).
2. Run each source's transform pipeline → its candidate value v_i.
3. chosen = the value from the best-priority source (P1 < P2 < P3 < F).
4. For each candidate v_i:
     look up the field's tolerance type (see §4)
     compute divergence(v_i, chosen):
        - coordinate / node_delta : ground distance in metres
        - integer_id / enum       : 0 if equal, ∞ if not
        - angle                   : angular difference in degrees
     if divergence <= tolerance  → agree
     else                        → disagree
5. Emit the conflict variable.
```

`agreement_count` includes the chosen value itself (it trivially agrees).

---

## 4. Tolerance table (the part you tune)

From `matching_rules.yaml → conflict_detection.tolerances`:

| field_type | method | default tolerance | applies to |
|---|---|---|---|
| `coordinate` | ground_distance_m | **2.0 m** | refPoint.lat, refPoint.long |
| `node_delta` | ground_distance_m | **1.0 m** | nodeList.nodes[].delta |
| `integer_id` | exact | **0** | signalGroup, LaneID, id.region, id.id |
| `enum` | exact | — | laneType, directionalUse, sharedWith |
| `angle` | angular_deg | **15°** | ingressApproach, egressApproach |
| `default` | exact | — | anything not mapped above |

**method meanings**
- `ground_distance_m` — values are integer 1/10⁷-degree coordinates; the engine
  converts the difference to approximate metres (1e-7° ≈ 0.0111 m) and compares.
- `exact` — equal → divergence 0; not equal → divergence ∞ (always a conflict).
- `angular_deg` — smallest angle between two bearings, in degrees.

**Field → type mapping** is in `conflict_detection.field_type_map` (glob patterns).
To change how a field's conflicts are judged, point it at a different type, or
edit that type's tolerance.

> These defaults are starting points chosen by the engine author. Expect to
> tune them during testing — e.g. tighten coordinate tolerance once the CRS
> transform accuracy is known.

---

## 5. How the confidence function uses it

The confidence teammate writes a `ConfidencePolicy` whose input is this
`conflict` variable. Example shapes their function could take:

```python
class TeammateConfidencePolicy(ConfidencePolicy):
    def from_conflict(self, conflict):
        if not conflict["all_required_groups_satisfied"]:
            return "low"                          # a required evidence group is missing
        if conflict["pending"]:
            return "unknown"                      # values not computed yet
        if conflict["disagreement_count"] and conflict["disagreement_count"] > 0:
            return "low"                          # sources contradict within a group
        if conflict["candidate_count"] >= 2:
            return "high"                         # multiple sources corroborate
        if conflict["primary_priority"] == "F":
            return "low"                          # only a fallback source
        return "medium"                           # single ok source, no conflict
```

They can also drill into `conflict["groups"][g]` for per-group logic, or use
`max_divergence` for finer grading (small disagreement → medium, large → low).

---

## 6. Worked examples

**Coordinate, one close + one far (tolerance 2.0 m)**
```
chosen = 538007550 (P1)
candidates: 538007550 (P1), 538007600 (P2, ~0.55 m), 538008000 (P3, ~5.0 m)
→ agreement_count = 2, disagreement_count = 1, max_divergence = 4.995 m
```

**Integer id, one matching + one different (exact)**
```
chosen = 3 (P1)
candidates: 3 (P1), 3 (P2), 5 (P3)
→ agreement_count = 2, disagreement_count = 1, max_divergence = null
```

**Single source, no rivals**
```
chosen = X (P1), only one candidate
→ candidate_count = 1, disagreement_count = 0
```

---

## 7. Where each piece lives

| Piece | Location | Who edits |
|---|---|---|
| Tolerance values & field mapping | `matching_rules.yaml → conflict_detection` | you (debugging) |
| Conflict computation | `matching_engine.py → ConflictDetector` | engine owner |
| The confidence function | a `ConfidencePolicy` subclass | confidence teammate |

The three are decoupled: tuning tolerances never touches code; writing the
confidence function never touches the engine.
