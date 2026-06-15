"""
matching_engine.py — Generic MAPEM matching engine (v0)
=======================================================

A TOOL, not a one-site converter. It reads:
    - matching_rules.yaml          (the rules — shared across all sites)
    - extracted_facts.<site>.json  (any site's parser output)
    - site_config_<site>.yaml      (any site's human-filled config)
and produces:
    - mapped_evidence.<site>.json  (per-field value + provenance + confidence)

It contains NO site-specific logic. Anything that varies between sites lives in
the two input files above. The same engine binary processes site 337L, any Leeds
site, any Bathnes site, or any future site, unchanged.

-----------------------------------------------------------------------------
EXTENSIBILITY POINTS  (designed to be swapped WITHOUT touching engine core)
-----------------------------------------------------------------------------
  * ConfidencePolicy  — how confidence is scored and compared to a floor.
                        >>> CHANGE CONFIDENCE JUDGEMENT HERE <<<
  * SourceSelector    — how a winning source is chosen among candidates.
                        >>> CHANGE PRIORITY LOGIC HERE <<<
  * InstanceResolver  — how collection templates (foo[]) expand to instances.
                        (depends on the parser fact contract)
  * TransformRunner   — how named transforms are dispatched to implementations.

To change priority logic later:  subclass SourceSelector, pass it to the engine.
To change confidence logic later: subclass ConfidencePolicy, pass it to the engine.
The engine core (MatchingEngine) never needs editing for those changes.

-----------------------------------------------------------------------------
USAGE
-----------------------------------------------------------------------------
  python matching_engine.py \
      --rules   matching_rules.yaml \
      --facts   extracted_facts.partial.json \
      --config  site_config_337L.yaml \
      --out     mapped_evidence.partial.json

  # swap in custom strategies programmatically:
  engine = MatchingEngine(rules, transforms,
                          confidence_policy=MyConfidencePolicy(),
                          source_selector=MySourceSelector())
"""

from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML required:  pip install pyyaml")


# =============================================================================
# Data models
# =============================================================================
@dataclass
class Fact:
    """One extracted fact from a parser. The parser contract: every fact has a
    fact_name (matching the dictionary's Fact Name), a payload, and a confidence.
    Optional instance keys (intersection_ref, lane_ref, connection_ref) tell the
    engine which instance the fact belongs to."""
    fact_id: str
    fact_name: str = ""
    fact_type: str = ""          # legacy alias; fact_name preferred
    payload: dict = field(default_factory=dict)
    confidence: str = "medium"
    source_file: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Fact":
        return cls(
            fact_id=d.get("fact_id", "?"),
            fact_name=d.get("fact_name", d.get("fact_type", "")),
            fact_type=d.get("fact_type", ""),
            payload=d.get("payload", {}),
            confidence=d.get("confidence", "medium"),
            source_file=d.get("source_file", ""),
        )

    def matches_name(self, name: str) -> bool:
        return fnmatch.fnmatch(self.fact_name, name) or \
               fnmatch.fnmatch(self.fact_type, name)

    # convenience: instance keys live in payload (parser contract)
    def instance_key(self, level: str) -> Optional[str]:
        return self.payload.get(f"{level}_ref") if isinstance(self.payload, dict) else None


@dataclass
class EvidenceRecord:
    """One resolved MAPEM field → the mapped_evidence.json output unit."""
    target_path: str
    value: Any = None
    population_mode: str = ""
    rule_applied: str = ""
    source_facts: list = field(default_factory=list)
    transforms_run: list = field(default_factory=list)
    priority_used: str = ""
    confidence: str = "n/a"
    conflict: dict = field(default_factory=dict)
    notes: str = ""
    corroborating: list = field(default_factory=list)
    status: str = "ok"  # ok | manual_review | forbidden | pending_transform

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# =============================================================================
# EXTENSION POINT 1 — ConfidencePolicy  (>>> CHANGE CONFIDENCE JUDGEMENT HERE <<<)
# =============================================================================
class ConfidencePolicy:
    """Default confidence model: ordinal low < medium < high.

    Swap/subclass to change how confidence is scored and compared. The engine
    only ever calls .score() and .meets_floor(); as long as a subclass keeps
    those two methods, the engine core is unaffected.

    Example future change (5 levels, or numeric 0..1, or age-decay): override
    score() and/or meets_floor() in a subclass and pass it to MatchingEngine.
    """
    LEVELS = {"low": 1, "medium": 2, "high": 3}

    def score(self, confidence: Any) -> float:
        return self.LEVELS.get(str(confidence).lower(), 0)

    def meets_floor(self, fact_confidence: Any, floor: Optional[str]) -> bool:
        if not floor:
            return True
        return self.score(fact_confidence) >= self.score(floor)


# =============================================================================
# EXTENSION POINT 2 — SourceSelector  (>>> CHANGE PRIORITY LOGIC HERE <<<)
# =============================================================================
class SourceSelector:
    """Default selection: priority order.

    Among candidate (source, fact) pairs, pick the one with the lowest effective
    priority number whose fact meets the confidence floor. Other floor-passing
    candidates become corroborating; floor-failing ones are rejected.

    Swap/subclass to change selection logic (confidence-first, weighted score,
    priority floor, etc.). The engine only calls .select(); keep that signature
    and the engine core is unaffected.
    """

    def select(self, candidates: list, rule: dict, conf: ConfidencePolicy,
               effective_priority: Callable[[dict], int]):
        floor = rule.get("confidence_floor")
        ordered = sorted(candidates, key=lambda c: effective_priority(c[0]))
        winner = None
        corroborating, rejected = [], []
        for source, fact in ordered:
            if conf.meets_floor(fact.confidence, floor):
                if winner is None:
                    winner = (source, fact)
                else:
                    corroborating.append((source, fact))
            else:
                rejected.append((source, fact, "below confidence floor"))
        return winner, corroborating, rejected


# =============================================================================
# EXTENSION POINT 3 — InstanceResolver  (depends on parser fact contract)
# =============================================================================
class InstanceResolver:
    """Expands collection templates (paths containing '[]') into concrete
    instances, e.g. 'laneSet[].laneID' → laneSet[0], laneSet[1], ...

    Default contract (override for your parser's real structure):
      - Each fact may carry instance keys in its payload:
            intersection_ref, lane_ref, connection_ref
      - Distinct values of those keys define the set of instances at each level.
      - If no relevant facts exist, a collection has zero instances (and any
        c_roads_mandatory rule on it raises manual_review).

    This is intentionally isolated: when the Week-2 parser fact format is final,
    only this class changes — never the engine core.
    """

    LEVEL_KEYS = {
        "intersections": "intersection",
        "laneSet": "lane",
        "connectsTo": "connection",
        "nodes": "node",
    }

    def __init__(self, facts: list):
        self.facts = facts

    def _distinct(self, level_key: str, scope: dict) -> list:
        """Distinct instance ids at a level, optionally scoped to a parent."""
        vals = []
        for f in self.facts:
            key = f.payload.get(f"{level_key}_ref") if isinstance(f.payload, dict) else None
            if key is None:
                continue
            # honour parent scope (e.g. only lanes within intersection 0)
            ok = all((f.payload.get(f"{k}_ref") if isinstance(f.payload, dict) else None) == v for k, v in scope.items())
            if ok and key not in vals:
                vals.append(key)
        return vals

    def expand(self, template_path: str) -> list:
        """Return list of (concrete_path, scope_dict) for a templated path.

        scope_dict maps level → instance id, used to filter facts later.
        """
        # Split on the collection markers, walking left to right.
        segments = template_path.split("[]")
        # segments like: ['intersections', '.laneSet', '.connectsTo', '.signalGroup']
        results = [("", {})]  # (path_prefix, scope)
        for i, seg in enumerate(segments[:-1]):
            level_name = seg.lstrip(".").split(".")[-1]  # last token before []
            level_key = self.LEVEL_KEYS.get(level_name)
            new_results = []
            for prefix, scope in results:
                if level_key is None:
                    # unknown collection — emit a single index 0 (best effort)
                    instance_ids = ["0"]
                else:
                    instance_ids = self._distinct(level_key, scope) or []
                for idx, inst_id in enumerate(instance_ids):
                    new_prefix = f"{prefix}{seg}[{idx}]"
                    new_scope = dict(scope)
                    if level_key:
                        new_scope[level_key] = inst_id
                    new_results.append((new_prefix, new_scope))
            results = new_results
        # append the trailing segment (the leaf field name)
        tail = segments[-1]
        return [(f"{prefix}{tail}", scope) for prefix, scope in results]


# =============================================================================
# EXTENSION POINT 4 — TransformRunner  (dispatches named transforms)
# =============================================================================
class TransformNotImplemented(Exception):
    def __init__(self, name):
        super().__init__(name)
        self.name = name


class TransformRunner:
    """Runs a named transform pipeline against the teammate's transforms module.

    Integration contract (matches transforms.py):
      - Functions are looked up in the module's TRANSFORMS registry (a name→func
        dict) if present, else by attribute name.
      - Each function is called as func(value, **kwargs). kwargs are filled ONLY
        with the named parameters the function actually declares (signature-aware),
        drawn from a context pool: ref_point, dummy_phase_set, phase_order.
        This matches the teammate's `func(value, **context)` convention without
        the fragile "pass everything" behaviour.
      - A missing transform raises TransformNotImplemented; the engine catches it
        and marks the field 'pending_transform' (so the engine still runs).
    """

    def __init__(self, transforms_module):
        self.mod = transforms_module
        self.registry = getattr(transforms_module, "TRANSFORMS", {}) if transforms_module else {}

    def _resolve(self, name):
        if name in self.registry:
            return self.registry[name]
        return getattr(self.mod, name, None) if self.mod else None

    @staticmethod
    def _context_pool(ctx: dict) -> dict:
        manual = ctx.get("manual") or {}
        site = ctx.get("site_config") or {}
        cfg = ctx.get("config") or {}
        resolved = ctx.get("resolved") or {}
        pool = {
            "ref_point": resolved.get("refPoint"),
            "dummy_phase_set": manual.get("dummy_phases", site.get("dummy_phases")),
            "phase_order": cfg.get("phase_order", site.get("phase_order")),
            "output": cfg.get("lanetype_output"),   # e.g. 'sitemodel' | 'mapem'
            "scope": ctx.get("scope"),               # current instance ids
            "resolved": resolved,                    # cross-field results
        }
        return {k: v for k, v in pool.items() if v is not None}

    def run(self, names: list, initial_value: Any, ctx: dict):
        import inspect
        value = initial_value
        ran = []
        pool = self._context_pool(ctx)
        for name in names:
            func = self._resolve(name)
            if not callable(func):
                raise TransformNotImplemented(name)
            try:
                params = inspect.signature(func).parameters
                accepted = {k: v for k, v in pool.items() if k in params}
            except (TypeError, ValueError):
                accepted = {}
            value = func(value, **accepted)
            ran.append(name)
        return value, ran


# =============================================================================
# EXTENSION POINT 5 — ConflictDetector  (feeds the confidence function)
# =============================================================================
class ConflictDetector:
    """Builds the per-field `conflict` variable that the confidence function
    (a ConfidencePolicy) consumes. It decides, among the candidate values for
    one field, how many AGREE with the chosen value and how many CONFLICT.

    Tolerances are DATA (from rules['conflict_detection']) — edit them during
    debugging without touching code. See conflict_rules.md for the spec.

    Output shape (one per field):
        {
          candidate_count, agreement_count, disagreement_count,
          priority_used, priority_spread, max_divergence, divergence_unit,
          tolerance_applied, field_type, pending
        }
    'pending' is True when candidate VALUES can't be computed yet (transforms
    not implemented); count/priority info is still filled.
    """

    def __init__(self, conflict_cfg: dict):
        cfg = conflict_cfg or {}
        self.tolerances = cfg.get("tolerances", {})
        self.field_type_map = cfg.get("field_type_map", {})

    def field_type(self, target_path: str) -> str:
        for pattern, ftype in self.field_type_map.items():
            if fnmatch.fnmatch(target_path, pattern):
                return ftype
        return "default"

    def _tol(self, ftype: str) -> dict:
        return self.tolerances.get(ftype, self.tolerances.get("default", {"method": "exact"}))

    # --- agreement test between two computed values --------------------------
    def divergence(self, a, b, ftype):
        """Return (divergence_value, unit). Larger = more different.
        Exact types return 0 if equal else inf."""
        tol = self._tol(ftype)
        method = tol.get("method", "exact")
        if a is None or b is None:
            return float("inf"), ""
        if method == "exact":
            return (0.0 if a == b else float("inf")), ""
        if method == "ground_distance_m":
            # a, b are integer 1/10^7 degrees (lat or long). Approx metres.
            # 1e-7 deg latitude ≈ 0.0111 m. Good enough for a tolerance test.
            try:
                return abs(a - b) * 1.11e-2, "m"
            except TypeError:
                return float("inf"), "m"
        if method == "angular_deg":
            try:
                d = abs(float(a) - float(b)) % 360
                return (min(d, 360 - d)), "deg"
            except (TypeError, ValueError):
                return float("inf"), "deg"
        return (0.0 if a == b else float("inf")), ""

    def agrees(self, a, b, ftype) -> bool:
        tol = self._tol(ftype)
        div, _ = self.divergence(a, b, ftype)
        return div <= tol.get("tolerance", 0)

    # --- main: build the conflict variable for one field --------------------
    def build(self, target_path, chosen_value, chosen_priority,
              candidate_values: list, values_pending: bool) -> dict:
        """candidate_values: list of (priority_label, value) for ALL hits."""
        ftype = self.field_type(target_path)
        tol = self._tol(ftype)
        spread = sorted({p for p, _ in candidate_values})
        out = {
            "candidate_count": len(candidate_values),
            "priority_used": chosen_priority,
            "priority_spread": spread,
            "field_type": ftype,
            "tolerance_applied": tol.get("tolerance"),
            "pending": values_pending,
        }
        if values_pending or chosen_value is None:
            # values not computable yet (transforms pending) — count/priority only
            out.update({"agreement_count": None, "disagreement_count": None,
                        "max_divergence": None, "divergence_unit": None})
            return out

        agree, disagree, max_div, unit = 0, 0, 0.0, ""
        for _, v in candidate_values:
            div, u = self.divergence(v, chosen_value, ftype)
            if u:
                unit = u
            if self.agrees(v, chosen_value, ftype):
                agree += 1
            else:
                disagree += 1
                if div != float("inf"):
                    max_div = max(max_div, div)
        out.update({
            "agreement_count": agree,
            "disagreement_count": disagree,
            "max_divergence": round(max_div, 3) if unit else (0 if disagree == 0 else None),
            "divergence_unit": unit or None,
        })
        return out


# =============================================================================
# Engine core
# =============================================================================
class MatchingEngine:
    """Orchestrates rule processing. Site-agnostic. Does not contain any
    site-specific values — those come from facts and site_config at run time."""

    def __init__(self, rules: dict, transforms_module=None,
                 confidence_policy: ConfidencePolicy = None,
                 source_selector: SourceSelector = None,
                 pipelines: dict = None):
        self.rules = rules
        self.conf = confidence_policy or ConfidencePolicy()
        self.selector = source_selector or SourceSelector()
        self.transforms = TransformRunner(transforms_module)
        # transform pipelines live in a SEPARATE file (transform_pipelines.yaml),
        # keyed by (target glob, fact_name glob) → ordered transform names.
        self.pipelines = (pipelines or {}).get("pipelines", []) if pipelines else []
        # merge rule-file config defaults (overridden by site_config at run())
        self.global_config = dict(rules.get("config", {}))
        # priority label → rank (P1<P2<P3<F). Data-driven & swappable: change in
        # the YAML's priority_ranks, or override here, to retune priority globally.
        # priority ranks: top-level, else scoring.source_priority_ranks, else default
        sc = rules.get("scoring", {})
        self.scoring = sc
        self.weights = sc.get("weights", {
            "extract_confidence": 0.15, "conflict_agreement": 0.35,
            "source_priority": 0.5})
        self.confidence_levels = sc.get("confidence_levels",
                                        {"low": 0.3, "medium": 0.6, "high": 0.9})
        self.source_priority_scores = sc.get("source_priority_scores",
                                             {"P1": 1.0, "P2": 0.75, "P3": 0.5, "F": 0.25})
        self.priority_ranks = dict(rules.get(
            "priority_ranks",
            sc.get("source_priority_ranks", {"P1": 1, "P2": 2, "P3": 3, "F": 9})))
        # v3 selected_statuses: when present, output uses v3 status vocabulary
        self.selected_statuses = sc.get("selected_statuses", {})
        self.conflicts = ConflictDetector(rules.get("conflict_detection", {}))
        # group logic: fact_group -> logical-group name (alternatives collapse).
        gl = rules.get("group_logic", {})
        self.group_policy = gl.get("policy", "all_required")
        self._fg_to_logical = {}
        for logical, members in (gl.get("alternative_sets") or {}).items():
            for m in members:
                self._fg_to_logical[m] = logical

    # ---- input validation -------------------------------------------------
    def _validate_inputs(self, facts: list, site_config: dict) -> list:
        """Fail fast on malformed input. Hard errors (wrong container types)
        raise ValueError; soft issues (unknown fact_name, bad confidence, missing
        instance keys) are collected as warnings so the run still proceeds.
        Returns a list of warning dicts."""
        warns = []
        # --- containers ---
        if not isinstance(facts, list):
            raise ValueError(f"facts must be a list, got {type(facts).__name__}")
        if not isinstance(site_config, dict):
            raise ValueError(f"site_config must be a dict, got {type(site_config).__name__}")

        # --- known fact names from the rules (for typo detection) ---
        known = set()
        for fld in self.rules.get("fields", []):
            for s in fld.get("sources", []):
                fn = s.get("fact_name") or s.get("fact_type")
                if fn:
                    known.add(fn)
        valid_conf = {"high", "medium", "low"}
        seen_ids = set()

        # --- per-fact checks ---
        for i, f in enumerate(facts):
            d = f if isinstance(f, dict) else getattr(f, "__dict__", {})
            fid = d.get("fact_id", f"#{i}")
            if "fact_name" not in d and "fact_type" not in d:
                warns.append({"code": "fact_missing_name", "severity": "high",
                              "fact": fid, "message": "fact has no fact_name"})
                continue
            fname = d.get("fact_name") or d.get("fact_type")
            if fid in seen_ids:
                warns.append({"code": "duplicate_fact_id", "severity": "medium",
                              "fact": fid, "message": "duplicate fact_id"})
            seen_ids.add(fid)
            if known and fname not in known:
                warns.append({"code": "unknown_fact_name", "severity": "medium",
                              "fact": fid,
                              "message": f"fact_name '{fname}' not in any rule "
                                         f"(typo? or dictionary out of date)"})
            conf = d.get("confidence", "medium")
            if conf not in valid_conf:
                warns.append({"code": "bad_confidence", "severity": "low",
                              "fact": fid,
                              "message": f"confidence '{conf}' not in {sorted(valid_conf)}"})
            if "payload" not in d:
                warns.append({"code": "fact_missing_payload", "severity": "medium",
                              "fact": fid, "message": "fact has no payload"})

        # --- site_config sanity ---
        for key in ("station_id", "region_code"):
            if key in site_config and not isinstance(site_config[key], (int, str)):
                warns.append({"code": "bad_config_type", "severity": "medium",
                              "message": f"site_config.{key} should be int/str"})
        po = site_config.get("priority_overrides")
        if po is not None and not isinstance(po, list):
            raise ValueError("site_config.priority_overrides must be a list")

        return warns

    # ---- public API -------------------------------------------------------
    def run(self, facts: list, site_config: dict) -> dict:
        input_warnings = self._validate_inputs(facts, site_config)
        facts = [Fact.from_dict(f) if isinstance(f, dict) else f for f in facts]
        facts = [Fact.from_dict(f) if isinstance(f, dict) else f for f in facts]

        # --- CRS declaration -> coordinate_reference evidence -----------------
        # If the site_config declares a coordinate reference system
        # (crs_source), inject a synthetic coordinate-reference fact so the
        # refPoint's required `coordinate_reference` group is satisfied by an
        # explicit, human-confirmed declaration rather than left unfilled.
        # This is deliberately gated on an EXPLICIT declaration: no declaration
        # -> no fact -> refPoint still held for review (no silent guessing).
        crs_decl = site_config.get("crs_source")
        if crs_decl:
            facts.append(Fact.from_dict({
                "fact_id": "crs_decl_from_site_config",
                "fact_name": "coordinate_reference_system_evidence_from_cad",
                "payload": {
                    "value": crs_decl,
                    "crs": crs_decl,
                    "_source": "site_config.crs_source (operator-declared)",
                },
                "confidence": "high",
            }))

        resolver = InstanceResolver(facts)

        # merged config: rule-file defaults < site_config
        cfg = dict(self.global_config)
        cfg.update({k: v for k, v in site_config.items()
                    if k not in ("manual", "priority_overrides", "site",
                                 "parser_hints", "expected", "conflict_area")})
        priority_overrides = site_config.get("priority_overrides") or []
        manual = site_config.get("manual", {}) or {}

        ctx = {
            "config": cfg,
            "manual": manual,
            "site_config": site_config,
            "resolved": {},  # filled progressively (e.g. refPoint for later nodes)
        }

        records: list[EvidenceRecord] = []
        manual_review: list[dict] = []
        validation_log: list[dict] = []

        # cross-lane prepass: cluster lanes into approaches + pair ingress/egress
        # by geometry (results land in ctx['resolved'] for per-lane transforms).
        self._analyze_lanes(facts, ctx)
        # surface OSTN15 grid status (B1): never let coordinate accuracy degrade
        # silently — record a prominent warning if the high-accuracy grid is absent.
        crs_warning = self._check_crs_grid()

        for rule in self.rules.get("fields", self.rules.get("mandatory_fields", [])):
            target = rule.get("target", "")
            # expand collection templates into concrete instances
            if "[]" in target:
                instances = resolver.expand(target)
            else:
                instances = [(target, {})]

            for concrete_path, scope in instances:
                rec = self._process_one(rule, concrete_path, scope, facts, ctx,
                                        priority_overrides)
                records.append(rec)
                # stash a resolved refPoint so downstream node transforms
                # (relative_to_refpoint) can offset against it
                if rec.value is not None and rec.status == "ok":
                    if concrete_path.endswith(".refPoint.lat"):
                        ctx["resolved"].setdefault("refPoint", {})["lat"] = rec.value
                    elif concrete_path.endswith(".refPoint.long"):
                        ctx["resolved"].setdefault("refPoint", {})["lon"] = rec.value
                if rec.status == "manual_review":
                    manual_review.append({"target": rec.target_path,
                                          "reason": rec.notes})
                validation_log.append({
                    "target": rec.target_path,
                    "status": rec.status,
                    "rule_applied": rec.rule_applied,
                    "chosen": rec.source_facts,
                    "confidence": rec.confidence,
                    "corroborating": rec.corroborating,
                })

        forbidden = self._collect_forbidden()
        summary = self._summarise(records)     # count before relabelling

        if self.selected_statuses:        # v3: relabel to selected_statuses vocab
            for rec in records:
                rec.status = self._v3_status(rec)

        return {
            "mapped_evidence": [r.to_dict() for r in records],
            "manual_review_items": manual_review,
            "validation_report": validation_log,
            "forbidden_elements": forbidden,
            "warnings": (([crs_warning] if crs_warning else []) + input_warnings),
            "summary": summary,
        }

    def _v3_status(self, rec):
        """Map internal status (ok/manual_review/pending_transform/forbidden) to
        the v3 selected_statuses vocabulary."""
        s = rec.status
        if s == "ok":
            if rec.value is None:
                return "unresolved"
            if rec.conflict.get("disagreement_count", 0) > 0:
                return "matched_with_conflict"
            return "matched"
        if s == "manual_review":
            return "manual_review_required"
        if s == "pending_transform":
            return "pending_transform"
        return s            # forbidden, or any other, passes through

    # ---- cross-lane prepass (B2: approach assignment is inherently cross-lane) -
    def _analyze_lanes(self, facts, ctx):
        """Cluster lane centrelines into approaches and pair ingress↔egress by
        geometry, ONCE, before per-field processing. Per-lane results go into
        ctx['resolved'] so the ingress/egress/connectingLane transforms can read
        them. Requires lane geometry facts shaped per payload_contract.md
        (payload carries lane_ref + a polyline). Silently no-ops if absent."""
        mod = self.transforms.mod
        if mod is None:
            return
        cluster = getattr(mod, "cluster_by_direction", None)
        direction = getattr(mod, "direction_relative_to_refpoint", None)
        polyc = getattr(mod, "polyline_centroid", None)
        pair = getattr(mod, "pair_ingress_egress_by_geometry", None)
        if not (cluster and direction and polyc):
            return

        # gather lane polylines keyed by lane_ref (BNG coordinates)
        lanes = {}   # lane_ref -> polyline (list of [E,N])
        for f in facts:
            if not isinstance(f.payload, dict):
                continue
            if not (fnmatch.fnmatch(f.fact_name, "lane_centreline*") or
                    fnmatch.fnmatch(f.fact_name, "lane_direction*") or
                    fnmatch.fnmatch(f.fact_name, "lane_geometry*")):
                continue
            lr = f.payload.get("lane_ref")
            poly = (f.payload.get("polyline") or f.payload.get("vertices") or
                    f.payload.get("points"))
            if lr and poly and lr not in lanes:
                lanes[lr] = poly
        if not lanes:
            return

        lane_refs = list(lanes)
        polylines = [lanes[r] for r in lane_refs]
        try:
            # BNG reference centroid from all lane points
            all_pts = [p for poly in polylines for p in poly]
            ref = polyc(all_pts)
            clusters = cluster(polylines, ref)
            appr = {}
            for r, poly, cid in zip(lane_refs, polylines, clusters):
                d = direction(poly, ref)
                appr[r] = {"id": cid, "dir": d}
            ctx["resolved"]["approach"] = appr
            # ingress/egress geometry pairing → connectingLane.lane
            if pair:
                ing = [{"lane_id": r, "nodes": lanes[r]}
                       for r in lane_refs if appr[r]["dir"] == "ingress"]
                egr = [{"lane_id": r, "nodes": lanes[r]}
                       for r in lane_refs if appr[r]["dir"] == "egress"]
                if ing and egr:
                    matched = pair(ing, egr)
                    ctx["resolved"]["lane_pairs"] = {
                        m["source_lane_id"]: m for m in matched}
        except Exception as e:  # prepass must never crash the run
            ctx["resolved"]["approach_error"] = f"{type(e).__name__}: {e}"

    def _check_crs_grid(self):
        """Return a warning dict if the OSTN15 grid is unavailable (B1)."""
        mod = self.transforms.mod
        checker = getattr(mod, "ostn15_grid_available", None)
        try:
            if checker and not checker():
                return {
                    "code": "ostn15_grid_missing",
                    "severity": "high",
                    "message": ("OSTN15 grid (uk_os_OSTN15_NTv2_OSGBtoETRS.tif) "
                                "not installed — BNG→WGS84 falls back to a generic "
                                "~metre-accuracy transform, NOT sub-metre OSTN15. "
                                "Install: `pyproj sync --file "
                                "uk_os_OSTN15_NTv2_OSGBtoETRS.tif` or place the .tif "
                                "in PROJ_DATA. Coordinates are computed but accuracy "
                                "is degraded until installed."),
                }
        except Exception:
            pass
        return None


    # ---- per-field processing --------------------------------------------
    def _process_one(self, rule, path, scope, facts, ctx, priority_overrides):
        rec = EvidenceRecord(target_path=path, rule_applied=rule.get("target", ""),
                             population_mode=rule.get("population_mode", ""))
        mode = rule.get("population_mode")

        # ---- non-source population modes ----
        if mode == "constant":
            rec.value, rec.confidence = rule.get("value"), "high"
            return rec

        if mode == "client_configured":
            key = rule.get("config_key")
            val = ctx["config"].get(key) if key else None
            if val is None and rule.get("fallback_config_key"):
                val = ctx["config"].get(rule["fallback_config_key"])
            rec.value = val
            rec.confidence = "high"
            rec.source_facts = [f"site_config.{key}"] if key else []
            # client_configured can still fall back to source facts if no config
            if rec.value is None and rule.get("sources"):
                return self._process_sources(rule, rec, scope, facts, ctx,
                                              priority_overrides)
            return self._finalise_mandatory(rec, rule)

        if mode == "project_managed":
            rec.value = rule.get("initial", 1)
            rec.confidence = "high"
            rec.notes = "project-managed counter"
            return rec

        if mode == "system_generated":
            start = rule.get("auto_start", 1)
            idx = self._leaf_index(path)
            rec.value = start + (idx if idx is not None else 0)
            rec.confidence = "high"
            return rec

        if mode == "must_exist":
            return self._process_must_exist(rule, rec, scope, facts)

        if mode == "default":
            # use default_value; but if override facts are present, prefer them
            if rule.get("overrides"):
                r2 = dict(rule)
                r2["sources"] = rule["overrides"]
                rec2 = self._process_sources(r2, rec, scope, facts, ctx,
                                             priority_overrides)
                if rec2.value is not None and rec2.status == "ok":
                    return rec2
            rec.value = rule.get("default_value")
            rec.confidence = "low"
            rec.notes = "default value" + (" (optional)" if rule.get("optional") else "")
            return rec

        # ---- source-matching population modes ----
        # directly_extracted / geometry_derived / evidence_fused
        if rule.get("sources"):
            return self._process_sources(rule, rec, scope, facts, ctx,
                                         priority_overrides)

        rec.status = "pending_transform"
        rec.notes = f"population_mode '{mode}' has no machine-usable sources yet"
        return self._finalise_mandatory(rec, rule)

    # ---- sources matching (group-aware: within-group OR, across-group AND) --
    def _logical_name(self, fact_group: str) -> str:
        """Map a fact_group to its logical group (alternatives collapse to one)."""
        return self._fg_to_logical.get(fact_group, fact_group)

    def _pipeline_for(self, target_path: str, fact_name: str) -> list:
        """Look up the transform chain for a (target, fact) from the separate
        transform_pipelines.yaml. First match wins; '*' globs allowed."""
        for p in self.pipelines:
            t_ok = fnmatch.fnmatch(target_path, p.get("target", "*"))
            f_ok = fnmatch.fnmatch(fact_name or "", p.get("fact_name", "*"))
            if t_ok and f_ok:
                return p.get("transform", [])
        return []

    def _transform_for(self, source, target_path, fact_name):
        """Transform chain for a source: prefer the inline `transform` on the
        source (v3 rules carry it there), else the separate pipeline file."""
        t = source.get("transform")
        if t:
            return t
        return self._pipeline_for(target_path, fact_name)

    # ---- final-score scoring (v3 'scoring' section) -----------------------
    def _conf_score(self, confidence) -> float:
        """Confidence → 0..1. Accepts a level ('high'/'medium'/'low') or a float."""
        if isinstance(confidence, (int, float)):
            return max(0.0, min(1.0, float(confidence)))
        return self.confidence_levels.get(confidence, 0.6)

    def _safe_value(self, source, rule, fact, ctx):
        """Run a candidate's transform chain, returning value or None (pending)."""
        try:
            chain = self._transform_for(source, rule["target"],
                                        source.get("fact_name") or source.get("fact_type"))
            val, _ = self.transforms.run(chain, fact.payload, ctx)
            return val
        except Exception:
            return None

    def _select_by_score(self, candidates, rule, ctx, eff_priority):
        """Final-score selection (replaces priority-only within a group):
            final_score = w_conf*confidence + w_agree*agreement + w_prio*priority
        Returns (winner, corroborating, rejected) in SourceSelector's shape, so
        the surrounding AND-grouping / conflict code is unchanged."""
        if not candidates:
            return (None, [], [])
        ftype = self.conflicts.field_type(rule["target"])
        enriched = []
        for (src, fact) in candidates:
            enriched.append({"src": src, "fact": fact,
                             "value": self._safe_value(src, rule, fact, ctx)})
        # conflict_agreement_score: agreeing candidates / candidates (by value)
        computable = [c for c in enriched if c["value"] is not None]
        for c in enriched:
            if c["value"] is None or not computable:
                c["agreement"] = 1.0   # neutral when values not computable yet
            else:
                agree = sum(1 for o in computable
                            if self.conflicts.agrees(o["value"], c["value"], ftype))
                c["agreement"] = agree / len(computable)
        w = self.weights
        for c in enriched:
            conf = self._conf_score(c["fact"].confidence)
            prio = self.source_priority_scores.get(c["src"].get("priority", "F"), 0.25)
            c["final"] = (w.get("extract_confidence", 0.15) * conf
                          + w.get("conflict_agreement", 0.35) * c["agreement"]
                          + w.get("source_priority", 0.5) * prio)
        # sort by final desc; tie-breakers: priority rank, confidence, source order
        order = sorted(enriched,
                       key=lambda c: (-c["final"], eff_priority(c["src"]),
                                      -self._conf_score(c["fact"].confidence)))
        winner = (order[0]["src"], order[0]["fact"])
        corro = [(c["src"], c["fact"]) for c in order[1:]]
        return (winner, corro, [])

    def _process_sources(self, rule, rec, scope, facts, ctx, priority_overrides):
        def eff_priority(source):
            return self._effective_priority(rule, source, priority_overrides)

        # 1. collect candidates keyed by LOGICAL group, preserving declared order
        declared = []                 # logical groups this field declares
        by_logical = {}               # logical group -> [(source, fact)]
        for source in rule["sources"]:
            lname = self._logical_name(source.get("fact_group", ""))
            if lname not in declared:
                declared.append(lname)
            name = source.get("fact_name") or source.get("fact_type")
            for f in self._facts_of_name(facts, name, scope, source):
                by_logical.setdefault(lname, []).append((source, f))

        # 2. WITHIN each logical group: select the best source.
        #    v3 'scoring' present → final-score selection; else priority-only.
        group_sel = {}                # lname -> (winner|None, corro, rejected)
        for lname in declared:
            cands = by_logical.get(lname, [])
            if not cands:
                group_sel[lname] = (None, [], [])
            elif self.scoring:
                group_sel[lname] = self._select_by_score(cands, rule, ctx, eff_priority)
            else:
                group_sel[lname] = self.selector.select(cands, rule, self.conf, eff_priority)

        # 3. ACROSS logical groups: AND — every declared group must have a winner
        winners = {g: group_sel[g][0] for g in declared if group_sel[g][0]}
        missing = [g for g in declared if group_sel[g][0] is None]

        if not winners:
            rec.value = None
            rec.notes = "no source present for any required group"
            rec.conflict = {
                "candidate_count": 0, "agreement_count": None,
                "disagreement_count": None, "priority_used": "",
                "priority_spread": [], "max_divergence": None,
                "divergence_unit": None, "tolerance_applied": None,
                "field_type": self.conflicts.field_type(rec.target_path),
                "pending": True, "groups": {}, "primary_group": None,
                "all_required_groups_satisfied": False,
                "missing_groups": missing, "total_candidate_count": 0,
            }
            return self._finalise_mandatory(rec, rule)

        # primary group = winner with the best effective priority
        primary_g = min(winners, key=lambda g: eff_priority(winners[g][0]))
        primary_source, primary_fact = winners[primary_g]

        # 4. value — expose ALL group winners to the transform (AND inputs),
        #    then run the primary group's pipeline.
        ctx = dict(ctx)
        ctx["group_inputs"] = {g: winners[g][1].payload for g in winners}
        ctx["scope"] = scope
        primary_fact_name = primary_source.get("fact_name") or primary_source.get("fact_type")
        transforms = self._transform_for(primary_source, rec.target_path, primary_fact_name)
        values_pending = False
        if not transforms:
            values_pending = True
            rec.status = "pending_transform"
            rec.notes = "no transform pipeline defined for primary group yet"
        else:
            try:
                value, ran = self.transforms.run(transforms, primary_fact.payload, ctx)
                rec.value, rec.transforms_run = value, ran
            except (TransformNotImplemented, NotImplementedError) as e:
                values_pending = True
                rec.status = "pending_transform"
                rec.notes = f"transform not implemented: {e}"
                rec.transforms_run = transforms
            except Exception as e:
                # shape/contract mismatch or transform error → degrade, don't crash
                values_pending = True
                rec.status = "pending_transform"
                rec.notes = (f"transform error ({type(e).__name__}: {e}) — "
                             f"likely payload-shape contract mismatch")
                rec.transforms_run = transforms

        rec.priority_used = primary_source.get("priority", "")
        rec.source_facts = [winners[g][1].fact_id for g in winners]   # all contribute
        rec.corroborating = [f.fact_id for g in declared
                             for (_, f) in group_sel[g][1]]

        # AND not satisfied → manual_review (a required group is missing)
        if missing:
            rec.status = "manual_review"
            rec.notes = f"required fact_group(s) not satisfied: {sorted(missing)}"

        # 5. conflict — per logical group + a top-level rollup
        rec.conflict = self._build_grouped_conflict(
            rec.target_path, declared, group_sel, primary_g, values_pending,
            ctx, missing)
        return rec

    def _build_grouped_conflict(self, target, declared, group_sel, primary_g,
                                pending, ctx, missing):
        groups_conf, total_cand, total_disagree = {}, 0, 0
        for g in declared:
            winner, corro, _ = group_sel[g]
            if winner is None:
                groups_conf[g] = {"satisfied": False, "candidate_count": 0}
                continue
            all_hits = [winner] + corro
            # this group's own chosen value (within-group comparison)
            gwin_val = None
            cand_vals = []
            for (src, fct) in all_hits:
                cv = None
                if not pending:
                    try:
                        fn = src.get("fact_name") or src.get("fact_type")
                        cv, _ = self.transforms.run(
                            self._transform_for(src, target, fn), fct.payload, ctx)
                    except Exception:
                        cv = None
                cand_vals.append((src.get("priority", "F"), cv))
            if not pending and cand_vals:
                gwin_val = cand_vals[0][1]
            gc = self.conflicts.build(target, gwin_val,
                                      winner[0].get("priority", ""),
                                      cand_vals, pending)
            gc["satisfied"] = True
            groups_conf[g] = gc
            total_cand += gc.get("candidate_count", 0)
            if gc.get("disagreement_count"):
                total_disagree += gc["disagreement_count"]

        # Flat top-level rollup: promote the PRIMARY group's full conflict so a
        # confidence function written against the flat spec finds every field at
        # the top level (candidate_count, agreement_count, disagreement_count,
        # priority_used, priority_spread, max_divergence, divergence_unit,
        # tolerance_applied, field_type, pending). The per-group breakdown stays
        # under 'groups', and the AND result under missing_groups / *_satisfied.
        primary = dict(groups_conf.get(primary_g, {}))
        primary.pop("satisfied", None)
        # spread = union across all groups (so it reflects every hitting source)
        all_spread = sorted({p for g in declared
                             for p in groups_conf.get(g, {}).get("priority_spread", [])})
        flat = {
            # --- flat fields the confidence function consumes directly ---
            "candidate_count": primary.get("candidate_count", 0),
            "agreement_count": primary.get("agreement_count"),
            "disagreement_count": primary.get("disagreement_count"),
            "priority_used": primary.get("priority_used",
                                         group_sel[primary_g][0][0].get("priority", "")),
            "priority_spread": all_spread or primary.get("priority_spread", []),
            "max_divergence": primary.get("max_divergence"),
            "divergence_unit": primary.get("divergence_unit"),
            "tolerance_applied": primary.get("tolerance_applied"),
            "field_type": primary.get("field_type"),
            "pending": pending,
            # --- grouping detail (for richer confidence logic) ---
            "groups": groups_conf,
            "primary_group": primary_g,
            "all_required_groups_satisfied": not missing,
            "missing_groups": sorted(missing),
            "total_candidate_count": total_cand,   # across all groups (AND inputs)
        }
        return flat

    def _process_default(self, rule, rec, scope, facts, ctx):
        rec.value = rule.get("default_value")
        rec.confidence = "medium"
        rec.notes = "default value"
        # apply overrides if any matching fact exists
        for ov in rule.get("overrides", []) or []:
            ft = ov.get("fact_type")
            present = list(self._facts_of_type(facts, ft, scope, ov))
            if present:
                rec.notes = f"default overridden by {ft}"
                rec.source_facts = [present[0].fact_id]
                # actual bit-setting handled by a transform in Task 2
        return rec

    def _process_must_exist(self, rule, rec, scope, facts):
        # the container must have ≥1 instance. We approximate by checking the
        # presence of facts that would populate it.
        rec.value = None
        rec.notes = rule.get("note", "container must exist")
        # if any fact is scoped to this instance, treat as satisfied
        has_any = any(self._fact_in_scope(f, scope) for f in facts)
        rec.status = "ok" if has_any else "manual_review"
        if rec.status == "manual_review":
            rec.notes = "required container is empty/absent — " + rec.notes
        return rec

    # ---- helpers ----------------------------------------------------------
    def _facts_of_name(self, facts, fact_name, scope, source):
        """Yield facts matching the dictionary Fact Name (glob ok) and scope."""
        if not fact_name:
            return
        for f in facts:
            if not f.matches_name(fact_name):
                continue
            if not self._fact_in_scope(f, scope):
                continue
            yield f

    @staticmethod
    def _fact_in_scope(fact, scope):
        for level, inst_id in scope.items():
            ref = fact.payload.get(f"{level}_ref") if isinstance(fact.payload, dict) else None
            if ref is not None and ref != inst_id:
                return False
        return True

    def _effective_priority(self, rule, source, priority_overrides):
        """Return a numeric rank for a source. Site-level overrides win over the
        rule-file priority label; labels (P1..F) map to ranks via priority_ranks.
        This is the priority logic the user will tune — kept isolated here and
        data-driven via priority_ranks in the YAML."""
        label = source.get("priority", "F")
        for ov in priority_overrides:
            if ov.get("target") == rule.get("target") and \
               ov.get("fact_name") == source.get("fact_name"):
                label = ov.get("priority", label)
        # allow overrides to give a raw int, else map label→rank
        if isinstance(label, int):
            return label
        return self.priority_ranks.get(label, 99)

    def _finalise_mandatory(self, rec, rule):
        """If a c_roads_mandatory field has no value, escalate to manual_review.
        ASN.1-mandatory fields are left to the encoder (informational only)."""
        empty = rec.value is None or rec.value == [] or rec.value == ""
        if empty and rule.get("c_roads_mandatory") and rec.status == "ok":
            rec.status = "manual_review"
            rec.notes = (rec.notes + " | " if rec.notes else "") + \
                        "C-Roads mandatory but not provided"
        return rec

    @staticmethod
    def _leaf_index(path):
        """Index of the last [] in a concrete path, for auto_number."""
        import re
        idxs = re.findall(r"\[(\d+)\]", path)
        return int(idxs[-1]) if idxs else None

    def _collect_forbidden(self):
        out = []
        for fb in self.rules.get("forbidden", []) or []:
            out.append({"target": fb.get("target"),
                        "reason": fb.get("reason", "")})
        return out

    @staticmethod
    def _summarise(records):
        from collections import Counter
        c = Counter(r.status for r in records)
        return {"total_fields": len(records), **dict(c)}


# =============================================================================
# CLI
# =============================================================================
def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    p = argparse.ArgumentParser(description="Generic MAPEM matching engine (tool).")
    p.add_argument("--rules", required=True, help="matching_rules.yaml")
    p.add_argument("--facts", required=True, help="extracted_facts.<site>.json")
    p.add_argument("--config", required=True, help="site_config_<site>.yaml")
    p.add_argument("--out", default="mapped_evidence.partial.json")
    p.add_argument("--transforms", default=None,
                   help="python module path for transforms (default: ./transforms.py)")
    p.add_argument("--pipelines", default=None,
                   help="transform_pipelines.yaml (default: alongside rules)")
    args = p.parse_args(argv)

    rules = _load_yaml(args.rules)
    facts_doc = _load_json(args.facts)
    facts = facts_doc.get("facts", facts_doc) if isinstance(facts_doc, dict) else facts_doc
    site_config = _load_yaml(args.config)

    # transform pipelines (separate file). Default: transform_pipelines.yaml next to rules.
    import os
    pipelines = {}
    pl_path = args.pipelines
    if pl_path is None:
        cand = os.path.join(os.path.dirname(os.path.abspath(args.rules)) or ".",
                            "transform_pipelines.yaml")
        pl_path = cand if os.path.exists(cand) else None
    if pl_path and os.path.exists(pl_path):
        pipelines = _load_yaml(pl_path)

    # try to import transforms module (optional; missing → pending_transform)
    transforms_mod = None
    try:
        import importlib
        if args.transforms:
            transforms_mod = importlib.import_module(args.transforms)
        else:
            sys.path.insert(0, os.path.dirname(os.path.abspath(args.rules)) or ".")
            try:
                transforms_mod = importlib.import_module("transforms")
            except ImportError:
                transforms_mod = None
    except Exception as e:  # pragma: no cover
        print(f"[warn] transforms not loaded ({e}); fields needing transforms "
              f"will be marked pending_transform", file=sys.stderr)

    engine = MatchingEngine(rules, transforms_mod, pipelines=pipelines)
    result = engine.run(facts, site_config)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    s = result["summary"]
    print(f"[ok] wrote {args.out}")
    print(f"     fields={s.get('total_fields',0)}  "
          f"ok={s.get('ok',0)}  manual_review={s.get('manual_review',0)}  "
          f"pending_transform={s.get('pending_transform',0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
