"""CAD/DXF geometry extraction boundary.

The v1 implementation should convert confidential DWG files to DXF locally and
extract only structured, non-confidential intermediate data into SiteModel.
"""

from __future__ import annotations


def extract_cad_geometry(_dxf_path: str) -> dict:
    raise NotImplementedError("CAD extraction is planned for the CAD module.")

