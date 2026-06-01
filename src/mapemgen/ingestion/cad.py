"""DXF extraction and DWG conversion through ODA File Converter."""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path


def extract_dxf_facts(path: str | Path) -> list[dict]:
    try:
        import ezdxf
    except ImportError as exc:
        raise RuntimeError("DXF extraction requires the 'ezdxf' package.") from exc
    return _extract_document_facts(ezdxf.readfile(path))


def extract_dwg_facts(path: str | Path) -> list[dict]:
    try:
        from ezdxf.addons import odafc
    except ImportError as exc:
        raise RuntimeError("DWG extraction requires 'ezdxf' and ODA File Converter.") from exc
    configured_path = os.environ.get("ODAFC_PATH")
    if configured_path:
        odafc.win_exec_path = configured_path
    if not odafc.is_installed():
        raise RuntimeError(
            "DWG extraction requires ODA File Converter to be installed. "
            "If it is installed outside the default location, set ODAFC_PATH "
            "to the full path of ODAFileConverter.exe."
        )
    return _extract_document_facts(odafc.readfile(path))


def extract_cad_geometry(dxf_path: str) -> dict:
    return {"extracted_facts": extract_dxf_facts(dxf_path)}


def _extract_document_facts(document: object) -> list[dict]:
    modelspace = document.modelspace()
    entities = list(modelspace)
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
            facts.append(_fact(_geometry_type(layer), geometry, location, 0.7))
        elif entity_type in {"LWPOLYLINE", "POLYLINE"}:
            geometry = [_xy(point) for point in entity.get_points()]
            points.extend(geometry)
            facts.append(_fact(_geometry_type(layer), geometry, location, 0.75))
        elif entity_type in {"TEXT", "MTEXT"}:
            text = entity.plain_text() if hasattr(entity, "plain_text") else entity.dxf.text
            facts.append(_fact("cad_text_label", text, location, 0.8))
        elif entity_type == "INSERT":
            facts.append(_fact("cad_block_reference", entity.dxf.name, location, 0.8))
    if points:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        facts.append(_fact("coordinate_bounds", {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}, "modelspace geometry", 0.9))
    return facts


def _geometry_type(layer: str) -> str:
    lowered = layer.lower()
    if "stop" in lowered:
        return "stop_line_candidate"
    if "cross" in lowered:
        return "crossing_candidate"
    if "signal" in lowered or "head" in lowered:
        return "signal_head_candidate"
    return "lane_candidate" if "lane" in lowered else "cad_geometry_candidate"


def _xy(value: object) -> tuple[float, float]:
    return float(value[0]), float(value[1])


def _fact(fact_type: str, value: object, location: str, confidence: float) -> dict:
    return {"fact_type": fact_type, "value": value, "evidence_location": location, "confidence": confidence}
