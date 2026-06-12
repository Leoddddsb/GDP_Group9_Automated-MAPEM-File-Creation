from __future__ import annotations

import os
from pathlib import Path

from mapemgen.ingestion.fact_records import make_fact


def extract_mova_facts(path: str | Path) -> list[dict]:
    target = Path(path)
    configured_path = os.environ.get("MOVA_TOOLS_PATH")
    if not configured_path or not Path(configured_path).is_file():
        raise RuntimeError(
            "MOVA extraction requires the official MOVA Tools application. "
            "Set MOVA_TOOLS_PATH to the full path of the installed MOVATools.exe. "
            "Use MOVA Tools to export text or report files into the site folder "
            "before running extraction."
        )
    return [
        make_fact(
            "mova_tools_manual_export_required",
            (
                "MOVA binary fields are not decoded directly. Use the official MOVA Tools "
                "application to export text or report files into the site folder."
            ),
            "file",
            1.0,
        ),
        make_fact("file_metadata", {"file_size_bytes": target.stat().st_size}, "file", 1.0),
    ]
