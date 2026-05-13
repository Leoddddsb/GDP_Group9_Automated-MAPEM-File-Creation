"""GIS and georeferencing boundary."""

from __future__ import annotations


def bng_to_wgs84(_easting: float, _northing: float) -> tuple[float, float]:
    raise NotImplementedError("BNG to WGS84 conversion will use pyproj in the GIS module.")

