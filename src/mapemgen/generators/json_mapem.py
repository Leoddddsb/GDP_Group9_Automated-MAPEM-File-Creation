from __future__ import annotations

from mapemgen.models import SiteModel


def generate_json_mapem(site: SiteModel) -> dict:
    return site.as_dict()
