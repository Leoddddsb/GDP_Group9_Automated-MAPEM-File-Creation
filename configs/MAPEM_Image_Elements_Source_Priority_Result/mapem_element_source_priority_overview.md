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

## Produced Artefacts

- Machine-readable dictionary: `mapem_element_source_priority_dictionary.yaml`
- Human-readable overview: `mapem_element_source_priority_overview.md`
