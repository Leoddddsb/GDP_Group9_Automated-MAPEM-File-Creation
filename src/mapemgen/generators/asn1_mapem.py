from __future__ import annotations

from mapemgen.models import GenericLane, IntersectionGeometry, SiteModel


def _format_connection(connection) -> str:
    parts = [
        "connectingLane { "
        f"lane {connection.connecting_lane.lane}"
        + (
            f", maneuver {connection.connecting_lane.maneuver}"
            if connection.connecting_lane.maneuver
            else ""
        )
        + " }"
    ]
    if connection.signal_group is not None:
        parts.append(f"signalGroup {connection.signal_group}")
    if connection.connection_id is not None:
        parts.append(f"connectionID {connection.connection_id}")
    return "{ " + ", ".join(parts) + " }"


def _format_lane(lane: GenericLane) -> str:
    nodes = ", ".join(
        f"{{ x {node.x}, y {node.y} }}" for node in lane.node_list.nodes
    )
    connections = ", ".join(
        _format_connection(connection) for connection in lane.connects_to
    )
    approach_lines = []
    if lane.ingress_approach is not None:
        approach_lines.append(f"            ingressApproach {lane.ingress_approach},")
    if lane.egress_approach is not None:
        approach_lines.append(f"            egressApproach {lane.egress_approach},")
    approaches = "\n".join(approach_lines)
    if approaches:
        approaches += "\n"

    return (
        "          {\n"
        f"            laneID {lane.lane_id},\n"
        f"            name \"{lane.name}\",\n"
        f"{approaches}"
        "            laneAttributes {\n"
        f"              directionalUse {lane.lane_attributes.directional_use},\n"
        f"              laneType {lane.lane_attributes.lane_type}\n"
        "            },\n"
        f"            maneuvers {{ {', '.join(lane.maneuvers)} }},\n"
        f"            nodeList {{ nodes {{ {nodes} }} }},\n"
        f"            connectsTo {{ {connections} }}\n"
        "          }"
    )


def _format_intersection(intersection: IntersectionGeometry) -> str:
    lanes = ",\n".join(_format_lane(lane) for lane in intersection.lane_set)
    lane_width = (
        f"      laneWidth {intersection.lane_width},\n"
        if intersection.lane_width is not None
        else ""
    )
    return (
        "    {\n"
        f"      name \"{intersection.name}\",\n"
        f"      id {{ region {intersection.id.region}, id \"{intersection.id.id}\" }},\n"
        f"      revision {intersection.revision},\n"
        "      refPoint { "
        f"lat {intersection.ref_point.lat}, lon {intersection.ref_point.lon}"
        " },\n"
        f"{lane_width}"
        "      laneSet {\n"
        f"{lanes}\n"
        "      }\n"
        "    }"
    )


def generate_asn1_mapem(site: SiteModel) -> str:
    intersections = ",\n".join(
        _format_intersection(intersection)
        for intersection in site.map_data.intersections
    )
    return (
        "MapData ::= {\n"
        f"  msgIssueRevision {site.map_data.msg_issue_revision},\n"
        "  intersections {\n"
        f"{intersections}\n"
        "  }\n"
        "}\n"
    )
