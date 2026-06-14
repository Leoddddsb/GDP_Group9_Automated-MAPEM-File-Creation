"""DXF extraction and DWG conversion through ODA File Converter."""

from __future__ import annotations

import os
import json
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from mapemgen.ingestion.fact_records import make_fact
from mapemgen.ingestion.movement_tables import _movement_payload


DEFAULT_CAD_SYMBOL_RULES = {
    "block_rules": [
        {"match": "exact", "pattern": "tactpblk", "semantic_type": "tactile_paving", "fact_name": "cad_pedestrian_facility_candidate"},
        {"match": "regex", "pattern": r"(?:^|[$_\s-])(?:tactpblk|tactknob|tactpave)(?:$|[^a-z0-9])", "semantic_type": "tactile_paving", "fact_name": "cad_pedestrian_facility_candidate"},
        {"match": "exact", "pattern": "pole", "semantic_type": "pole", "fact_name": "cad_pole_candidate"},
        {"match": "regex", "pattern": r"(?:^|[$_\s-])(?:pole|wbpole|poleno|stubpole|crpole|polesock)(?:$|[^a-z0-9])", "semantic_type": "pole", "fact_name": "cad_pole_candidate"},
        {
            "match": "exact",
            "pattern": "HD003P",
            "semantic_type": "signal_arrow",
            "fact_name": "cad_arrow_block_candidate",
            "payload": {"arrow_direction_candidate": "right", "requires_context_match": True},
        },
        {
            "match": "regex",
            "pattern": r"(?:^|[$_\s-])HD003P(?:$|[^a-z0-9])",
            "semantic_type": "signal_arrow",
            "fact_name": "cad_arrow_block_candidate",
            "payload": {"arrow_direction_candidate": "right", "requires_context_match": True},
        },
        {
            "match": "exact",
            "pattern": "HD004P",
            "semantic_type": "signal_arrow",
            "fact_name": "cad_arrow_block_candidate",
            "payload": {"arrow_direction_candidate": "left", "requires_context_match": True},
        },
        {
            "match": "regex",
            "pattern": r"(?:^|[$_\s-])HD004P(?:$|[^a-z0-9])",
            "semantic_type": "signal_arrow",
            "fact_name": "cad_arrow_block_candidate",
            "payload": {"arrow_direction_candidate": "left", "requires_context_match": True},
        },
        {"match": "prefix", "pattern": "HD", "semantic_type": "signal_head", "fact_name": "cad_signal_head_candidate"},
        {"match": "regex", "pattern": r"(?:^|[$_\s-])(?:HD[0-9]{3}[A-Z]*|Signal-Symbol-[0-9]{3}[A-Z]*)(?:$|[^a-z0-9])", "semantic_type": "signal_head", "fact_name": "cad_signal_head_candidate"},
        {
            "match": "regex",
            "pattern": r"(?:right|1038r|arrow-r|r-arrow)",
            "semantic_type": "directional_arrow",
            "fact_name": "cad_arrow_block_candidate",
            "payload": {"arrow_direction_candidate": "right", "requires_context_match": True},
        },
        {
            "match": "regex",
            "pattern": r"(?:left|1038l|arrow-l|l-arrow)",
            "semantic_type": "directional_arrow",
            "fact_name": "cad_arrow_block_candidate",
            "payload": {"arrow_direction_candidate": "left", "requires_context_match": True},
        },
        {"match": "contains", "pattern": "arrow", "semantic_type": "arrow", "fact_name": "cad_arrow_block_candidate"},
        {"match": "contains", "pattern": "left", "semantic_type": "arrow", "fact_name": "cad_arrow_block_candidate"},
        {"match": "contains", "pattern": "right", "semantic_type": "arrow", "fact_name": "cad_arrow_block_candidate"},
    ],
    "text_rules": [
        {
            "match": "regex",
            "pattern": r"\b(?:LEFT|RIGHT|AHEAD|STRAIGHT|INBOUND|OUTBOUND|NB|SB|EB|WB)\b",
            "semantic_type": "movement_label",
            "fact_name": "cad_movement_label_candidate",
            "derive_movement": True,
        },
        {
            "match": "regex",
            "pattern": r"\bKEEP\s+CLEAR\b",
            "semantic_type": "lane_use",
            "fact_name": "cad_lane_use_label_candidate",
            "label": "keep_clear",
        },
    ],
}

DEFAULT_CAD_LAYER_RULES = {
    "layer_rules": [
        {"match": "regex", "pattern": r"(?:stop\s*line|stoplines|sct_loops|slc)", "fact_name": "stop_line_from_cad", "semantic_type": "stop_line"},
        {"match": "regex", "pattern": r"(?:road\s*mark|roadmarking|pro-markings|rd\s*mks|1038|studs|zig\s*zags|lines-studs)", "fact_name": "road_marking_candidate_from_cad", "semantic_type": "road_marking"},
        {"match": "regex", "pattern": r"(?:tact|toucan|xing|crossing)", "fact_name": "crossing_candidate_from_cad", "semantic_type": "crossing_or_tactile"},
        {"match": "regex", "pattern": r"(?:signal|utc_signals|kts_signals|traffic\s*signal)", "fact_name": "signal_geometry_candidate_from_cad", "semantic_type": "signal_geometry"},
        {"match": "regex", "pattern": r"(?:loop|mova\s*loop|traffic\s*loops|va\s*loops)", "fact_name": "detector_loop_candidate_from_cad", "semantic_type": "detector_loop"},
        {"match": "regex", "pattern": r"(?:kerb|carriagewaykerb|road-edge|road\s*or\s*track|channel)", "fact_name": "cad_context_geometry_candidate", "semantic_type": "road_context_geometry"},
        {"match": "regex", "pattern": r"(?:^|[$_\s-])(?:os|topo|exbase|base)(?:[$_\s-]|$)", "fact_name": "cad_context_geometry_candidate", "semantic_type": "background_context"},
    ]
}

CAD_LANE_CENTRELINE_MIN_LENGTH = 20.0
CAD_LANE_CENTRELINE_LAYER_PATTERNS = (
    r"(?:^|[$_\s-])(?:kts_lines|lines|roadcentre|roadcenter|centreline|centerline|r_cl)$",
)
CAD_LANE_CENTRELINE_EXCLUDE_PATTERNS = (
    r"(?:duct|loop|signal|tact|kerb|base|exbase|topo|text|key|dim|border|build|wall|veg|water|rail|fence|slope|verge|channel|hatch|utility|service|title|frame|control|cctv|benchmark|construction|yellow|double|existing|off)",
)


def extract_dxf_facts(path: str | Path) -> list[dict]:
    try:
        import ezdxf
    except ImportError as exc:
        raise RuntimeError("DXF extraction requires the 'ezdxf' package.") from exc
    return _extract_document_facts(ezdxf.readfile(path))


def extract_dwg_facts(path: str | Path) -> list[dict]:
    try:
        import ezdxf
        from ezdxf.addons import odafc
    except ImportError as exc:
        raise RuntimeError("DWG extraction requires 'ezdxf' and ODA File Converter.") from exc
    configured_path = os.environ.get("ODAFC_PATH")
    if configured_path:
        ezdxf.options.set("odafc-addon", "win_exec_path", configured_path)
    if not odafc.is_installed():
        raise RuntimeError(
            "DWG extraction requires ODA File Converter to be installed. "
            "If it is installed outside the default location, set ODAFC_PATH "
            "to the full path of ODAFileConverter.exe."
        )
    source_path = Path(path).resolve()
    temp_root = Path(os.environ.get("MAPEMGEN_TEMP_DIR", Path.cwd() / "outputs" / "mapemgen_odafc_work")).resolve()
    temp_root.mkdir(parents=True, exist_ok=True)
    converted_dir = temp_root / f"mapemgen_odafc_{uuid.uuid4().hex}"
    converted_dir.mkdir()
    converted_path = converted_dir / source_path.with_suffix(".dxf").name
    try:
        arguments = odafc._odafc_arguments(
            source_path.name,
            in_folder=str(source_path.parent),
            out_folder=str(converted_dir),
            output_format="DXF",
            version="ACAD2018",
            audit=True,
        )
        odafc._execute_odafc(arguments)
        if not converted_path.exists():
            candidates = sorted(converted_dir.glob("*.dxf")) + sorted(converted_dir.glob("*.DXF"))
            if candidates:
                converted_path = candidates[0]
        try:
            document = ezdxf.readfile(converted_path)
        except ezdxf.DXFStructureError:
            from ezdxf import recover

            document, _auditor = recover.readfile(converted_path)
    finally:
        _cleanup_odafc_output(converted_dir)
    return _extract_document_facts(document)


def _cleanup_odafc_output(folder: Path) -> None:
    try:
        for child in folder.iterdir():
            if child.is_file():
                child.unlink(missing_ok=True)
        folder.rmdir()
    except OSError:
        pass


def _load_cad_symbol_rules() -> dict[str, Any]:
    configured_path = os.environ.get("CAD_SYMBOL_RULES_PATH")
    path = Path(configured_path) if configured_path else Path("configs") / "cad_symbol_semantics.json"
    if not path.is_file():
        return DEFAULT_CAD_SYMBOL_RULES
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_CAD_SYMBOL_RULES
    return {
        "block_rules": data.get("block_rules", DEFAULT_CAD_SYMBOL_RULES["block_rules"]),
        "text_rules": data.get("text_rules", DEFAULT_CAD_SYMBOL_RULES["text_rules"]),
    }


def _load_cad_layer_rules() -> dict[str, Any]:
    configured_path = os.environ.get("CAD_LAYER_RULES_PATH")
    path = Path(configured_path) if configured_path else Path("configs") / "cad_layer_semantics.json"
    if not path.is_file():
        return DEFAULT_CAD_LAYER_RULES
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_CAD_LAYER_RULES
    return {
        "layer_rules": data.get("layer_rules", DEFAULT_CAD_LAYER_RULES["layer_rules"]),
    }


def _extract_document_facts(document: object) -> list[dict]:
    modelspace = document.modelspace()
    entities = list(modelspace)
    semantic_rules = _load_cad_symbol_rules()
    layer_rules = _load_cad_layer_rules()
    counts = Counter(entity.dxftype() for entity in entities)
    layers = sorted({getattr(entity.dxf, "layer", "0") for entity in entities})
    facts = [_fact("cad_layer_names", layers, "modelspace", 0.95), _fact("cad_entity_counts", dict(sorted(counts.items())), "modelspace", 0.95)]
    points: list[tuple[float, float]] = []
    for index, entity in enumerate(entities, start=1):
        entity_type = entity.dxftype()
        layer = getattr(entity.dxf, "layer", "0")
        location = f"modelspace entity {index} layer {layer}"
        if entity_type == "LINE":
            geometry = [_xy(entity.dxf.start), _xy(entity.dxf.end)]
            points.extend(geometry)
            fact_name, payload, confidence = _layer_geometry_fact(layer, geometry, layer_rules)
            facts.append(_fact(fact_name, payload, location, confidence))
        elif entity_type == "LWPOLYLINE":
            geometry = [_xy(point) for point in entity.get_points()]
            points.extend(geometry)
            fact_name, payload, confidence = _layer_geometry_fact(layer, geometry, layer_rules)
            facts.append(_fact(fact_name, payload, location, max(confidence, 0.75) if confidence >= 0.7 else confidence))
        elif entity_type == "POLYLINE":
            geometry = [_xy(vertex.dxf.location) for vertex in entity.vertices]
            points.extend(geometry)
            fact_name, payload, confidence = _layer_geometry_fact(layer, geometry, layer_rules)
            facts.append(_fact(fact_name, payload, location, max(confidence, 0.75) if confidence >= 0.7 else confidence))
        elif entity_type in {"TEXT", "MTEXT"}:
            text = entity.plain_text() if hasattr(entity, "plain_text") else entity.dxf.text
            text = str(text).strip()
            if text:
                payload = _cad_text_payload(entity, text)
                facts.append(_fact("cad_text_label", payload, location, 0.8))
                facts.extend(_semantic_text_facts(text, payload, location, semantic_rules))
        elif entity_type == "INSERT":
            payload = _cad_block_payload(entity)
            facts.append(_fact("cad_block_reference", payload, location, 0.8))
            facts.extend(_semantic_block_facts(str(payload["name"]), payload, location, semantic_rules))
    if points:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        facts.append(_fact("coordinate_bounds", {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}, "modelspace geometry", 0.9))
    return facts


def _layer_geometry_fact(layer: str, geometry: list[tuple[float, float]], layer_rules: dict[str, Any]) -> tuple[str, object, float]:
    for rule in layer_rules.get("layer_rules", []):
        if not _rule_matches(layer, rule):
            continue
        fact_name = str(rule.get("fact_name") or "")
        semantic_type = str(rule.get("semantic_type") or "")
        if not fact_name:
            continue
        return fact_name, {"geometry": geometry, "layer": layer, "semantic_type": semantic_type}, 0.7
    if _is_lane_centreline_candidate(layer, geometry):
        return (
            "lane_geometry_candidate_from_cad",
            {
                "geometry": geometry,
                "layer": layer,
                "semantic_type": "lane_centreline_candidate",
                "recognition_basis": "cad_layer_geometry_heuristic",
                "requires_context_match": True,
            },
            0.6,
        )
    fact_name = _geometry_type(layer)
    if fact_name == "cad_geometry_candidate":
        return fact_name, geometry, 0.7
    return fact_name, {"geometry": geometry, "layer": layer, "semantic_type": _legacy_layer_semantic_type(fact_name)}, 0.7


def _is_lane_centreline_candidate(layer: str, geometry: list[tuple[float, float]]) -> bool:
    if _geometry_length(geometry) < CAD_LANE_CENTRELINE_MIN_LENGTH:
        return False
    if any(re.search(pattern, layer, flags=re.IGNORECASE) for pattern in CAD_LANE_CENTRELINE_EXCLUDE_PATTERNS):
        return False
    return any(re.search(pattern, layer, flags=re.IGNORECASE) for pattern in CAD_LANE_CENTRELINE_LAYER_PATTERNS)


def _geometry_length(geometry: list[tuple[float, float]]) -> float:
    length = 0.0
    for first, second in zip(geometry, geometry[1:]):
        length += ((first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2) ** 0.5
    return length


def _legacy_layer_semantic_type(fact_name: str) -> str:
    return {
        "stop_line_from_cad": "stop_line",
        "lane_facility_geometry_candidate_from_cad": "lane_facility",
        "lane_geometry_candidate_from_cad": "lane_geometry",
    }.get(fact_name, "cad_geometry")


def _geometry_type(layer: str) -> str:
    lowered = layer.lower()
    if "stop" in lowered:
        return "stop_line_from_cad"
    if "cross" in lowered:
        return "lane_facility_geometry_candidate_from_cad"
    if "signal" in lowered or "head" in lowered:
        return "lane_facility_geometry_candidate_from_cad"
    if "lane" in lowered:
        return "lane_geometry_candidate_from_cad"
    return "cad_geometry_candidate"


def _cad_text_payload(entity: object, text: str) -> dict:
    payload: dict[str, object] = {"text": text}
    if point := _entity_insert_point(entity):
        payload["geometry"] = _point_geometry(point)
    if isinstance(height := getattr(entity.dxf, "height", None), (int, float)):
        payload["height"] = float(height)
    if isinstance(rotation := getattr(entity.dxf, "rotation", None), (int, float)):
        payload["rotation"] = float(rotation)
    return payload


def _cad_block_payload(entity: object) -> dict:
    payload: dict[str, object] = {"name": str(entity.dxf.name)}
    if point := _entity_insert_point(entity):
        payload["geometry"] = _point_geometry(point)
    if isinstance(rotation := getattr(entity.dxf, "rotation", None), (int, float)):
        payload["rotation"] = float(rotation)
    return payload


def _semantic_text_facts(text: str, base_payload: dict[str, object], location: str, semantic_rules: dict[str, Any]) -> list[dict]:
    facts: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rule in semantic_rules.get("text_rules", []):
        if not _rule_matches(text, rule):
            continue
        fact_name = str(rule.get("fact_name") or "")
        semantic_type = str(rule.get("semantic_type") or "")
        if not fact_name or (fact_name, semantic_type) in seen:
            continue
        seen.add((fact_name, semantic_type))
        if rule.get("derive_movement"):
            payload = _movement_payload(text)
            payload["label"] = text
        else:
            payload = {"label": rule.get("label") or text}
        payload["semantic_type"] = semantic_type
        payload["source_text"] = text
        if "geometry" in base_payload:
            payload["geometry"] = base_payload["geometry"]
        if "rotation" in base_payload:
            payload["rotation"] = base_payload["rotation"]
        facts.append(_fact(fact_name, payload, location, 0.7))
    return facts


def _semantic_block_facts(name: str, base_payload: dict[str, object], location: str, semantic_rules: dict[str, Any]) -> list[dict]:
    facts: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rule in semantic_rules.get("block_rules", []):
        if not _rule_matches(name, rule):
            continue
        fact_name = str(rule.get("fact_name") or "")
        semantic_type = str(rule.get("semantic_type") or "")
        if not fact_name or (fact_name, semantic_type) in seen:
            continue
        seen.add((fact_name, semantic_type))
        payload = dict(base_payload)
        payload["semantic_type"] = semantic_type
        payload["source_block_name"] = name
        extra_payload = rule.get("payload")
        if isinstance(extra_payload, dict):
            payload.update(extra_payload)
        facts.append(_fact(fact_name, payload, location, 0.7))
    return facts


def _rule_matches(value: str, rule: dict[str, Any]) -> bool:
    match_type = str(rule.get("match") or "exact").lower()
    pattern = str(rule.get("pattern") or "")
    if not pattern:
        return False
    if match_type == "exact":
        return value.lower() == pattern.lower()
    if match_type == "prefix":
        return value.lower().startswith(pattern.lower())
    if match_type == "contains":
        return pattern.lower() in value.lower()
    if match_type == "regex":
        return re.search(pattern, value, flags=re.IGNORECASE) is not None
    return False


def _entity_insert_point(entity: object) -> tuple[float, float] | None:
    dxf = getattr(entity, "dxf", None)
    if dxf is None:
        return None
    for attribute in ("insert", "insert_point", "location"):
        value = getattr(dxf, attribute, None)
        if value is not None:
            return _xy(value)
    return None


def _point_geometry(point: tuple[float, float]) -> dict[str, float]:
    return {"x": point[0], "y": point[1]}


def _xy(value: object) -> tuple[float, float]:
    return float(value[0]), float(value[1])


def _fact(fact_name: str, value: object, location: str, confidence: float) -> dict:
    return make_fact(fact_name, value, location, confidence)

