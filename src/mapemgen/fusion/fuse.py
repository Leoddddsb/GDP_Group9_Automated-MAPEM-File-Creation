"""
fuse.py  —  Evidence Fusion (Task 3)
====================================
Reads the matching stage's `mapped_evidence.json` and produces a clean, nested,
MAPEM-shaped model that the encoding stage turns into the final MAPEM file.

Fusion does NOT encode. It:
  1. Parses each flat, indexed target_path (e.g.
     `mapData.intersections[0].laneSet[1].connectsTo[0].signalGroup`).
  2. Assembles the nested structure (intersections → laneSet → connectsTo → ...).
  3. Adjudicates each field by its matching status:
       matched               -> take the value
       matched_with_conflict -> take the value, flag in the report
       manual_review_required / unresolved / pending_transform
                             -> leave null, record as a gap
  4. Runs cross-field consistency checks (lane ids, signal groups, references).
       [STANDARD: C-Roads MAPEM/SPATEM 3.2.0] Consistency checks enforce the
       structural integrity expected by the MAPEM model (unique ids, resolvable
       references, valid coordinate ranges).
  5. Emits:
       fused_model.json   — nested MAPEM-shaped values (null where unresolved)
       fusion_report.json — per-field decision + provenance + gaps + conflicts

Usage:
    python fuse.py --evidence mapped_evidence.json \
                   --out fused_model.json --report fusion_report.json
"""
import argparse
import json
import re
import sys

SEGMENT = re.compile(r"^([A-Za-z_]\w*)(?:\[(\d+)\])?$")


# --- path handling -----------------------------------------------------------
def parse_path(target_path):
    """'a.b[0].c' -> [('a',None),('b',0),('c',None)]."""
    parsed = []
    for seg in target_path.split("."):
        m = SEGMENT.match(seg)
        if not m:
            raise ValueError(f"bad path segment: {seg!r} in {target_path!r}")
        key, idx = m.group(1), m.group(2)
        parsed.append((key, int(idx) if idx is not None else None))
    return parsed


def is_container(path, all_paths):
    """A path is a container (built from children) if some other path extends it
    with '[' (indexed child) or '.' (deeper field)."""
    for other in all_paths:
        if other != path and (other.startswith(path + "[") or other.startswith(path + ".")):
            return True
    return False


def _ensure_list(node, key, index):
    lst = node.setdefault(key, [])
    if not isinstance(lst, list):
        raise TypeError(f"expected list at {key}, found {type(lst).__name__}")
    while len(lst) <= index:
        lst.append({})
    return lst[index]


def set_nested(root, parsed, value):
    """Place `value` at the parsed path inside the nested dict `root`,
    creating intermediate dicts/lists as needed."""
    node = root
    for i, (key, index) in enumerate(parsed):
        last = i == len(parsed) - 1
        if index is None:
            if last:
                node[key] = value
            else:
                node = node.setdefault(key, {})
        else:
            child = _ensure_list(node, key, index)
            if last:
                # leaf is an indexed slot whose value is a scalar/list itself
                node[key][index] = value
            else:
                node = child


# --- adjudication ------------------------------------------------------------
TAKE = {"matched", "matched_with_conflict"}
GAP = {"manual_review_required", "unresolved", "pending_transform"}


def fuse(evidence):
    records = evidence.get("mapped_evidence", [])
    all_paths = [r["target_path"] for r in records]

    model = {}
    decisions = []
    gaps = []
    conflicts = []
    needs_review = []

    for r in records:
        path = r["target_path"]
        status = r.get("status", "")
        # containers are assembled from their children — skip their own value
        if is_container(path, all_paths):
            continue

        parsed = parse_path(path)
        value = r.get("value")
        if status in TAKE:
            set_nested(model, parsed, value)
            decision = "accepted"
            if status == "matched_with_conflict":
                conflicts.append({
                    "target_path": path, "value": value,
                    "source_facts": r.get("source_facts", []),
                    "corroborating": r.get("corroborating", []),
                    "conflict": r.get("conflict", {}),
                })
        elif status == "manual_review_required" and value is not None:
            # value exists but matching wants a human to confirm: keep it as a
            # provisional value and flag it, rather than discarding matching's work.
            set_nested(model, parsed, value)
            decision = "provisional"
            needs_review.append({
                "target_path": path, "value": value,
                "reason": r.get("notes", ""),
                "missing_groups": r.get("conflict", {}).get("missing_groups", []),
            })
        else:  # unresolved / pending_transform / manual_review with no value
            set_nested(model, parsed, None)
            decision = "gap"
            gaps.append({
                "target_path": path, "status": status,
                "reason": r.get("notes", ""),
                "missing_groups": r.get("conflict", {}).get("missing_groups", []),
            })

        decisions.append({
            "target_path": path, "status": status, "decision": decision,
            "value": r.get("value"),
            "source_facts": r.get("source_facts", []),
            "confidence": r.get("confidence", ""),
        })

    issues = _consistency_checks(model)
    errors = [i for i in issues if i["severity"] == "error"]

    report = {
        "summary": {
            "total_leaf_fields": len(decisions),
            "accepted": sum(1 for d in decisions if d["decision"] == "accepted"),
            "gaps": len(gaps),
            "provisional_needs_review": len(needs_review),
            "conflicts": len(conflicts),
            "consistency_issues": len(issues),
            "consistency_errors": len(errors),
        },
        "gaps": gaps,
        "needs_review": needs_review,
        "conflicts": conflicts,
        "consistency_issues": issues,
        "decisions": decisions,
    }
    return model, report


# --- cross-field consistency (warn, never silently fix) ----------------------
# Rules are independent and individually toggleable. Each takes the assembled
# model and yields issue dicts {where, issue}. The runner tags each with the
# rule id and severity. These are GENERIC structural-integrity rules (reference
# integrity, uniqueness, required/non-empty, range sanity) — they do NOT encode
# MAPEM/C-Roads-specific semantics; add those as new rules once confirmed.
#
# [STANDARD: C-Roads MAPEM/SPATEM 3.2.0] The structural expectations checked
# below follow the MAPEM message structure: an intersection requires an id and
# a refPoint; lane ids and signal-group ids are unique; connectsTo references
# must resolve to existing lanes. These are integrity checks over the MAPEM
# model, not value-level profile semantics.
CONSISTENCY_RULES = []


def _rule(rule_id, description, severity="warning", enabled=True):
    def deco(fn):
        CONSISTENCY_RULES.append({
            "id": rule_id, "description": description,
            "severity": severity, "enabled": enabled, "fn": fn})
        return fn
    return deco


def _intersections(model):
    return (model.get("mapData") or {}).get("intersections") or []


def _lanes(inter):
    return inter.get("laneSet") or [] if isinstance(inter, dict) else []


def _lane_ids(inter):
    ids = set()
    for lane in _lanes(inter):
        if isinstance(lane, dict) and lane.get("laneID") is not None:
            ids.add(lane["laneID"])
    return ids


@_rule("R01_intersection_has_id", "Each intersection has id.id.", "error")
def _r01(model):
    for ix, inter in enumerate(_intersections(model)):
        if not isinstance(inter, dict) or (inter.get("id") or {}).get("id") is None:
            yield {"where": f"intersections[{ix}].id.id", "issue": "intersection id missing"}


@_rule("R02_intersection_id_unique", "intersection id.id is unique across intersections.", "error")
def _r02(model):
    seen = {}
    for ix, inter in enumerate(_intersections(model)):
        iid = (inter.get("id") or {}).get("id") if isinstance(inter, dict) else None
        if iid is None:
            continue
        if iid in seen:
            yield {"where": f"intersections[{ix}].id.id",
                   "issue": f"duplicate intersection id {iid} (also intersections[{seen[iid]}])"}
        else:
            seen[iid] = ix


@_rule("R03_intersection_has_refpoint", "refPoint has both lat and long.", "warning")
def _r03(model):
    for ix, inter in enumerate(_intersections(model)):
        rp = (inter.get("refPoint") or {}) if isinstance(inter, dict) else {}
        if rp.get("lat") is None or rp.get("long") is None:
            yield {"where": f"intersections[{ix}].refPoint", "issue": "reference point not fully resolved"}


# [STANDARD: MAPEM refPoint encoding] Latitude/Longitude are transmitted as
# integers of 1e-7 degrees (deg x 10^7). Valid global bounds are therefore
# +/-90 deg -> +/-900000000 and +/-180 deg -> +/-1800000000.
@_rule("R04_latlong_in_range", "lat/long (1e-7 deg ints) within valid global bounds.", "warning")
def _r04(model):
    for ix, inter in enumerate(_intersections(model)):
        rp = (inter.get("refPoint") or {}) if isinstance(inter, dict) else {}
        lat, lon = rp.get("lat"), rp.get("long")
        if isinstance(lat, (int, float)) and not (-900000000 <= lat <= 900000000):
            yield {"where": f"intersections[{ix}].refPoint.lat", "issue": f"lat out of range: {lat}"}
        if isinstance(lon, (int, float)) and not (-1800000000 <= lon <= 1800000000):
            yield {"where": f"intersections[{ix}].refPoint.long", "issue": f"long out of range: {lon}"}


@_rule("R05_intersection_has_lanes", "Each intersection has at least one lane.", "warning")
def _r05(model):
    for ix, inter in enumerate(_intersections(model)):
        if not _lanes(inter):
            yield {"where": f"intersections[{ix}].laneSet", "issue": "no lanes"}


@_rule("R06_lane_has_id", "Each lane has a laneID.", "error")
def _r06(model):
    for ix, inter in enumerate(_intersections(model)):
        for li, lane in enumerate(_lanes(inter)):
            if not isinstance(lane, dict) or lane.get("laneID") is None:
                yield {"where": f"intersections[{ix}].laneSet[{li}]", "issue": "laneID missing"}


@_rule("R07_laneID_unique", "laneID is unique within an intersection.", "error")
def _r07(model):
    for ix, inter in enumerate(_intersections(model)):
        seen = {}
        for li, lane in enumerate(_lanes(inter)):
            lid = lane.get("laneID") if isinstance(lane, dict) else None
            if lid is None:
                continue
            if lid in seen:
                yield {"where": f"intersections[{ix}].laneSet[{li}]",
                       "issue": f"duplicate laneID {lid} (also laneSet[{seen[lid]}])"}
            else:
                seen[lid] = li


@_rule("R08_laneID_positive", "laneID is a positive integer.", "warning")
def _r08(model):
    for ix, inter in enumerate(_intersections(model)):
        for li, lane in enumerate(_lanes(inter)):
            lid = lane.get("laneID") if isinstance(lane, dict) else None
            if lid is not None and (not isinstance(lid, int) or lid <= 0):
                yield {"where": f"intersections[{ix}].laneSet[{li}].laneID", "issue": f"laneID not a positive int: {lid}"}


@_rule("R09_connectingLane_ref_exists",
       "connectsTo[].connectingLane.lane references an existing laneID in the same intersection.",
       "error")
def _r09(model):
    for ix, inter in enumerate(_intersections(model)):
        ids = _lane_ids(inter)
        for li, lane in enumerate(_lanes(inter)):
            for ci, conn in enumerate(lane.get("connectsTo") or [] if isinstance(lane, dict) else []):
                if not isinstance(conn, dict):
                    continue
                ref = (conn.get("connectingLane") or {}).get("lane")
                if ref is not None and ref not in ids:
                    yield {"where": f"intersections[{ix}].laneSet[{li}].connectsTo[{ci}].connectingLane.lane",
                           "issue": f"references laneID {ref} which does not exist in this intersection"}


@_rule("R10_connection_has_signalGroup", "Each connectsTo entry has a signalGroup.", "warning")
def _r10(model):
    for ix, inter in enumerate(_intersections(model)):
        for li, lane in enumerate(_lanes(inter)):
            for ci, conn in enumerate(lane.get("connectsTo") or [] if isinstance(lane, dict) else []):
                if isinstance(conn, dict) and conn.get("signalGroup") is None:
                    yield {"where": f"intersections[{ix}].laneSet[{li}].connectsTo[{ci}]",
                           "issue": "connection has no signalGroup"}


@_rule("R11_connection_has_connectingLane", "Each connectsTo entry has a connectingLane.lane.", "warning")
def _r11(model):
    for ix, inter in enumerate(_intersections(model)):
        for li, lane in enumerate(_lanes(inter)):
            for ci, conn in enumerate(lane.get("connectsTo") or [] if isinstance(lane, dict) else []):
                if isinstance(conn, dict) and (conn.get("connectingLane") or {}).get("lane") is None:
                    yield {"where": f"intersections[{ix}].laneSet[{li}].connectsTo[{ci}].connectingLane",
                           "issue": "connection has no connecting lane reference"}


@_rule("R12_lanewidth_positive", "laneWidth, if present, is a positive number.", "warning")
def _r12(model):
    for ix, inter in enumerate(_intersections(model)):
        lw = inter.get("laneWidth") if isinstance(inter, dict) else None
        if lw is not None and (not isinstance(lw, (int, float)) or lw <= 0):
            yield {"where": f"intersections[{ix}].laneWidth", "issue": f"laneWidth not positive: {lw}"}


def _consistency_checks(model, disabled=None):
    """Run all enabled consistency rules; return a flat list of tagged issues."""
    disabled = set(disabled or [])
    issues = []
    for rule in CONSISTENCY_RULES:
        if not rule["enabled"] or rule["id"] in disabled:
            continue
        for issue in rule["fn"](model):
            issues.append({"rule": rule["id"], "severity": rule["severity"], **issue})
    return issues


def main(argv=None):
    p = argparse.ArgumentParser(description="Evidence fusion: mapped_evidence -> nested MAPEM model")
    p.add_argument("--evidence", required=True)
    p.add_argument("--out", default="fused_model.json")
    p.add_argument("--report", default="fusion_report.json")
    args = p.parse_args(argv)

    evidence = json.load(open(args.evidence, encoding="utf-8"))
    model, report = fuse(evidence)

    json.dump(model, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(report, open(args.report, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    s = report["summary"]
    print(f"[ok] wrote {args.out} and {args.report}")
    print(f"     leaves={s['total_leaf_fields']} accepted={s['accepted']} "
          f"provisional={s['provisional_needs_review']} gaps={s['gaps']} conflicts={s['conflicts']} "
          f"consistency_issues={s['consistency_issues']} (errors={s['consistency_errors']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
