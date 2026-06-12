from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from mapemgen.ingestion.pdf_tables import extract_pdf_facts


CLASS_NAMES = [
    "road_marking",
    "lane_line",
    "stop_line",
    "crossing",
    "arrow",
    "signal_head",
]

FACT_CLASS = {
    "road_marking_candidate_from_pdf_vector": "road_marking",
    "road_marking_candidate_from_pdf_cv": "road_marking",
    "lane_line_candidate_from_pdf_vector": "lane_line",
    "lane_line_candidate_from_pdf_cv": "lane_line",
    "stop_line_candidate_from_pdf_vector": "stop_line",
    "stop_line_candidate_from_pdf_cv": "stop_line",
    "crossing_candidate_from_pdf_vector": "crossing",
    "crossing_candidate_from_pdf_cv": "crossing",
    "arrow_candidate_from_pdf_vector": "arrow",
    "arrow_candidate_from_pdf_cv": "arrow",
    "signal_head_symbol_candidate_from_pdf_vector": "signal_head",
    "signal_head_symbol_candidate_from_pdf_cv": "signal_head",
}

PAGE_PATTERN = re.compile(r"\bpage\s+(\d+)\b", re.IGNORECASE)


def build_weak_pdf_yolo_dataset(
    site_folder: str | Path,
    out_dir: str | Path,
    max_labels_per_page_class: int = 300,
) -> dict[str, Any]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("Weak PDF training dataset export requires the 'pymupdf' package.") from exc

    site_path = Path(site_folder)
    output = Path(out_dir)
    image_dir = output / "images" / "train"
    label_dir = output / "labels" / "train"
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"Training output directory already exists and is not empty: {output}")
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(path for path in site_path.rglob("*.pdf") if path.is_file())
    image_count = 0
    label_count = 0
    source_count = 0
    for pdf_path in pdf_files:
        facts = extract_pdf_facts(pdf_path)
        by_page: dict[int, list[dict]] = defaultdict(list)
        for fact in facts:
            class_name = FACT_CLASS.get(fact.get("fact_name", ""))
            if class_name is None:
                continue
            page_number = _page_number(fact.get("evidence_location", ""))
            if page_number is None:
                continue
            by_page[page_number].append(fact)
        if not by_page:
            continue
        source_count += 1
        with fitz.open(pdf_path) as document:
            for page_number, page_facts in sorted(by_page.items()):
                if page_number < 1 or page_number > len(document):
                    continue
                page = document[page_number - 1]
                stem = _safe_stem(pdf_path, site_path, page_number)
                image_path = image_dir / f"{stem}.png"
                label_path = label_dir / f"{stem}.txt"
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                pixmap.save(image_path)
                labels = _labels_for_page(page_facts, float(page.rect.width), float(page.rect.height), max_labels_per_page_class)
                label_path.write_text("\n".join(labels) + ("\n" if labels else ""), encoding="utf-8")
                image_count += 1
                label_count += len(labels)

    data_yaml = output / "data.yaml"
    data_yaml.write_text(_data_yaml(output), encoding="utf-8")
    manifest = {
        "source_pdf_count": source_count,
        "image_count": image_count,
        "label_count": label_count,
        "class_names": CLASS_NAMES,
        "data_yaml": data_yaml.as_posix(),
        "warning": "Weak labels are generated from rules, not human annotations.",
    }
    return manifest


def train_weak_pdf_yolo(
    data_yaml: str | Path,
    out_dir: str | Path,
    model: str = "yolov8n.pt",
    epochs: int = 10,
    image_size: int = 1024,
) -> dict[str, Any]:
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("YOLO training requires the optional 'ultralytics' package.") from exc

    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    detector = YOLO(model)
    result = detector.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=image_size,
        project=str(output),
        name="weak_pdf_yolo",
        exist_ok=True,
    )
    return {"result": str(result), "project": str(output / "weak_pdf_yolo")}


def require_yolo_training_package() -> None:
    try:
        import ultralytics  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("YOLO training requires the optional 'ultralytics' package.") from exc


def _labels_for_page(
    facts: list[dict],
    page_width: float,
    page_height: float,
    max_labels_per_page_class: int,
) -> list[str]:
    labels: list[str] = []
    per_class: dict[str, int] = defaultdict(int)
    for fact in facts:
        class_name = FACT_CLASS.get(fact.get("fact_name", ""))
        if class_name is None:
            continue
        if per_class[class_name] >= max_labels_per_page_class:
            continue
        geometry = ((fact.get("payload") or {}).get("value") or {}).get("geometry") or {}
        box = _box_from_geometry(geometry, page_width, page_height)
        if box is None:
            continue
        class_id = CLASS_NAMES.index(class_name)
        labels.append(f"{class_id} {box[0]:.6f} {box[1]:.6f} {box[2]:.6f} {box[3]:.6f}")
        per_class[class_name] += 1
    return labels


def _box_from_geometry(geometry: dict, page_width: float, page_height: float) -> tuple[float, float, float, float] | None:
    x0, y0, x1, y1 = _raw_box(geometry)
    if None in (x0, y0, x1, y1):
        return None
    left = min(float(x0), float(x1))
    right = max(float(x0), float(x1))
    top = min(float(y0), float(y1))
    bottom = max(float(y0), float(y1))
    if right - left < 4:
        left -= 2
        right += 2
    if bottom - top < 4:
        top -= 2
        bottom += 2
    left = max(0.0, min(page_width, left))
    right = max(0.0, min(page_width, right))
    top = max(0.0, min(page_height, top))
    bottom = max(0.0, min(page_height, bottom))
    if right <= left or bottom <= top or page_width <= 0 or page_height <= 0:
        return None
    x_center = ((left + right) / 2) / page_width
    y_center = ((top + bottom) / 2) / page_height
    width = (right - left) / page_width
    height = (bottom - top) / page_height
    return x_center, y_center, width, height


def _raw_box(geometry: dict) -> tuple[float | int | None, float | int | None, float | int | None, float | int | None]:
    if all(key in geometry for key in ("x0", "top", "x1", "bottom")):
        return geometry.get("x0"), geometry.get("top"), geometry.get("x1"), geometry.get("bottom")
    if all(key in geometry for key in ("x1", "y1", "x2", "y2")):
        return geometry.get("x1"), geometry.get("y1"), geometry.get("x2"), geometry.get("y2")
    return None, None, None, None


def _page_number(location: str) -> int | None:
    match = PAGE_PATTERN.search(location)
    return int(match.group(1)) if match else None


def _safe_stem(pdf_path: Path, site_path: Path, page_number: int) -> str:
    try:
        relative = pdf_path.relative_to(site_path)
    except ValueError:
        relative = pdf_path.name
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(relative))
    return f"{stem}_page_{page_number}"


def _data_yaml(output: Path) -> str:
    names = "\n".join(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
    return f"path: {output.as_posix()}\ntrain: images/train\nval: images/train\nnames:\n{names}\n"
