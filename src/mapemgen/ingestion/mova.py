from __future__ import annotations

import os
from pathlib import Path


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
        {
            "fact_type": "mova_tools_manual_export_required",
            "value": (
                "MOVA binary fields are not decoded directly. Use the official MOVA Tools "
                "application to export text or report files into the site folder."
            ),
            "evidence_location": "file",
            "confidence": 1.0,
        },
        {
            "fact_type": "file_metadata",
            "value": {"file_size_bytes": target.stat().st_size},
            "evidence_location": "file",
            "confidence": 1.0,
        },
    ]
