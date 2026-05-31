# MAPEM Element Source Priority Overview

## Mandatory Paths

```text
header.protocolVersion
header.messageID
header.stationID
MapData.msgIssueRevision
MapData.intersections[].id.region
MapData.intersections[].id.id
MapData.intersections[].revision
MapData.intersections[].refPoint.lat
MapData.intersections[].refPoint.long
MapData.intersections[].laneSet[]
MapData.intersections[].laneSet[].laneID
MapData.intersections[].laneSet[].ingressApproach
MapData.intersections[].laneSet[].egressApproach
MapData.intersections[].laneSet[].laneAttributes.directionalUse
MapData.intersections[].laneSet[].laneAttributes.sharedWith
MapData.intersections[].laneSet[].laneAttributes.laneType
MapData.intersections[].laneSet[].nodeList.nodes[].delta
MapData.intersections[].laneSet[].connectsTo[].connectingLane.lane
MapData.intersections[].laneSet[].connectsTo[].signalGroup
```

## Element Dictionary Overview

| MAPEM element | Population mode | Required fact type(s) | P1 source | P2 source | P3 / fallback | Review trigger | Validation rule |
|---|---|---|---|---|---|---|---|
| `header.protocolVersion` | `constant` | - | System constant: MAPEM profile constant | - | - | `protocol_version_constant_missing`; `protocol_version_constant_conflicts_with_profile` | Must match required protocol constant |
| `header.messageID` | `constant` | - | System constant: MAPEM message type constant | - | - | `message_id_constant_missing`; `message_id_does_not_identify_mapem` | Must identify MAPEM message |
| `header.stationID` | `client_configured` | `station_id` | Project/client deployment configuration | Explicit station ID in UTC/config/spec document | Explicit station ID in drawing title block or metadata | `missing_station_id`; `conflicting_station_ids`; `station_id_only_available_from_filename` | Must be populated and confirmed by explicit source or review |
| `MapData.msgIssueRevision` | `project_managed` | `mapem_message_revision` | MAPEM lifecycle record | - | - | `msg_issue_revision_not_initialised`; `document_issue_number_used_as_msg_issue_revision` | Must not be copied from ordinary document issue |
| `MapData.intersections[].id.region` | `client_configured` | `road_regulator_id` | Project/client authority identifier mapping | Explicit regulator ID in official site configuration | Explicit regulator ID in drawing title block | `missing_road_regulator_id`; `authority_identifier_unconfirmed`; `conflicting_road_regulator_ids` | Region must be populated and valid for deployment domain |
| `MapData.intersections[].id.id` | `directly_extracted` | `official_intersection_id`; `scn`; `orn` | Site configuration: UTC/config/spec document | Drawing title block confirmation | Filename or package metadata with review | `missing_official_intersection_id`; `conflicting_official_intersection_ids`; `only_filename_identifier_available` | Must identify one intersection and be unique within road-regulator domain |
| `MapData.intersections[].revision` | `project_managed` | `topology_revision` | MAPEM lifecycle or topology-change record | Client confirmation | - | `topology_revision_not_initialised`; `document_issue_mistaken_as_topology_revision`; `topology_change_without_revision_update` | Update only for topology change and align with SPATEM revision when paired |
| `MapData.intersections[].refPoint.lat` | `geometry_derived` | `junction_centre_candidate`; `coordinate_reference_system_evidence`; `georeference_status`; `reference_point_latitude` | CAD drawing if georeferenced or CRS known | Ordnance Survey / authoritative GIS if supplied | OpenStreetMap fallback or cross-check | `cad_coordinate_system_unknown`; `candidate_reference_points_conflict`; `reference_point_outside_expected_junction_area`; `only_review_alignment_available` | Latitude must be present, valid, and near conflict-area centre |
| `MapData.intersections[].refPoint.long` | `geometry_derived` | `junction_centre_candidate`; `coordinate_reference_system_evidence`; `georeference_status`; `reference_point_longitude` | CAD drawing if georeferenced or CRS known | Ordnance Survey / authoritative GIS if supplied | OpenStreetMap fallback or cross-check | `cad_coordinate_system_unknown`; `candidate_reference_points_conflict`; `reference_point_outside_expected_junction_area`; `only_review_alignment_available` | Longitude must be present, valid, and near conflict-area centre |
| `MapData.intersections[].laneSet[]` | `geometry_derived` | `controlled_lane_candidate`; `crosswalk_lane_candidate`; `lane_grouping_candidate` | CAD drawing with vector lane geometry | Annotated drawing / embedded layout support | - | `controlled_lane_not_geometrically_resolved`; `lane_set_incomplete_or_ambiguous`; `crosswalk_lane_candidate_uncertain` | All signal-controlled lanes must be included |
| `MapData.intersections[].laneSet[].laneID` | `system_generated` | `lane_candidate` | Stable system lane-ID allocation after lane extraction | - | - | `duplicate_lane_ids`; `unstable_lane_id_ordering`; `lane_candidate_missing_required_identity` | Lane ID must be unique within the intersection |
| `MapData.intersections[].laneSet[].ingressApproach` | `geometry_derived` | `lane_direction_candidate`; `stop_line_candidate`; `road_arm_candidate` | CAD drawing with lane direction and stop-line geometry | Annotated drawing / embedded layout | MOVA schematic or signal spec as semantic support | `ingress_direction_uncertain`; `stop_line_not_identified`; `road_arm_assignment_conflict` | Must be consistent with lane direction and not conflict with egress approach |
| `MapData.intersections[].laneSet[].egressApproach` | `geometry_derived` | `lane_direction_candidate`; `exit_lane_candidate`; `road_arm_candidate` | CAD drawing with exit-lane geometry | Annotated drawing / embedded layout | MOVA schematic or signal spec as semantic support | `egress_direction_uncertain`; `exit_lane_not_identified`; `road_arm_assignment_conflict` | Must be consistent with lane direction and not conflict with ingress approach |
| `MapData.intersections[].laneSet[].laneAttributes.directionalUse` | `geometry_derived` | `classified_lane_direction`; `approach_assignment` | Derived from resolved approach assignment | CAD / annotated drawing confirms lane direction | - | `approach_unresolved`; `directional_use_sources_conflict`; `lane_direction_confidence_too_low` | Correct directional-use bits must match ingress or egress role |
| `MapData.intersections[].laneSet[].laneAttributes.sharedWith` | `evidence_fused` | `shared_use_candidate`; `lane_marking_evidence`; `pedestrian_or_cycle_use_candidate` | CAD / annotated drawing markings | Configuration notes | - | `shared_use_unclear`; `shared_with_sources_conflict`; `drawing_markings_not_legible` | Mandatory sharedWith value must be populated and consistent with laneType |
| `MapData.intersections[].laneSet[].laneAttributes.laneType` | `evidence_fused` | `lane_type_candidate`; `crossing_candidate`; `phase_type`; `pedestrian_phase_candidate` | CAD / annotated drawing geometry and markings | Site configuration evidence | - | `lane_type_sources_conflict`; `lane_type_unclassified`; `crossing_candidate_without_matching_control_evidence` | Mandatory lane type must be selected and consistent with other lane attributes |
| `MapData.intersections[].laneSet[].nodeList.nodes[].delta` | `geometry_derived` | `lane_centreline_nodes`; `reference_point`; `coordinate_reference_system_evidence` | CAD drawing with vector lane geometry | LiDAR / topographic survey if later supplied | Digitised drawing fallback | `lane_centreline_broken`; `geometry_not_georeferenced`; `node_sequence_direction_uncertain`; `digitised_drawing_used_as_only_geometry_source` | Nodes must follow lane centreline and be encoded relative to refPoint |
| `MapData.intersections[].laneSet[].connectsTo[].connectingLane.lane` | `evidence_fused` | `lane_connection_candidate`; `movement_direction_candidate`; `target_lane_candidate` | CAD topology | Annotated drawing / embedded layout confirms movement | MOVA schematic or signal specification as movement support | `multiple_target_lanes_plausible`; `no_target_lane_resolved`; `movement_direction_sources_conflict` | Target lane must exist in the laneSet |
| `MapData.intersections[].laneSet[].connectsTo[].signalGroup` | `evidence_fused` | `phase_label`; `stage_phase_relationship`; `movement_phase_mapping`; `lane_connection_candidate` | Site configuration: controller config / UTC form / signal spec | MOVA schematic for movement-to-phase support | Annotated drawing for physical movement confirmation only | `phase_cannot_be_mapped_to_lane_connection`; `conflicting_signal_group_assignment`; `movement_phase_mapping_missing`; `controlled_connection_without_signal_group` | Every signal-controlled connection must have a signal-group assignment |

## Produced Artefacts

- Machine-readable dictionary: `mapem_element_source_priority_dictionary.yaml`
- Human-readable overview: `mapem_element_source_priority_overview.md`
