"""Computer vision boundary for PDF image-page feature extraction."""

from __future__ import annotations

import math
from typing import Any

from mapemgen.ingestion.fact_records import make_fact
from mapemgen.ingestion.text_facts import extract_metadata_facts


PDF_OCR_KEYWORD_FACTS = {
    "phase": "phase_candidate_from_pdf_ocr",
}


def describe_image_page(page: Any, page_number: int) -> list[dict]:
    """Record non-semantic image features for a PDF page.

    This does not run OCR or computer vision. It preserves enough page-level
    information for a later OCR/CV stage to target likely scanned drawings.
    """
    images = list(getattr(page, "images", []) or [])
    value = {
        "page_width": _number_or_none(getattr(page, "width", None)),
        "page_height": _number_or_none(getattr(page, "height", None)),
        "image_count": len(images),
        "image_boxes": [_image_box(image) for image in images[:20]],
    }
    return []


def extract_pdf_vector_facts(page: Any, page_number: int) -> list[dict]:
    lines = list(getattr(page, "lines", []) or [])
    curves = list(getattr(page, "curves", []) or [])
    rects = list(getattr(page, "rects", []) or [])
    if not lines and not curves and not rects:
        return []
    page_width = _number_or_none(getattr(page, "width", None))
    page_height = _number_or_none(getattr(page, "height", None))

    facts: list[dict] = []
    for index, line in enumerate(lines, start=1):
        value = _vector_object(line)
        location = f"page {page_number} vector line {index}"
        facts.extend(_semantic_line_candidates(value, location, "pdf_vector", page_width, page_height))
    for index, curve in enumerate(curves, start=1):
        value = _vector_object(curve)
        location = f"page {page_number} vector curve {index}"
        facts.extend(_semantic_curve_candidates(value, location, "pdf_vector", page_width, page_height))
    for index, rect in enumerate(rects, start=1):
        value = _vector_object(rect)
        location = f"page {page_number} vector rect {index}"
        facts.extend(_semantic_rect_candidates(value, location, "pdf_vector", page_width, page_height))
    return facts


def extract_pdf_image_facts(path: str, page_numbers: list[int] | None = None) -> list[dict]:
    try:
        import cv2
        import fitz
        import numpy
        import pytesseract
    except ImportError as exc:
        raise RuntimeError(
            "PDF image recognition requires optional packages: pymupdf, pytesseract, opencv-python."
        ) from exc

    facts: list[dict] = []
    with fitz.open(path) as document:
        selected_pages = page_numbers or list(range(1, len(document) + 1))
        for page_number in selected_pages:
            page = document[page_number - 1]
            image = _render_pdf_page(page, fitz, cv2, numpy)
            location_prefix = f"page {page_number} image"
            facts.extend(_extract_ocr_facts(image, pytesseract, location_prefix))
            facts.extend(_extract_line_facts(image, cv2, location_prefix))
    return facts


def extract_diagram_features(_pdf_path: str) -> dict:
    raise NotImplementedError("PDF diagram extraction is planned for the CV module.")


def _render_pdf_page(page: Any, fitz: Any, cv2: Any, numpy: Any) -> Any:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    image_bytes = pixmap.tobytes("png")
    buffer = numpy.frombuffer(image_bytes, dtype=numpy.uint8)
    return cv2.imdecode(buffer, cv2.IMREAD_COLOR)


def _extract_ocr_facts(image: Any, pytesseract: Any, location_prefix: str) -> list[dict]:
    text = pytesseract.image_to_string(image, config="--psm 6")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    facts: list[dict] = []
    facts.extend(_extract_ocr_keyword_facts(lines, location_prefix))
    facts.extend(extract_metadata_facts(lines, f"{location_prefix} ocr line"))
    return facts


def _extract_ocr_keyword_facts(lines: list[str], location_prefix: str) -> list[dict]:
    facts: list[dict] = []
    for index, line in enumerate(lines, start=1):
        lowered = line.lower()
        emitted: set[str] = set()
        for keyword, fact_name in PDF_OCR_KEYWORD_FACTS.items():
            if keyword in lowered and fact_name not in emitted:
                facts.append(_fact(fact_name, line, f"{location_prefix} ocr line {index}", 0.55))
                emitted.add(fact_name)
    return facts


def _extract_line_facts(image: Any, cv2: Any, location_prefix: str) -> list[dict]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _threshold, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    edges = cv2.Canny(closed, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, math.pi / 180, threshold=80, minLineLength=40, maxLineGap=8)
    if lines is None:
        return []
    facts: list[dict] = []
    for index, line in enumerate(list(lines)[:50], start=1):
        x1, y1, x2, y2 = _line_coordinates(line)
        value = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        location = f"{location_prefix} cv line {index}"
        facts.extend(_semantic_line_candidates(value, location, "pdf_cv", None, None))
    return facts


def _line_coordinates(line: Any) -> tuple[int, int, int, int]:
    coords = line[0] if len(line) == 1 else line
    return tuple(int(value) for value in coords[:4])


def _image_box(image: dict) -> dict:
    return {
        "x0": _number_or_none(image.get("x0")),
        "top": _number_or_none(image.get("top")),
        "x1": _number_or_none(image.get("x1")),
        "bottom": _number_or_none(image.get("bottom")),
        "width": _number_or_none(image.get("width")),
        "height": _number_or_none(image.get("height")),
    }


def _vector_object(item: dict) -> dict:
    value = {
        "x0": _number_or_none(item.get("x0")),
        "top": _number_or_none(item.get("top")),
        "x1": _number_or_none(item.get("x1")),
        "bottom": _number_or_none(item.get("bottom")),
        "width": _number_or_none(item.get("width")),
        "height": _number_or_none(item.get("height")),
        "linewidth": _number_or_none(item.get("linewidth")),
    }
    points = item.get("pts")
    if isinstance(points, list):
        value["points"] = [_point(point) for point in points[:20]]
    return value


def _semantic_line_candidates(
    value: dict,
    location: str,
    source: str,
    page_width: float | int | None,
    page_height: float | int | None,
) -> list[dict]:
    length = _line_length(value)
    if length is None or length < 15:
        return []
    if _is_page_border_or_margin(value, page_width, page_height):
        return []
    if _is_full_width_or_height_rule(value, page_width, page_height):
        return []
    facts = [
        _fact(
            f"road_marking_candidate_from_{source}",
            _semantic_payload(value, "line segment detected in drawing region"),
            location,
            0.42,
        )
    ]
    if length >= 25:
        facts.append(
            _fact(
                f"lane_line_candidate_from_{source}",
                _semantic_payload(value, "long line segment candidate"),
                location,
                0.45,
            )
        )
    return facts


def _semantic_curve_candidates(
    value: dict,
    location: str,
    source: str,
    page_width: float | int | None,
    page_height: float | int | None,
) -> list[dict]:
    if _is_page_border_or_margin(value, page_width, page_height):
        return []
    facts: list[dict] = []
    if _is_compact_symbol(value):
        facts.append(
            _fact(
                f"signal_head_symbol_candidate_from_{source}",
                _semantic_payload(value, "compact curve symbol candidate"),
                location,
                0.42,
            )
        )
    return facts


def _semantic_rect_candidates(
    value: dict,
    location: str,
    source: str,
    page_width: float | int | None,
    page_height: float | int | None,
) -> list[dict]:
    if _is_page_border_or_margin(value, page_width, page_height):
        return []
    facts: list[dict] = []
    if _is_compact_symbol(value):
        facts.append(
            _fact(
                f"signal_head_symbol_candidate_from_{source}",
                _semantic_payload(value, "compact rectangle symbol candidate"),
                location,
                0.42,
            )
        )
    return facts


def _semantic_payload(value: dict, basis: str) -> dict:
    return {
        "geometry": value,
        "recognition_basis": basis,
        "requires_context_match": True,
    }


def _line_length(value: dict) -> float | None:
    x0, y0, x1, y1 = _line_endpoints(value)
    if None in (x0, y0, x1, y1):
        return None
    return math.hypot(float(x1) - float(x0), float(y1) - float(y0))


def _is_near_axis_aligned(value: dict) -> bool:
    x0, y0, x1, y1 = _line_endpoints(value)
    if None in (x0, y0, x1, y1):
        return False
    return abs(float(x1) - float(x0)) <= 2 or abs(float(y1) - float(y0)) <= 2


def _is_page_border_or_margin(value: dict, page_width: float | int | None, page_height: float | int | None) -> bool:
    box = _box(value)
    if box is None or page_width is None or page_height is None or page_width <= 0 or page_height <= 0:
        return False
    left, top, right, bottom = box
    margin = max(3.0, min(float(page_width), float(page_height)) * 0.01)
    near_left = left <= margin
    near_top = top <= margin
    near_right = right >= float(page_width) - margin
    near_bottom = bottom >= float(page_height) - margin
    spans_width = (right - left) >= float(page_width) * 0.85
    spans_height = (bottom - top) >= float(page_height) * 0.85
    return (spans_width and (near_top or near_bottom)) or (spans_height and (near_left or near_right))


def _is_full_width_or_height_rule(value: dict, page_width: float | int | None, page_height: float | int | None) -> bool:
    box = _box(value)
    if box is None or page_width is None or page_height is None or page_width <= 0 or page_height <= 0:
        return False
    left, top, right, bottom = box
    return (right - left) >= float(page_width) * 0.9 or (bottom - top) >= float(page_height) * 0.9


def _line_endpoints(value: dict) -> tuple[float | int | None, float | int | None, float | int | None, float | int | None]:
    if all(key in value for key in ("x1", "y1", "x2", "y2")):
        return value.get("x1"), value.get("y1"), value.get("x2"), value.get("y2")
    return value.get("x0"), value.get("top"), value.get("x1"), value.get("bottom")


def _is_compact_symbol(value: dict) -> bool:
    width = _dimension(value, "width", "x0", "x1")
    height = _dimension(value, "height", "top", "bottom")
    if width is None or height is None:
        return False
    larger = max(width, height)
    smaller = min(width, height)
    return 5 <= larger <= 45 and smaller / larger >= 0.5


def _is_arrow_like_curve(value: dict) -> bool:
    width = _dimension(value, "width", "x0", "x1")
    height = _dimension(value, "height", "top", "bottom")
    if width is None or height is None:
        return False
    larger = max(width, height)
    smaller = min(width, height)
    if larger < 10 or larger > 180:
        return False
    ratio = smaller / larger if larger else 0
    return 0.12 <= ratio <= 0.65


def _is_crossing_like_rect(value: dict) -> bool:
    width = _dimension(value, "width", "x0", "x1")
    height = _dimension(value, "height", "top", "bottom")
    if width is None or height is None:
        return False
    larger = max(width, height)
    smaller = min(width, height)
    if larger < 8 or larger > 180 or smaller < 2:
        return False
    ratio = smaller / larger if larger else 0
    return ratio <= 0.35


def _box(value: dict) -> tuple[float, float, float, float] | None:
    if all(key in value for key in ("x1", "y1", "x2", "y2")):
        x0 = value.get("x1")
        top = value.get("y1")
        x1 = value.get("x2")
        bottom = value.get("y2")
        if None in (x0, top, x1, bottom):
            return None
        return min(float(x0), float(x1)), min(float(top), float(bottom)), max(float(x0), float(x1)), max(float(top), float(bottom))
    x0 = _first_number(value, "x0", "x1")
    top = _first_number(value, "top", "y1")
    x1 = _first_number(value, "x1", "x2")
    bottom = _first_number(value, "bottom", "y2")
    if None in (x0, top, x1, bottom):
        return None
    return min(float(x0), float(x1)), min(float(top), float(bottom)), max(float(x0), float(x1)), max(float(top), float(bottom))


def _dimension(value: dict, direct_key: str, start_key: str, end_key: str) -> float | None:
    direct = value.get(direct_key)
    if isinstance(direct, (int, float)) and not isinstance(direct, bool):
        return abs(float(direct))
    start = value.get(start_key)
    end = value.get(end_key)
    if isinstance(start, (int, float)) and isinstance(end, (int, float)):
        return abs(float(end) - float(start))
    return None


def _first_number(value: dict, *keys: str) -> float | int | None:
    for key in keys:
        item = value.get(key)
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            return item
    return None


def _point(point: object) -> list[float] | None:
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        return None
    x = _number_or_none(point[0])
    y = _number_or_none(point[1])
    if x is None or y is None:
        return None
    return [float(x), float(y)]


def _number_or_none(value: object) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _fact(fact_name: str, value: object, location: str, confidence: float) -> dict:
    return make_fact(fact_name, value, location, confidence)
