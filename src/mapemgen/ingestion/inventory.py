from __future__ import annotations

import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


PARSER_BY_EXTENSION = {
    "pdf": "pdf_parser",
    "docx": "docx_parser",
    "dwg": "cad_parser_after_conversion",
    "dxf": "cad_parser",
    "zip": "zip_inventory_parser",
    "txt": "ram_text_parser",
    "8tx": "ram_text_parser",
    "mova": "mova_availability_recorder",
    "geojson": "gis_parser",
    "json": "gis_parser",
    "osm": "gis_parser",
    "gpkg": "gis_parser",
    "shp": "gis_parser",
}

TEXT_READABLE_EXTENSIONS = {"txt", "8tx"}
DIRECT_ARCHIVE_EXTENSIONS = {"zip"}
NOT_DIRECTLY_READABLE_EXTENSIONS = {
    "pdf",
    "docx",
    "dwg",
    "dxf",
    "mova",
    "geojson",
    "json",
    "osm",
    "gpkg",
    "shp",
}

FILENAME_HINT_RULES = [
    (("spec", "2500config", "configuration"), "possible configuration file"),
    (("drawing", "asbuilt", "detaileddesign"), "possible drawing / layout file"),
    (("utcform",), "possible UTC form"),
    (("scootdets",), "possible SCOOT detector data"),
    (("ramdata",), "possible RAM / override data"),
    (("mova",), "possible MOVA/control logic data"),
]


def build_site_inventory(
    site_folder: str | Path,
    site_id: str,
    site_name: str = "",
    dataset: str = "",
) -> dict[str, Any]:
    folder = Path(site_folder)
    if not folder.exists():
        raise FileNotFoundError(f"Site folder does not exist: {folder}")
    if not folder.is_dir():
        raise ValueError(f"Site folder must be a directory: {folder}")

    source_files = [_build_source_file(path) for path in sorted(_iter_files(folder), key=_path_string)]
    file_type_counts = Counter(source["file_type"] for source in source_files)
    unreadable_files = sum(
        1 for source in source_files if source["readable_status"] == "unreadable"
    )

    return {
        "site_id": str(site_id),
        "site_name": site_name or folder.name,
        "local_authority_or_dataset": dataset,
        "input_folder_path": _path_string(folder),
        "inventory_summary": {
            "total_files": len(source_files),
            "file_type_counts": dict(sorted(file_type_counts.items())),
            "readable_files": len(source_files) - unreadable_files,
            "unreadable_files": unreadable_files,
        },
        "source_files": source_files,
    }


def _iter_files(folder: Path) -> list[Path]:
    return [path for path in folder.rglob("*") if path.is_file()]


def _build_source_file(path: Path) -> dict[str, Any]:
    file_type = _file_type(path)
    readable_status, notes = _readability(path, file_type)
    return {
        "file_path": _path_string(path),
        "file_type": file_type,
        "file_size_bytes": _file_size(path),
        "filename_hints": _filename_hints(path),
        "readable_status": readable_status,
        "parser_to_use": PARSER_BY_EXTENSION.get(file_type, "manual_review"),
        "notes": notes,
    }


def _file_type(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return suffix or "unknown"


def _file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _filename_hints(path: Path) -> list[str]:
    normalized_name = path.name.lower().replace(" ", "").replace("_", "").replace("-", "")
    hints: list[str] = []
    for keywords, hint in FILENAME_HINT_RULES:
        if any(keyword in normalized_name for keyword in keywords):
            hints.append(hint)

    if _file_type(path) == "zip" and _zip_contains_extension(path, ".dwg"):
        hints.append("possible CAD package")

    return hints


def _readability(path: Path, file_type: str) -> tuple[str, str]:
    try:
        with path.open("rb"):
            pass
    except OSError as exc:
        return "unreadable", str(exc)

    if file_type in TEXT_READABLE_EXTENSIONS:
        return "text_readable", ""
    if file_type in DIRECT_ARCHIVE_EXTENSIONS:
        return _zip_readability(path)
    if file_type in NOT_DIRECTLY_READABLE_EXTENSIONS:
        return "available_not_directly_readable", ""
    return "available_unknown_format", ""


def _zip_readability(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            archive.namelist()
    except (OSError, zipfile.BadZipFile) as exc:
        return "unreadable", str(exc)
    return "archive_readable", ""


def _zip_contains_extension(path: Path, extension: str) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return any(name.lower().endswith(extension.lower()) for name in archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def _path_string(path: Path) -> str:
    return path.as_posix()
