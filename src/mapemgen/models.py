from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


Coordinate = tuple[float, float]


@dataclass(frozen=True)
class Lane:
    lane_id: int
    name: str
    lane_type: str
    approach_id: int
    direction: str
    centerline: list[Coordinate]
    maneuvers: list[str] = field(default_factory=list)
    connects_to: list[int] = field(default_factory=list)
    signal_group: int | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Lane":
        return cls(
            lane_id=int(raw["lane_id"]),
            name=str(raw.get("name", "")),
            lane_type=str(raw.get("lane_type", "vehicle")),
            approach_id=int(raw["approach_id"]),
            direction=str(raw.get("direction", "ingress")),
            centerline=[(float(x), float(y)) for x, y in raw.get("centerline", [])],
            maneuvers=[str(value) for value in raw.get("maneuvers", [])],
            connects_to=[int(value) for value in raw.get("connects_to", [])],
            signal_group=(
                int(raw["signal_group"]) if raw.get("signal_group") is not None else None
            ),
        )


@dataclass(frozen=True)
class SignalGroup:
    signal_group_id: int
    phase_label: str
    description: str
    controlled_lanes: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SignalGroup":
        return cls(
            signal_group_id=int(raw["signal_group_id"]),
            phase_label=str(raw.get("phase_label", "")),
            description=str(raw.get("description", "")),
            controlled_lanes=[int(value) for value in raw.get("controlled_lanes", [])],
        )


@dataclass(frozen=True)
class SiteModel:
    site_id: str
    name: str
    revision: int
    ref_point: Coordinate
    lane_width_m: float
    source_notes: list[str]
    lanes: list[Lane]
    signal_groups: list[SignalGroup]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SiteModel":
        ref_point = raw["ref_point"]
        return cls(
            site_id=str(raw["site_id"]),
            name=str(raw.get("name", raw["site_id"])),
            revision=int(raw.get("revision", 1)),
            ref_point=(float(ref_point["lat"]), float(ref_point["lon"])),
            lane_width_m=float(raw.get("lane_width_m", 3.25)),
            source_notes=[str(value) for value in raw.get("source_notes", [])],
            lanes=[Lane.from_dict(value) for value in raw.get("lanes", [])],
            signal_groups=[
                SignalGroup.from_dict(value) for value in raw.get("signal_groups", [])
            ],
        )

