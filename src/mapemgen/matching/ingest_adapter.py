"""
ingest_adapter.py
=================
Adapts the ingestion + geometry-assignment output into the flat
`{"facts": [...]}` shape the matching engine consumes.

It does four things (Step 1 — geometry-aware):
  1. Flatten facts out of `extracted_facts.source_files[].extracted_facts`.
  2. Unwrap each fact's data: payload {"value": X} -> payload usable by transforms.
     (Falls back to a top-level `value` if a parser still emits the old shape.)
  3. Convert float `confidence` -> "high"/"medium"/"low" (engine uses levels).
  4. Inject instance keys: for facts the geometry-assignment stage placed, copy
     target_scope.intersection_ref / lane_ref INTO the fact payload, where the
     engine's InstanceResolver looks (payload.intersection_ref / payload.lane_ref).

Step 2 (DONE): route non-geometry facts (phase / label) to a lane. Phase facts
can't carry lane_ref (assignment's internal id) but carry a movement_ref /
phase_ref. assignment emits `movement_lane_mappings`
({movement_ref, lane_ref, phase_refs[], requires_context_match, ...});
`build_movement_to_lane` indexes it by movement_ref AND phase_ref, and
`_inject_nongeometry_scope` resolves each phase fact's ref to a lane_ref.
requires_context_match mappings are injected but marked provisional. Facts with
no ref, or an unmapped one, stay intersection-scoped rather than guessed. An
explicit --movement-map file can override / fill gaps.

Usage:
    python ingest_adapter.py \
        --facts extracted_facts.partial.json \
        --assignments geometry_assignments.partial.json \
        --out facts.json
    # --assignments is optional; without it you get unwrap + confidence only.
"""
import argparse
import json
import sys


# --- confidence float -> engine level ---------------------------------------
# Thresholds are deliberately simple and adjustable. The engine reasons in
# levels; the original float is preserved in payload["_confidence_score"] so the
# confidence workstream can still use the precise value later.
def confidence_to_level(c, high=0.8, medium=0.5):
    if isinstance(c, str):
        return c if c in ("high", "medium", "low") else "medium"
    try:
        c = float(c)
    except (TypeError, ValueError):
        return "medium"
    if c >= high:
        return "high"
    if c >= medium:
        return "medium"
    return "low"


def _fact_name(fact):
    return fact.get("fact_name") or fact.get("fact_type") or ""


def _unwrap_payload(fact):
    """Return a dict payload usable by transforms.
    Canonical shape is payload={"value": X}; older parsers used a top-level
    `value`. We normalise so the engine/transforms receive X directly, wrapped
    in a dict if X isn't already one. Sibling keys placed alongside `value`
    (instance keys, movement_id, etc.) are PRESERVED so routing can use them."""
    payload = fact.get("payload")
    siblings = {}
    if isinstance(payload, dict) and "value" in payload:
        value = payload["value"]
        siblings = {k: v for k, v in payload.items() if k != "value"}
    elif "value" in fact:
        value = fact["value"]
    elif isinstance(payload, dict):
        value = payload            # already a usable dict
    else:
        value = payload
    if isinstance(value, dict):
        result = dict(value)
    else:
        result = {"value": value}
    # carry across instance keys / movement_id / etc. without clobbering value data
    for k, v in siblings.items():
        result.setdefault(k, v)
    return result


def flatten_facts(extracted):
    """Pull facts out of the nested ingestion output into a flat list."""
    if isinstance(extracted, list):
        return [dict(f) for f in extracted]
    flat = []
    for source in extracted.get("source_files", []):
        for fact in source.get("extracted_facts", []):
            item = dict(fact)
            item.setdefault("source_file", source.get("source_file"))
            item.setdefault("file_type", source.get("file_type"))
            flat.append(item)
    # some pipelines may already provide a flat "facts"/"extracted_facts" list
    if not flat:
        for key in ("facts", "extracted_facts"):
            if isinstance(extracted.get(key), list):
                return [dict(f) for f in extracted[key]]
    return flat


def build_scope_map(assignments):
    """fact_id -> {intersection_ref, lane_ref} from the assignment output."""
    if not assignments:
        return {}
    scope = {}
    for a in assignments.get("assigned_facts", []):
        fid = a.get("fact_id")
        ts = a.get("target_scope") or {}
        if fid:
            scope[fid] = {k: v for k, v in {
                "intersection_ref": ts.get("intersection_ref"),
                "lane_ref": ts.get("lane_ref"),
            }.items() if v is not None}
    return scope


def build_movement_to_lane(assignments, movement_map=None):
    """ref -> {intersection_ref, lane_ref, requires_context_match}, where ref is a
    movement_ref OR a phase_ref.

    Phase/label facts can't carry lane_ref (it's an internal id assignment
    creates) but they carry a movement_ref / phase_ref. assignment now emits a
    `movement_lane_mappings` list ({movement_ref, lane_ref, phase_refs[],
    requires_context_match, ...}); we index it by BOTH the movement_ref and each
    of its phase_refs so a phase fact can resolve via either. Sources, in order:
      1. assignment's `movement_lane_mappings` (primary);
      2. legacy `lanes[].movement_id` (back-compat);
      3. an explicit movement_map file (override / fill-in).
    Mappings flagged `requires_context_match` are kept but marked provisional.
    Returns {} if nothing available — phase facts then degrade gracefully.
    """
    table = {}

    if assignments:
        # 1. primary: movement_lane_mappings
        for m in assignments.get("movement_lane_mappings", []):
            lane_ref = m.get("lane_ref")
            if not lane_ref:
                continue
            target = {
                "intersection_ref": m.get("intersection_ref"),
                "lane_ref": lane_ref,
                "requires_context_match": bool(m.get("requires_context_match")),
            }
            mv = m.get("movement_ref")
            if mv is not None:
                table[str(mv)] = target
            for ph in m.get("phase_refs", []) or []:
                table.setdefault(str(ph), target)

        # 2. legacy: movement_id carried on assigned lanes
        for lane in assignments.get("lanes", []):
            mv = lane.get("movement_id") or lane.get("movement")
            if mv is not None and lane.get("lane_ref"):
                table.setdefault(str(mv), {
                    "intersection_ref": lane.get("intersection_ref"),
                    "lane_ref": lane.get("lane_ref"),
                    "requires_context_match": False,
                })

    # 3. explicit map file overrides / fills in
    if movement_map:
        for ref, target in movement_map.items():
            if isinstance(target, dict):
                table[str(ref)] = {
                    "intersection_ref": target.get("intersection_ref"),
                    "lane_ref": target.get("lane_ref"),
                    "requires_context_match": bool(target.get("requires_context_match", False)),
                }
            else:  # bare lane_ref string
                entry = table.get(str(ref), {"requires_context_match": False})
                entry["lane_ref"] = target
                table[str(ref)] = entry

    return table


def _route_refs(fact, payload):
    """Candidate refs to route a phase/label fact by, in order: movement_ref,
    movement_id, movement, then phase_ref. (assignment's semantic step may add
    phase_ref; controller config may carry a movement_ref.)"""
    refs = []
    for src in (payload, fact, fact.get("payload") or {}):
        if isinstance(src, dict):
            for key in ("movement_ref", "movement_id", "movement", "phase_ref"):
                v = src.get(key)
                if v is not None and str(v) not in refs:
                    refs.append(str(v))
    return refs


def _inject_nongeometry_scope(fact, payload, movement_to_lane):
    """Route phase/label facts to a lane via movement_ref / phase_ref -> lane_ref.

    Uses assignment's movement_lane_mappings (indexed by movement_ref and
    phase_ref). If a mapping is flagged requires_context_match, the lane_ref is
    still injected but marked provisional so downstream treats it as needing
    confirmation rather than certain. Facts with no ref, or an unmapped one, stay
    intersection-scoped rather than being guessed.
    """
    refs = _route_refs(fact, payload)
    if not refs:
        return payload
    for ref in refs:
        target = movement_to_lane.get(ref)
        if target and target.get("lane_ref"):
            payload["lane_ref"] = target["lane_ref"]
            if target.get("intersection_ref") and "intersection_ref" not in payload:
                payload["intersection_ref"] = target["intersection_ref"]
            if target.get("requires_context_match"):
                payload["_lane_ref_provisional"] = True   # needs context confirmation
            return payload
    # had a ref but none mapped — keep visible for debugging
    payload.setdefault("_unmapped_movement_ref", refs[0])
    return payload


def adapt(extracted, assignments=None, movement_map=None,
          high=0.8, medium=0.5):
    facts = flatten_facts(extracted)
    scope_map = build_scope_map(assignments)
    movement_to_lane = build_movement_to_lane(assignments, movement_map)
    out = []
    for i, fact in enumerate(facts):
        name = _fact_name(fact)
        payload = _unwrap_payload(fact)
        fid = fact.get("fact_id") or f"f{i:05d}"

        # inject instance keys from geometry assignment (matched by fact_id)
        if fid in scope_map:
            payload.update(scope_map[fid])
        else:
            # non-geometry (phase/label): route via movement_id -> lane_ref
            payload = _inject_nongeometry_scope(fact, payload, movement_to_lane)

        # preserve the original float confidence for the confidence workstream
        raw_conf = fact.get("confidence")
        if isinstance(raw_conf, (int, float)):
            payload.setdefault("_confidence_score", raw_conf)

        out.append({
            "fact_id": fid,
            "fact_name": name,
            "payload": payload,
            "confidence": confidence_to_level(raw_conf, high, medium),
            "source_file": fact.get("source_file") or fact.get("evidence_location", ""),
        })
    return {"facts": out}


def main(argv=None):
    p = argparse.ArgumentParser(description="Adapt ingestion/assignment output for the matching engine")
    p.add_argument("--facts", required=True, help="extracted_facts(.partial).json")
    p.add_argument("--assignments", default=None, help="geometry_assignments.partial.json (optional)")
    p.add_argument("--movement-map", default=None,
                   help="movement_id -> lane_ref map (json, optional); bridges phase facts to lanes")
    p.add_argument("--out", required=True, help="output facts.json for the engine")
    p.add_argument("--high", type=float, default=0.8, help="confidence >= high -> 'high'")
    p.add_argument("--medium", type=float, default=0.5, help="confidence >= medium -> 'medium'")
    args = p.parse_args(argv)

    extracted = json.load(open(args.facts, encoding="utf-8"))
    assignments = json.load(open(args.assignments, encoding="utf-8")) if args.assignments else None
    movement_map = json.load(open(args.movement_map, encoding="utf-8")) if args.movement_map else None

    result = adapt(extracted, assignments, movement_map, args.high, args.medium)
    json.dump(result, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    n = len(result["facts"])
    scoped = sum(1 for f in result["facts"]
                 if "lane_ref" in f["payload"])
    unmapped = sum(1 for f in result["facts"]
                   if "_unmapped_movement_ref" in f["payload"])
    provisional = sum(1 for f in result["facts"]
                      if f["payload"].get("_lane_ref_provisional"))
    print(f"[ok] wrote {args.out}: {n} facts ({scoped} with lane_ref, "
          f"{provisional} provisional/requires-context, {unmapped} with an unmapped ref)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
