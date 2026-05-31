# MAPEM Mandatory Element-Source Priority Dictionary

_Integrated human-readable overview for the mandatory MVP MAPEM elements._

---

## 1. Overview

This dictionary defines the general rules for populating the mandatory MVP MAPEM
elements. It is an element-centred configuration artefact, not a site-specific
evidence table. It does not contain final MAPEM values for any individual junction.

For each element, the dictionary identifies:

1. how the value is populated;
2. which intermediate facts are required;
3. which source category and subtype should be used first;
4. which sources can support or replace the preferred source;
5. when manual review is required;
6. which validation rule should be applied; and
7. why the rule is appropriate.

## 2. Table columns

| Column | Meaning |
|---|---|
| `MAPEM mandatory element` | Normalised MAPEM field path handled by the MVP. |
| `Population mode` | How the final value is obtained: constant, configured, extracted, derived, generated, or fused. |
| `Required fact type(s)` | Intermediate facts required before the MAPEM field can be populated. |
| `P1 source category / subtype` | First-choice source when element-specific conditions are satisfied. |
| `P2 supporting source` | Secondary or corroborating source. |
| `P3 / fallback` | Lower-priority fallback or manual decision path. |
| `Manual-review trigger` | Condition where automatic population should stop and request review. |
| `Validation rule` | Structural or semantic rule applied after population. |
| `Short rationale / notes` | Concise explanation of the element-centred decision. |

## 3. Scope and path convention

The integrated dictionary uses one normalised hierarchy:

```text
header
map
└── intersections[]
    ├── id
    ├── revision
    ├── refPoint
    └── laneSet[]
        ├── laneID
        ├── ingressApproach
        ├── egressApproach
        ├── laneAttributes
        ├── nodeList
        │   └── nodes[]
        │       └── delta
        └── connectsTo[]
            ├── connectingLane
            │   └── lane
            └── signalGroup
```

The three source dictionaries used mixed `map` and `mapData` prefixes and mixed
`laneSet` and `laneSet[]` notation. This overview standardises them to
`map.intersections[].laneSet[]...`.

## 4. Complete mandatory element dictionary

| MAPEM mandatory element | Population mode | Required fact type(s) | P1 source category / subtype | P2 supporting source | P3 / fallback | Manual-review trigger | Validation rule | Short rationale / notes |
|---|---|---|---|---|---|---|---|---|
| `header.protocolVersion` | `constant` | N/A | `system_configuration -> mapem_profile_constant` | N/A | N/A | Constant missing; constant conflicts with profile | Must match the required MAPEM profile constant | System constant; do not infer from site files. |
| `header.messageID` | `constant` | N/A | `system_configuration -> mapem_message_id_constant` | N/A | N/A | Constant missing; value does not identify MAPEM | Must identify a MAPEM message | System constant; do not infer from site files. |
| `header.stationID` | `client_configured` | `station_id` | `project_or_client_configuration -> explicit_station_id_configuration` | Explicit station ID in site configuration document | Manual client confirmation | Missing or conflicting station IDs; only filename-derived candidate available | Must be populated and explicitly sourced or manually confirmed | Deployment identifier, not a site code inferred from filenames. |
| `map.msgIssueRevision` | `project_managed` | `mapem_message_revision` | `project_or_client_configuration -> mapem_lifecycle_record` | N/A | Manual lifecycle initialisation | Revision not initialised; ordinary document issue used as MAPEM revision | Must be initialised and managed by the MAPEM lifecycle | Internal message lifecycle value. |
| `map.intersections[].id.region` | `client_configured` | `road_regulator_id` | `project_or_client_configuration -> road_regulator_assignment` | Explicit authority identifier in official site configuration | Manual client confirmation | Missing, conflicting, or unconfirmed road-regulator ID | Must be populated and valid for deployment domain | Identifies the road-regulator domain. |
| `map.intersections[].id.id` | `directly_extracted` | `official_intersection_id`; `scn`; `orn` | `site_configuration_information -> utc_form_docx / controller_configuration_pdf / signal_specification_pdf` | `site_plans_and_cad_files -> drawing_title_block` | Filename or package metadata with manual review | Missing or conflicting official IDs; only filename identifier available | Must identify one intersection and be unique within road-regulator domain | Prefer an explicit official site identifier. |
| `map.intersections[].revision` | `project_managed` | `topology_revision` | `project_or_client_configuration -> topology_lifecycle_record` | N/A | Manual topology revision confirmation | Revision not initialised; document issue mistaken as topology revision; topology changed without update | Must update for topology changes and align with paired SPATEM revision where applicable | Internal topology lifecycle value. |
| `map.intersections[].refPoint.lat` | `geometry_derived` | `junction_centre_candidate`; `coordinate_reference_system_evidence`; `georeference_status`; `reference_point_latitude` | `site_plans_and_cad_files -> cad_drawing`, only when georeferenced or CRS is known | `gis_data -> ordnance_survey_or_authoritative_gis` | `gis_data -> open_street_map`, or manually aligned drawing PDF | CAD CRS unknown; candidates conflict; point outside expected junction area; only manual alignment available | Latitude must be valid WGS84 and near conflict-area centre | One coordinate of the geometry anchor. |
| `map.intersections[].refPoint.long` | `geometry_derived` | `junction_centre_candidate`; `coordinate_reference_system_evidence`; `georeference_status`; `reference_point_longitude` | `site_plans_and_cad_files -> cad_drawing`, only when georeferenced or CRS is known | `gis_data -> ordnance_survey_or_authoritative_gis` | `gis_data -> open_street_map`, or manually aligned drawing PDF | CAD CRS unknown; candidates conflict; point outside expected junction area; only manual alignment available | Longitude must be valid WGS84 and near conflict-area centre | Must be reviewed with latitude as one refPoint pair. |
| `map.intersections[].laneSet[]` | `geometry_derived` | `controlled_lane_candidate`; `crosswalk_lane_candidate`; `lane_candidate`; `signal_controlled_lane_evidence` | `site_plans_and_cad_files -> cad_drawing` | `site_plans_and_cad_files -> annotated_drawing_pdf / embedded_layout_in_specification_pdf` | Manual geometry review | Controlled lanes unresolved; geometry sources disagree; roundabout internal lanes ambiguous | Include all fused signal-controlled lanes individually | Geometry delineates candidates; configuration evidence confirms controlled scope. |
| `map.intersections[].laneSet[].laneID` | `system_generated` | `lane_candidate`; `stable_lane_ordering_rule` | `project_or_client_configuration -> stable_lane_ordering_rule` | CAD geometry supports stable ordering, not final IDs | Manual ordering confirmation | Ordering tie; unresolved geometry; lane candidate set changed after generation | Every lane must have a unique deterministic ID within the intersection | Generated identifier, not a CAD label. |
| `map.intersections[].laneSet[].ingressApproach` | `geometry_derived` | `lane_direction_candidate`; `stop_line_candidate`; `road_arm_candidate`; `approach_group_candidate` | `site_plans_and_cad_files -> cad_drawing` | Annotated drawing or embedded layout; MOVA/UTC support when mapped clearly | Manual approach assignment | Inbound direction uncertain; stop line conflicts with direction; arm grouping ambiguous | Each ingress lane must have a consistent ingress approach matching directional use | Group inbound lanes by arm and travel direction. |
| `map.intersections[].laneSet[].egressApproach` | `geometry_derived` | `lane_direction_candidate`; `stop_line_candidate`; `road_arm_candidate`; `approach_group_candidate` | `site_plans_and_cad_files -> cad_drawing` | Annotated drawing or embedded layout; MOVA/UTC support when mapped clearly | Manual approach assignment | Outbound direction uncertain; exit geometry conflicts with direction; arm grouping ambiguous | Each egress lane must have a consistent egress approach matching directional use | Group outbound lanes by arm and travel direction. |
| `map.intersections[].laneSet[].laneAttributes.directionalUse` | `geometry_derived` | `classified_lane_direction`; `approach_assignment`; `stop_line_candidate` | `site_plans_and_cad_files -> cad_drawing` | `site_plans_and_cad_files -> annotated_drawing_pdf` | Manual direction confirmation | Approach unresolved; geometry, stop line, and schematic disagree | Assert ingressPath for ingress, egressPath for egress, and both for reviewed bidirectional lanes | Derived after approach assignment. |
| `map.intersections[].laneSet[].laneAttributes.sharedWith` | `evidence_fused` | `shared_use_candidate`; `bus_lane_candidate`; `cycle_lane_candidate`; `pedestrian_shared_use_candidate`; `road_marking_or_sign_note` | `site_plans_and_cad_files -> cad_drawing / annotated_drawing_pdf` | `site_configuration_information -> signal_specification_pdf / controller_configuration_pdf / mova_schematic_docx / utc_form_docx` | Manual shared-use confirmation | Shared use unclear; sources conflict; primary lane user unclear | Populate mandatory bit string and retain provenance for asserted bits | Coordinate sharing bits with the primary lane type. |
| `map.intersections[].laneSet[].laneAttributes.laneType` | `evidence_fused` | `lane_type_candidate`; `vehicle_lane_candidate`; `crossing_candidate`; `pedestrian_phase_candidate`; `cycle_lane_candidate`; `bus_lane_candidate` | `site_plans_and_cad_files -> cad_drawing / annotated_drawing_pdf` | `site_configuration_information -> signal_specification_pdf / controller_configuration_pdf / mova_schematic_docx / utc_form_docx` | Manual lane-type classification | Geometry and control evidence disagree; special facility unclear; evidence missing | Select a supported mandatory lane type consistent with sharedWith | Geometry provides visible type; control evidence confirms classifications. |
| `map.intersections[].laneSet[].nodeList.nodes[].delta` | `geometry_derived` | `lane_geometry_candidate`; `lane_centreline_nodes`; `upstream_refPoint`; `coordinate_reference_system_evidence`; `georeference_status`; `node_position_offsets` | `site_plans_and_cad_files -> cad_drawing` | `road_condition_and_lidar_surveys -> lidar / topographic_survey`, if supplied | `site_plans_and_cad_files -> annotated_drawing_pdf` manual digitisation; GIS for approximate support only | CAD CRS unknown; centreline broken; geometry ambiguous; refPoint uncertain; PDF digitisation required; offset out of range | Nodes must follow lane centreline, use valid relative offsets, and remain consistent with lane direction | Represents lane centreline geometry relative to refPoint. |
| `map.intersections[].laneSet[].connectsTo[].connectingLane.lane` | `evidence_fused` | `lane_candidate`; `lane_id_assignment`; `lane_connection_candidate`; `target_lane_candidate`; `movement_direction_candidate`; `lane_direction_candidate`; `stop_line_candidate` | `site_plans_and_cad_files -> cad_drawing` | `site_plans_and_cad_files -> annotated_drawing_pdf` | `site_configuration_information -> mova_schematic_docx / signal_specification_pdf`; GIS approximate support only | Multiple targets plausible; target missing; internal connection uncertain; direction uncertain; drawing conflicts with geometry | Target lane ID must exist and connection must follow valid topology | Value is the downstream laneID, not a road name or phase label. |
| `map.intersections[].laneSet[].connectsTo[].signalGroup` | `evidence_fused` | `phase_label`; `phase_type`; `stage_phase_relationship`; `movement_phase_mapping`; `lane_connection_candidate`; `target_lane_candidate`; `signal_group_assignment_candidate`; `control_stream_candidate`; `conflict_matrix_evidence` | Control: `site_configuration_information -> signal_control_configuration_document`; physical connection: `site_plans_and_cad_files -> cad_drawing` | Control: `utc_form_docx`; physical connection: `annotated_drawing_pdf` | Control: `mova_schematic_docx`; physical support: GIS road-arm approximation only | Missing control or physical evidence; phase cannot map to lane connection; assignments conflict; dummy/pedestrian phase confusion; multi-stream ambiguity | Every controlled connection needs a valid signal group consistent with stages, phases, movement, and stream | Requires both control semantics and resolved physical connection evidence. |

