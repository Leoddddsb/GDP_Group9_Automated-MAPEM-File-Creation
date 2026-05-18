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

    if not site.map_data.intersections:
        return ValidationReport(
            site_id="unknown",
            errors=["MapData contains no intersections"],
        )

    intersection = site.primary_intersection
    lane_ids = [lane.lane_id for lane in intersection.lane_set]
    duplicate_lane_ids = sorted(
        {lane_id for lane_id in lane_ids if lane_ids.count(lane_id) > 1}
    )
    if duplicate_lane_ids:
        errors.append(f"Duplicate lane IDs: {duplicate_lane_ids}")

    known_lanes = set(lane_ids)
    referenced_signal_groups: set[int] = set()

    for lane in intersection.lane_set:
        if not lane.node_list.nodes:
            errors.append(f"Lane {lane.lane_id} has no nodeList nodes")

        if lane.ingress_approach is None and lane.egress_approach is None:
            errors.append(
                f"Lane {lane.lane_id} has neither ingressApproach nor egressApproach"
            )

        if lane.lane_attributes.directional_use not in {"ingress", "egress", "both"}:
            warnings.append(
                f"Lane {lane.lane_id} has non-standard directionalUse "
                f"'{lane.lane_attributes.directional_use}'"
            )

        for connection in lane.connects_to:
            target = connection.connecting_lane.lane
            if target not in known_lanes:
                errors.append(f"Lane {lane.lane_id} connects to missing lane {target}")
            if connection.signal_group is None:
                errors.append(
                    f"Lane {lane.lane_id} connection to lane {target} has no signalGroup"
                )
            else:
                referenced_signal_groups.add(connection.signal_group)
            if connection.connecting_lane.maneuver is None:
                warnings.append(
                    f"Lane {lane.lane_id} connection to lane {target} has no maneuver"
                )

        if (
            lane.lane_attributes.directional_use == "ingress"
            and lane.connects_to
            and not lane.maneuvers
        ):
            warnings.append(f"Ingress lane {lane.lane_id} has no maneuvers")

    signal_head_groups = {
        location.signal_group_id for location in intersection.signal_head_locations
    }
    unlocated_signal_groups = sorted(referenced_signal_groups - signal_head_groups)
    if referenced_signal_groups and intersection.signal_head_locations and unlocated_signal_groups:
        warnings.append(
            f"Signal groups referenced by connections but missing signal head locations: "
            f"{unlocated_signal_groups}"
        )

    metrics = {
        "intersection_count": len(site.map_data.intersections),
        "lane_count": len(intersection.lane_set),
        "lane_node_count": sum(
            len(lane.node_list.nodes) for lane in intersection.lane_set
        ),
        "connection_count": sum(
            len(lane.connects_to) for lane in intersection.lane_set
        ),
        "referenced_signal_group_count": len(referenced_signal_groups),
        "signal_head_location_count": len(intersection.signal_head_locations),
    }
    return ValidationReport(
        site_id=site.site_id,
        errors=errors,
        warnings=warnings,
        metrics=metrics,
    )
