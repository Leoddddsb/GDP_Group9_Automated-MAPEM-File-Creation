from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from mapemgen.models import SiteModel


MapemSource = SiteModel | Mapping[str, Any]


def generate_json_mapem(source: MapemSource) -> dict[str, Any]:
    """Return the MAPEM-facing JSON structure for a SiteModel or fused model.

    The fusion stage already emits a nested MAPEM-shaped dict with ``header`` and
    ``mapData``. Older call sites may still pass a ``SiteModel``. This adapter
    keeps both paths working while applying the field-name normalisation expected
    by the MAPEM output layer.
    """
    raw = _as_mapping(source)
    if "mapData" not in raw:
        raise ValueError("MAPEM generation input must contain a 'mapData' object")

    output: dict[str, Any] = {}
    if "header" in raw:
        output["header"] = _normalise_mapem_value(raw["header"])
    output["mapData"] = _normalise_mapem_value(raw["mapData"])
    return output


def _as_mapping(source: MapemSource) -> Mapping[str, Any]:
    if isinstance(source, SiteModel):
        return source.as_dict()
    if isinstance(source, Mapping):
        return source
    raise TypeError(
        "MAPEM generation input must be a SiteModel or a mapping loaded from JSON"
    )


def _normalise_mapem_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _normalise_mapem_mapping(value)
    if isinstance(value, list):
        return [_normalise_mapem_value(item) for item in value]
    return deepcopy(value)


def _normalise_mapem_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    normalised: dict[str, Any] = {}
    has_long = "long" in value

    for key, item in value.items():
        if key == "lon":
            if has_long:
                continue
            output_key = "long"
        else:
            output_key = str(key)
        normalised[output_key] = _normalise_mapem_value(item)

    return normalised
