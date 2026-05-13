from __future__ import annotations

import json
from dataclasses import dataclass, field

from mapemgen.models import SiteModel


@dataclass(frozen=True)
class ValidationReport:
    site_id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, float | int] = field(default_factory=dict)

    @property
    def is_usable(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {
            "site_id": self.site_id,
            "is_usable": self.is_usable,
            "errors": self.errors,
            "warnings": self.warnings,
            "metrics": self.metrics,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False)


def validate_site_model(site: SiteModel) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []

    lane_ids = [lane.lane_id for lane in site.lanes]
    duplicate_lane_ids = sorted({lane_id for lane_id in lane_ids if lane_ids.count(lane_id) > 1})
    if duplicate_lane_ids:
        errors.append(f"Duplicate lane IDs: {duplicate_lane_ids}")

    known_lanes = set(lane_ids)
    for lane in site.lanes:
        if not lane.centerline:
            errors.append(f"Lane {lane.lane_id} has no centreline nodes")
        if lane.direction not in {"ingress", "egress", "internal"}:
            warnings.append(f"Lane {lane.lane_id} has non-standard direction '{lane.direction}'")
        for target in lane.connects_to:
            if target not in known_lanes:
                errors.append(f"Lane {lane.lane_id} connects to missing lane {target}")

    known_signal_groups = {group.signal_group_id for group in site.signal_groups}
    for lane in site.lanes:
        if lane.signal_group is not None and lane.signal_group not in known_signal_groups:
            errors.append(
                f"Lane {lane.lane_id} references missing signal group {lane.signal_group}"
            )

    controlled = {
        lane_id for group in site.signal_groups for lane_id in group.controlled_lanes
    }
    uncontrolled_ingress = [
        lane.lane_id
        for lane in site.lanes
        if lane.direction == "ingress" and lane.lane_id not in controlled
    ]
    if uncontrolled_ingress:
        warnings.append(f"Ingress lanes not controlled by a signal group: {uncontrolled_ingress}")

    metrics = {
        "lane_count": len(site.lanes),
        "signal_group_count": len(site.signal_groups),
        "lane_node_count": sum(len(lane.centerline) for lane in site.lanes),
        "controlled_lane_ratio": (
            len(controlled & known_lanes) / len(known_lanes) if known_lanes else 0
        ),
    }
    return ValidationReport(
        site_id=site.site_id,
        errors=errors,
        warnings=warnings,
        metrics=metrics,
    )

