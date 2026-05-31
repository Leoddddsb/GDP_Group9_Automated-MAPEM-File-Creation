# MAPEM Image Elements Source Priority Overview

## Scope

This overview applies the full element-centred dictionary process to the
MAPEM elements visible in the supplied image only.

The image shows `intersections[]` containing `IntersectionGeometry`. The
normalised paths below treat `IntersectionGeometry` as the object type of each
`intersections[]` item, so the dictionary path is written as
`map.intersections[].id.region`.

## Step 1 - Mandatory paths read from image

```text
header.protocolVersion
header.messageID
header.stationID
map.msgIssueRevision
map.intersections[].id.region
map.intersections[].id.id
map.intersections[].revision
map.intersections[].refPoint.lat
map.intersections[].refPoint.long
```

## Step 2 to Step 7 - Element dictionary overview

| MAPEM element | Population mode | Required fact type(s) | P1 source category / subtype | P2 supporting source | P3 / fallback | Manual-review trigger | Validation rule |
|---|---|---|---|---|---|---|---|
| `header.protocolVersion` | `constant` | N/A | System constant | N/A | N/A | `protocol_version_constant_missing`; `protocol_version_constant_conflicts_with_profile` | Must match required protocol constant |
| `header.messageID` | `constant` | N/A | System constant | N/A | N/A | `message_id_constant_missing`; `message_id_does_not_identify_mapem` | Must identify MAPEM message |
| `header.stationID` | `client_configured` | `station_id` | Site configuration documents only if explicit | Drawing title block / metadata only if explicit | Manual review | `missing_station_id`; `conflicting_station_ids`; `station_id_only_available_from_filename`; `station_id_not_available_from_remaining_source_categories` | Must be populated and confirmed by explicit source or manual review |
| `map.msgIssueRevision` | `project_managed` | `mapem_message_revision` | N/A - managed internally by lifecycle record | N/A | Manual review | `msg_issue_revision_not_initialised`; `document_issue_number_used_as_msg_issue_revision` | Must not be copied from ordinary document issue |
| `map.intersections[].id.region` | `client_configured` | `road_regulator_id` | Official site configuration if explicit | Drawing title block only if explicit | Manual review | `missing_road_regulator_id`; `authority_identifier_unconfirmed`; `conflicting_road_regulator_ids`; `road_regulator_id_not_available_from_remaining_source_categories` | Region must be populated and valid for deployment domain |
| `map.intersections[].id.id` | `directly_extracted` | `official_intersection_id`; `scn`; `orn` | Site configuration: UTC/config/spec document | Drawing title block confirmation | Filename or package metadata with review | `missing_official_intersection_id`; `conflicting_official_intersection_ids`; `only_filename_identifier_available` | Must identify one intersection and be unique within road-regulator domain |
| `map.intersections[].revision` | `project_managed` | `topology_revision` | N/A - managed internally by lifecycle record | N/A | Manual review | `topology_revision_not_initialised`; `document_issue_mistaken_as_topology_revision`; `topology_change_without_revision_update` | Update only for topology change; align with SPATEM revision when paired |
| `map.intersections[].refPoint.lat` | `geometry_derived` | `junction_centre_candidate`; `coordinate_reference_system_evidence`; `georeference_status`; `reference_point_latitude` | CAD drawing if georeferenced or CRS known | Authoritative GIS / Ordnance Survey if supplied | OSM fallback or manual alignment | `cad_coordinate_system_unknown`; `candidate_reference_points_conflict`; `reference_point_outside_expected_junction_area`; `only_manual_alignment_available` | Latitude must be present, valid, and near conflict-area centre |
| `map.intersections[].refPoint.long` | `geometry_derived` | `junction_centre_candidate`; `coordinate_reference_system_evidence`; `georeference_status`; `reference_point_longitude` | CAD drawing if georeferenced or CRS known | Authoritative GIS / Ordnance Survey if supplied | OSM fallback or manual alignment | `cad_coordinate_system_unknown`; `candidate_reference_points_conflict`; `reference_point_outside_expected_junction_area`; `only_manual_alignment_available` | Longitude must be present, valid, and near conflict-area centre |

## Step 8 - Produced artefacts

- Machine-readable dictionary: `mapem_image_elements_dictionary.yaml`
- Human-readable overview: `mapem_image_elements_overview.md`
