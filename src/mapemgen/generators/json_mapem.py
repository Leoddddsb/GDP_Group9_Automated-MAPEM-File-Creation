from __future__ import annotations

from mapemgen.models import SiteModel


def generate_json_mapem(site: SiteModel) -> dict:
    return {
        "mapData": {
            "msgIssueRevision": site.revision,
            "intersections": [
                {
                    "name": site.name,
                    "id": {"region": 826, "id": site.site_id},
                    "revision": site.revision,
                    "refPoint": {
                        "lat": site.ref_point[0],
                        "lon": site.ref_point[1],
                    },
                    "laneWidth": site.lane_width_m,
                    "laneSet": [
                        {
                            "laneID": lane.lane_id,
                            "name": lane.name,
                            "laneType": lane.lane_type,
                            "approachID": lane.approach_id,
                            "direction": lane.direction,
                            "maneuvers": lane.maneuvers,
                            "nodeList": [
                                {"x": x, "y": y} for x, y in lane.centerline
                            ],
                            "connectsTo": [
                                {
                                    "connectingLane": target,
                                    "signalGroup": lane.signal_group,
                                }
                                for target in lane.connects_to
                            ],
                        }
                        for lane in site.lanes
                    ],
                    "signalGroups": [
                        {
                            "signalGroupID": group.signal_group_id,
                            "phaseLabel": group.phase_label,
                            "description": group.description,
                            "controlledLanes": group.controlled_lanes,
                        }
                        for group in site.signal_groups
                    ],
                }
            ],
        },
        "sourceNotes": site.source_notes,
    }

