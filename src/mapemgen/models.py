from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


Coordinate = tuple[float, float]


def _string_list(values: list[Any] | None) -> list[str]:
    return [str(value) for value in values or []]


@dataclass(frozen=True)
class Position3D:
    lat: float
    lon: float
    elevation: float | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Position3D":
        return cls(
            lat=float(raw["lat"]),
            lon=float(raw["lon"]),
            elevation=float(raw["elevation"]) if raw.get("elevation") is not None else None,
        )

    def as_dict(self) -> dict[str, float]:
        value = {"lat": self.lat, "lon": self.lon}
        if self.elevation is not None:
            value["elevation"] = self.elevation
        return value


@dataclass(frozen=True)
class IntersectionReferenceID:
    region: int | None
    id: int | str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "IntersectionReferenceID":
        return cls(
            region=int(raw["region"]) if raw.get("region") is not None else None,
            id=raw["id"],
        )

    def as_dict(self) -> dict[str, int | str]:
        value: dict[str, int | str] = {"id": self.id}
        if self.region is not None:
            value["region"] = self.region
        return value


@dataclass(frozen=True)
class LaneAttributes:
    lane_type: str
    directional_use: str
    shared_with: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "LaneAttributes":
        raw = raw or {}
        return cls(
            lane_type=str(raw.get("laneType", raw.get("lane_type", "vehicle"))),
            directional_use=str(
                raw.get("directionalUse", raw.get("directional_use", "ingress"))
            ),
            shared_with=_string_list(raw.get("sharedWith", raw.get("shared_with", []))),
        )

    def as_dict(self) -> dict:
        return {
            "laneType": self.lane_type,
            "directionalUse": self.directional_use,
            "sharedWith": self.shared_with,
        }


@dataclass(frozen=True)
class NodeXY:
    x: float
    y: float

    @classmethod
    def from_value(cls, raw: dict[str, Any] | list[Any] | tuple[Any, ...]) -> "NodeXY":
        if isinstance(raw, dict):
            return cls(x=float(raw["x"]), y=float(raw["y"]))
        return cls(x=float(raw[0]), y=float(raw[1]))

    def as_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True)
class NodeList:
    nodes: list[NodeXY]

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | list[Any]) -> "NodeList":
        if isinstance(raw, dict):
            raw_nodes = raw.get("nodes", [])
        else:
            raw_nodes = raw
        return cls(nodes=[NodeXY.from_value(value) for value in raw_nodes])

    def as_dict(self) -> dict:
        return {"nodes": [node.as_dict() for node in self.nodes]}


@dataclass(frozen=True)
class ConnectingLane:
    lane: int
    maneuver: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | int) -> "ConnectingLane":
        if isinstance(raw, int):
            return cls(lane=raw)
        return cls(
            lane=int(raw["lane"]),
            maneuver=str(raw["maneuver"]) if raw.get("maneuver") is not None else None,
        )

    def as_dict(self) -> dict:
        value = {"lane": self.lane}
        if self.maneuver is not None:
            value["maneuver"] = self.maneuver
        return value


@dataclass(frozen=True)
class Connection:
    connecting_lane: ConnectingLane
    signal_group: int | None = None
    connection_id: int | None = None
    user_class: int | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | int) -> "Connection":
        if isinstance(raw, int):
            return cls(connecting_lane=ConnectingLane(lane=raw))
        connecting_raw = raw.get("connectingLane", raw.get("connecting_lane"))
        return cls(
            connecting_lane=ConnectingLane.from_dict(connecting_raw),
            signal_group=(
                int(raw["signalGroup"]) if raw.get("signalGroup") is not None else None
            ),
            connection_id=(
                int(raw["connectionID"]) if raw.get("connectionID") is not None else None
            ),
            user_class=int(raw["userClass"]) if raw.get("userClass") is not None else None,
        )

    def as_dict(self) -> dict:
        value = {"connectingLane": self.connecting_lane.as_dict()}
        if self.signal_group is not None:
            value["signalGroup"] = self.signal_group
        if self.connection_id is not None:
            value["connectionID"] = self.connection_id
        if self.user_class is not None:
            value["userClass"] = self.user_class
        return value


@dataclass(frozen=True)
class GenericLane:
    lane_id: int
    name: str
    lane_attributes: LaneAttributes
    node_list: NodeList
    ingress_approach: int | None = None
    egress_approach: int | None = None
    maneuvers: list[str] = field(default_factory=list)
    connects_to: list[Connection] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "GenericLane":
        # Backward-compatible fallbacks keep older MVP files readable during migration.
        lane_attributes = LaneAttributes.from_dict(
            raw.get("laneAttributes")
            or {
                "laneType": raw.get("lane_type"),
                "directionalUse": raw.get("direction"),
            }
        )
        node_list = NodeList.from_dict(raw.get("nodeList", raw.get("centerline", [])))
        legacy_signal_group = raw.get("signal_group")
        connections = [Connection.from_dict(value) for value in raw.get("connectsTo", raw.get("connects_to", []))]
        if legacy_signal_group is not None:
            connections = [
                Connection(
                    connecting_lane=connection.connecting_lane,
                    signal_group=connection.signal_group or int(legacy_signal_group),
                    connection_id=connection.connection_id,
                    user_class=connection.user_class,
                )
                for connection in connections
            ]

        return cls(
            lane_id=int(raw["laneID"] if "laneID" in raw else raw["lane_id"]),
            name=str(raw.get("name", "")),
            ingress_approach=(
                int(raw["ingressApproach"])
                if raw.get("ingressApproach") is not None
                else (int(raw["approach_id"]) if raw.get("direction") == "ingress" and raw.get("approach_id") is not None else None)
            ),
            egress_approach=(
                int(raw["egressApproach"])
                if raw.get("egressApproach") is not None
                else (int(raw["approach_id"]) if raw.get("direction") == "egress" and raw.get("approach_id") is not None else None)
            ),
            lane_attributes=lane_attributes,
            maneuvers=_string_list(raw.get("maneuvers", [])),
            node_list=node_list,
            connects_to=connections,
        )

    def as_dict(self) -> dict:
        value = {
            "laneID": self.lane_id,
            "name": self.name,
            "laneAttributes": self.lane_attributes.as_dict(),
            "maneuvers": self.maneuvers,
            "nodeList": self.node_list.as_dict(),
            "connectsTo": [connection.as_dict() for connection in self.connects_to],
        }
        if self.ingress_approach is not None:
            value["ingressApproach"] = self.ingress_approach
        if self.egress_approach is not None:
            value["egressApproach"] = self.egress_approach
        return value


@dataclass(frozen=True)
class SpeedLimit:
    type: str
    speed: int

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SpeedLimit":
        return cls(type=str(raw["type"]), speed=int(raw["speed"]))

    def as_dict(self) -> dict:
        return {"type": self.type, "speed": self.speed}


@dataclass(frozen=True)
class SignalHeadLocation:
    node_xy: NodeXY
    signal_group_id: int
    node_z: float | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SignalHeadLocation":
        return cls(
            node_xy=NodeXY.from_value(raw["nodeXY"]),
            node_z=float(raw["nodeZ"]) if raw.get("nodeZ") is not None else None,
            signal_group_id=int(raw["signalGroupID"]),
        )

    def as_dict(self) -> dict:
        value = {"nodeXY": self.node_xy.as_dict(), "signalGroupID": self.signal_group_id}
        if self.node_z is not None:
            value["nodeZ"] = self.node_z
        return value


@dataclass(frozen=True)
class RestrictionClassAssignment:
    id: int
    users: list[str]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RestrictionClassAssignment":
        return cls(id=int(raw["id"]), users=_string_list(raw.get("users", [])))

    def as_dict(self) -> dict:
        return {"id": self.id, "users": self.users}


@dataclass(frozen=True)
class DataParameters:
    process_method: str | None = None
    process_agency: str | None = None
    last_checked_date: str | None = None
    geoid_used: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "DataParameters":
        raw = raw or {}
        return cls(
            process_method=raw.get("processMethod"),
            process_agency=raw.get("processAgency"),
            last_checked_date=raw.get("lastCheckedDate"),
            geoid_used=raw.get("geoidUsed"),
        )

    def as_dict(self) -> dict:
        return {
            key: value
            for key, value in {
                "processMethod": self.process_method,
                "processAgency": self.process_agency,
                "lastCheckedDate": self.last_checked_date,
                "geoidUsed": self.geoid_used,
            }.items()
            if value is not None
        }


@dataclass(frozen=True)
class IntersectionGeometry:
    id: IntersectionReferenceID
    revision: int
    ref_point: Position3D
    lane_set: list[GenericLane]
    name: str = ""
    lane_width: float | None = None
    speed_limits: list[SpeedLimit] = field(default_factory=list)
    signal_head_locations: list[SignalHeadLocation] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "IntersectionGeometry":
        return cls(
            name=str(raw.get("name", "")),
            id=IntersectionReferenceID.from_dict(raw["id"]),
            revision=int(raw["revision"]),
            ref_point=Position3D.from_dict(raw["refPoint"]),
            lane_width=(
                float(raw["laneWidth"]) if raw.get("laneWidth") is not None else None
            ),
            speed_limits=[
                SpeedLimit.from_dict(value) for value in raw.get("speedLimits", [])
            ],
            lane_set=[GenericLane.from_dict(value) for value in raw.get("laneSet", [])],
            signal_head_locations=[
                SignalHeadLocation.from_dict(value)
                for value in raw.get("signalHeadLocations", [])
            ],
        )

    def as_dict(self) -> dict:
        value = {
            "id": self.id.as_dict(),
            "revision": self.revision,
            "refPoint": self.ref_point.as_dict(),
            "laneSet": [lane.as_dict() for lane in self.lane_set],
        }
        if self.name:
            value["name"] = self.name
        if self.lane_width is not None:
            value["laneWidth"] = self.lane_width
        if self.speed_limits:
            value["speedLimits"] = [speed.as_dict() for speed in self.speed_limits]
        if self.signal_head_locations:
            value["signalHeadLocations"] = [
                location.as_dict() for location in self.signal_head_locations
            ]
        return value


@dataclass(frozen=True)
class MapData:
    msg_issue_revision: int
    intersections: list[IntersectionGeometry]
    timestamp: int | None = None
    layer_type: str | None = None
    layer_id: int | None = None
    data_parameters: DataParameters | None = None
    restriction_list: list[RestrictionClassAssignment] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "MapData":
        return cls(
            timestamp=int(raw["timestamp"]) if raw.get("timestamp") is not None else None,
            msg_issue_revision=int(raw.get("msgIssueRevision", 1)),
            layer_type=raw.get("layerType"),
            layer_id=int(raw["layerID"]) if raw.get("layerID") is not None else None,
            intersections=[
                IntersectionGeometry.from_dict(value)
                for value in raw.get("intersections", [])
            ],
            data_parameters=(
                DataParameters.from_dict(raw.get("dataParameters"))
                if raw.get("dataParameters") is not None
                else None
            ),
            restriction_list=[
                RestrictionClassAssignment.from_dict(value)
                for value in raw.get("restrictionList", [])
            ],
        )

    def as_dict(self) -> dict:
        value = {
            "msgIssueRevision": self.msg_issue_revision,
            "intersections": [
                intersection.as_dict() for intersection in self.intersections
            ],
        }
        if self.timestamp is not None:
            value["timestamp"] = self.timestamp
        if self.layer_type is not None:
            value["layerType"] = self.layer_type
        if self.layer_id is not None:
            value["layerID"] = self.layer_id
        if self.data_parameters is not None:
            value["dataParameters"] = self.data_parameters.as_dict()
        if self.restriction_list:
            value["restrictionList"] = [
                restriction.as_dict() for restriction in self.restriction_list
            ]
        return value


@dataclass(frozen=True)
class SiteModel:
    map_data: MapData
    source_notes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SiteModel":
        if "mapData" in raw:
            return cls(
                map_data=MapData.from_dict(raw["mapData"]),
                source_notes=_string_list(raw.get("sourceNotes", raw.get("source_notes", []))),
            )

        # Migration path for early MVP examples.
        legacy_intersection = {
            "name": raw.get("name", raw["site_id"]),
            "id": {"region": 826, "id": raw["site_id"]},
            "revision": raw.get("revision", 1),
            "refPoint": raw["ref_point"],
            "laneWidth": raw.get("lane_width_m", 3.25),
            "laneSet": raw.get("lanes", []),
        }
        return cls(
            map_data=MapData.from_dict(
                {
                    "msgIssueRevision": raw.get("revision", 1),
                    "intersections": [legacy_intersection],
                }
            ),
            source_notes=_string_list(raw.get("source_notes", [])),
        )

    @property
    def primary_intersection(self) -> IntersectionGeometry:
        if not self.map_data.intersections:
            raise ValueError("SiteModel contains no intersections")
        return self.map_data.intersections[0]

    @property
    def site_id(self) -> str:
        return str(self.primary_intersection.id.id)

    def as_dict(self) -> dict:
        value = {"mapData": self.map_data.as_dict()}
        if self.source_notes:
            value["sourceNotes"] = self.source_notes
        return value
