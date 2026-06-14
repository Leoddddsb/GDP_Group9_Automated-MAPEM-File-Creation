from __future__ import annotations

import os
from pathlib import Path

from mapemgen.ingestion.fact_records import make_fact


def extract_mova_facts(path: str | Path) -> list[dict]:
    target = Path(path)
    configured_path = os.environ.get("MOVA_TOOLS_PATH")
    if not configured_path or not Path(configured_path).is_file():
        return [
            make_fact(
                "mova_tools_not_configured_skipped",
                {
                    "skipped": True,
                    "priority": "low",
                    "reason": (
                        "MOVA Tools is not configured. The .mova binary is kept as "
                        "a low-priority supplemental source and does not block "
                        "lane extraction."
                    ),
                    "next_step": (
                        "If MOVA evidence is required later, install MOVA Tools, "
                        "set MOVA_TOOLS_PATH, export text/report files, and rerun extraction."
                    ),
                },
                "file",
                1.0,
            ),
            make_fact("file_metadata", {"file_size_bytes": target.stat().st_size}, "file", 1.0),
        ]
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
