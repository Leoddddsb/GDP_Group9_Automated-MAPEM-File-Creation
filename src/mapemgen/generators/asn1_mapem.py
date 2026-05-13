from __future__ import annotations

from mapemgen.models import SiteModel


def generate_asn1_mapem(site: SiteModel) -> str:
    lane_blocks = []
    for lane in site.lanes:
        nodes = ", ".join(f"{{ x {x}, y {y} }}" for x, y in lane.centerline)
        connects = ", ".join(str(target) for target in lane.connects_to)
        signal_group = "NULL" if lane.signal_group is None else str(lane.signal_group)
        lane_blocks.append(
            "          {\n"
            f"            laneID {lane.lane_id},\n"
            f"            name \"{lane.name}\",\n"
            f"            approachID {lane.approach_id},\n"
            f"            laneType \"{lane.lane_type}\",\n"
            f"            nodeList {{ {nodes} }},\n"
            f"            connectsTo {{ {connects} }},\n"
            f"            signalGroup {signal_group}\n"
            "          }"
        )

    lanes = ",\n".join(lane_blocks)
    return (
        "MapData ::= {\n"
        f"  msgIssueRevision {site.revision},\n"
        "  intersections {\n"
        "    {\n"
        f"      name \"{site.name}\",\n"
        f"      id {{ region 826, id \"{site.site_id}\" }},\n"
        f"      revision {site.revision},\n"
        f"      refPoint {{ lat {site.ref_point[0]}, lon {site.ref_point[1]} }},\n"
        f"      laneWidth {site.lane_width_m},\n"
        "      laneSet {\n"
        f"{lanes}\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )

