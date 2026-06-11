# Fusion stage (`src/mapemgen/fusion/`)

Reads the matching stage's `mapped_evidence.json` and produces a clean, nested,
MAPEM-shaped model for the **encoding** stage. Fusion does **not** encode.

```
matching ─▶ mapped_evidence.json ─▶ [ fuse.py ] ─▶ fused_model.json (+ fusion_report.json) ─▶ encoding ─▶ MAPEM file
```

Matching and fusion connect only through the `mapped_evidence.json` contract
(see the matching module's `output_schema.md`).

## What fusion does

1. **Parse** each flat, indexed `target_path`
   (e.g. `mapData.intersections[0].laneSet[1].connectsTo[0].signalGroup`).
2. **Assemble** the nested structure (intersections → laneSet → connectsTo → …).
3. **Adjudicate** each field by its matching status:
   | matching status | fusion decision |
   |---|---|
   | `matched` | accept the value |
   | `matched_with_conflict` | accept, record in `conflicts` |
   | `manual_review_required` **with a value** | keep as **provisional**, record in `needs_review` |
   | `unresolved` / `pending_transform` / review with no value | leave `null`, record in `gaps` |
4. **Cross-field consistency checks** — independent, toggleable rules
   (reference integrity, uniqueness, required/non-empty, range sanity).
5. **Emit**
   - `fused_model.json` — nested MAPEM-shaped values (`null` where unresolved)
   - `fusion_report.json` — per-field decision + provenance + gaps + conflicts + issues

## Run

```bash
python fuse.py --evidence mapped_evidence.json \
               --out fused_model.json --report fusion_report.json
```

## `fused_model.json` shape (for the encoding stage)

```json
{
  "header": { "protocolVersion": 2, "messageID": 5, "stationID": 100 },
  "mapData": {
    "msgIssueRevision": 1,
    "intersections": [
      { "id": { "region": 50050, "id": 337 },
        "revision": 1,
        "refPoint": { "lat": null, "long": null },
        "laneWidth": 350,
        "laneSet": [
          { "laneID": 1,
            "laneAttributes": { "directionalUse": "both", "laneType": "vehicle", "sharedWith": null },
            "connectsTo": [ { "connectingLane": { "lane": null, "maneuver": null }, "signalGroup": 1 } ] }
        ],
        "signalHeadLocations": [ { "nodeXY": null } ] }
    ]
  }
}
```

`null` means fusion could not resolve that field yet — the encoding stage / a human
fills or omits it. The `fusion_report.json` says why (see `gaps`).

## Consistency rules

12 generic structural-integrity rules are registered (R01–R12): reference integrity
(R09 connectingLane references an existing laneID), uniqueness (R02 intersection id,
R07 laneID), required/non-empty (R01/R05/R06), range/type sanity (R04/R08/R12), and
structural coherence (R03/R10/R11). Each rule is independent and toggleable:

```python
fuse.fuse(evidence)                                  # all rules
# disable specific rules at call sites if needed
```

Add a rule by writing a `@_rule(id, description, severity)` function that yields
`{"where", "issue"}`. **MAPEM/C-Roads-specific** constraints (maneuver enum ranges,
approach references, conditionally-required fields) are intentionally NOT included
yet — add them as new rules once the standard's requirements are confirmed.

## Status / TODO

- [x] path parsing + nested assembly (single and multi-intersection)
- [x] status adjudication (accept / provisional / gap)
- [x] 12 generic consistency rules (toggleable registry)
- [ ] MAPEM/C-Roads-specific consistency rules (pending standard confirmation)
- [ ] adjudication tuning for real conflicts (pending real data)
- [ ] end-to-end on real `mapped_evidence.json` (pending real facts upstream)
