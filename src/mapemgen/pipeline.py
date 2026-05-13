from __future__ import annotations

from dataclasses import dataclass

from mapemgen.generators.asn1_mapem import generate_asn1_mapem
from mapemgen.generators.json_mapem import generate_json_mapem
from mapemgen.models import SiteModel
from mapemgen.validation.report import ValidationReport, validate_site_model


@dataclass(frozen=True)
class PipelineOutputs:
    mapem_json: dict
    mapem_asn1: str
    validation_report: dict


def validate_site(site: SiteModel) -> ValidationReport:
    return validate_site_model(site)


def generate_outputs(site: SiteModel) -> PipelineOutputs:
    report = validate_site_model(site)
    return PipelineOutputs(
        mapem_json=generate_json_mapem(site),
        mapem_asn1=generate_asn1_mapem(site),
        validation_report=report.as_dict(),
    )

