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

Step 2 (TODO, pending team decision): route non-geometry facts (phase / label)
to a lane. The assignment stage only scopes geometry facts, so phase/label facts
currently get no lane_ref and will resolve at intersection level only. Once the
parser carries an explicit phase->lane/movement reference (or assignment is
extended), add that mapping in `_inject_nongeometry_scope` below.

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
    in a dict if X isn't already one (so instance keys can be attached)."""
    payload = fact.get("payload")
    if isinstance(payload, dict) and "value" in payload:
        value = payload["value"]
    elif "value" in fact:
        value = fact["value"]
    elif isinstance(payload, dict):
        value = payload            # already a usable dict
    else:
        value = payload
    # transforms expect the raw value; but instance keys must live alongside it.
    # If value is a dict, keep it and add keys to it. Otherwise wrap it under
    # "value" so we still have somewhere to attach keys, and transforms that
    # take the whole payload can read payload["value"].
    if isinstance(value, dict):
        return dict(value)
    return {"value": value}


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


def _inject_nongeometry_scope(fact, payload):
    """STEP 2 placeholder: route phase/label facts to a lane.
    Pending the team decision on how phase->lane is expressed. If the parser
    later carries an explicit reference (e.g. payload['controls_lane'] or a
    movement id), map it to lane_ref here. For now this is a no-op."""
    return payload


def adapt(extracted, assignments=None,
          high=0.8, medium=0.5):
    facts = flatten_facts(extracted)
    scope_map = build_scope_map(assignments)
    out = []
    for i, fact in enumerate(facts):
        name = _fact_name(fact)
        payload = _unwrap_payload(fact)
        fid = fact.get("fact_id") or f"f{i:05d}"

        # inject instance keys from geometry assignment (matched by fact_id)
        if fid in scope_map:
            payload.update(scope_map[fid])
        else:
            payload = _inject_nongeometry_scope(fact, payload)

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
    p.add_argument("--out", required=True, help="output facts.json for the engine")
    p.add_argument("--high", type=float, default=0.8, help="confidence >= high -> 'high'")
    p.add_argument("--medium", type=float, default=0.5, help="confidence >= medium -> 'medium'")
    args = p.parse_args(argv)

    extracted = json.load(open(args.facts, encoding="utf-8"))
    assignments = json.load(open(args.assignments, encoding="utf-8")) if args.assignments else None

    result = adapt(extracted, assignments, args.high, args.medium)
    json.dump(result, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    n = len(result["facts"])
    scoped = sum(1 for f in result["facts"]
                 if "lane_ref" in f["payload"] or "intersection_ref" in f["payload"])
    print(f"[ok] wrote {args.out}: {n} facts ({scoped} with instance scope, "
          f"{n - scoped} intersection/unscoped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
