# MAPEM Dictionary Section: Lane Geometry and Connections

## 1. Overview: Minimum Dictionary Table to Complete

This section provides the human-readable overview table for the part of the MAPEM element-source priority dictionary covering lane geometry and lane-to-lane connections. Before writing the full YAML configuration, this table should be completed and agreed by the group.

This table is not a site-specific evidence matrix. It does not record final values for a particular site such as `337L` or `5040`. Instead, it defines the general rule for how each mandatory MAPEM element in this section should be populated across different site packages.

For each MAPEM element, the table identifies:

1. how the value is populated;
2. what intermediate facts are required;
3. which source category/subtype should be used first;
4. which sources can support or validate the result;
5. when manual review is required; and
6. what validation rule should be applied.

After this overview table is agreed, the same logic can be converted into a machine-readable YAML configuration used by the prototype for fact extraction, field matching, evidence fusion and validation.

## 2. Table Columns

| Column | Meaning |
|---|---|
| `MAPEM mandatory element` | The MAPEM field path that must be handled in the MVP. |
| `Population mode` | How the final value is obtained: constant, configured, extracted, derived, generated or fused. |
| `Required fact type(s)` | Intermediate facts that need to be extracted before the MAPEM field can be populated. |
| `P1 source category / subtype` | Primary evidence source for this element. |
| `P2 supporting source` | Source that can support or validate the primary evidence. |
| `P3 / fallback` | Lower-confidence source used only if stronger evidence is unavailable. |
| `Manual-review trigger` | Condition where automatic population should stop and ask for review. |
| `Validation rule` | Rule used to check whether the populated value is structurally or semantically acceptable. |

## 3. Scope of This Section

This section covers the MAPEM elements used to describe lane geometry and downstream lane connections:

```text
GenericLane
├── nodeList
│   └── nodes[]
│       └── delta
└── connectsTo[]
    └── Connection
        ├── connectingLane
        │   └── lane
        └── signalGroup
```

These elements are central to representing how a vehicle, cyclist or pedestrian moves through a signalised junction.

- `nodeList.nodes[].delta` describes the geometry of each lane.
- `connectsTo.connectingLane.lane` defines which downstream lane can be reached.
- `connectsTo.signalGroup` identifies the signal group controlling that movement.

In this section:

- `nodeList.nodes[].delta` is treated as a `geometry_derived` element because it is calculated from lane centreline geometry relative to the intersection reference point.
- `connectsTo.connectingLane.lane` is treated as an `evidence_fused` element because the target lane should be inferred from physical lane topology and confirmed against movement evidence where necessary.
- `connectsTo.signalGroup` is treated as an `evidence_fused` element because geometry alone cannot determine the controlling signal group; signal-control documents must be combined with physical lane-connection evidence.

## 4. Minimum Dictionary Table for This Section

| MAPEM mandatory element | Population mode | Required fact type(s) | P1 source category / subtype | P2 supporting source | P3 / fallback | Manual-review trigger | Validation rule |
|---|---|---|---|---|---|---|---|
| `nodeList.nodes[].delta` | `geometry_derived` | `lane_centreline_nodes`; `reference_point`; `coordinate_reference_system_evidence`; `node_position_offsets` | `site_plans_and_cad_files -> cad_drawing` | `road_condition_and_lidar_surveys`, if available | `annotated_drawing_pdf` as digitised fallback; `gis_data` for approximate alignment | CAD CRS unknown; lane centreline broken; geometry ambiguous; offset out of valid range | Nodes must follow lane centreline; node offsets must be relative to `refPoint`; values must be valid `NodeXY.delta` |
| `connectsTo.connectingLane.lane` | `evidence_fused` | `lane_candidate`; `lane_id_assignment`; `lane_connection_candidate`; `target_lane_candidate`; `movement_direction_candidate` | `site_plans_and_cad_files -> cad_drawing` | `annotated_drawing_pdf` for movement arrows/layout interpretation | `mova_schematic_docx` or `signal_specification_pdf` for movement support | Multiple target lanes plausible; target lane missing; roundabout/internal connection uncertain; lane direction unclear | Target lane ID must exist; connection must follow lane direction and be physically plausible |
| `connectsTo.signalGroup` | `evidence_fused` | `phase_label`; `phase_type`; `stage_phase_relationship`; `movement_phase_mapping`; `lane_connection_candidate`; `signal_group_assignment_candidate` | `site_configuration_information -> controller_configuration_pdf / utc_form_docx / signal_specification_pdf` | `mova_schematic_docx` for movement-phase interpretation | `annotated_drawing_pdf` and `cad_drawing` for physical movement confirmation only | Phase cannot be mapped to lane connection; conflicting signal group assignment; dummy phase mistaken as control phase; multiple streams create ambiguity | Every signal-controlled connection must have a signal group; signal group must match stage-phase relationship and physical movement |

## 5. Element Detail: `nodeList.nodes[].delta`

### Definition

`nodeList.nodes[].delta` describes the lane centreline using a sequence of relative node offsets. Each node is encoded relative to the previous node, while the first node is referenced from the intersection `refPoint`.

In simple terms:

```text
nodeList.nodes[].delta
= the relative positional offsets used to draw the lane path
```

This is different from `dWidth`. `delta` describes the x/y position offset of each node, while `dWidth` describes lane-width variation and is outside the current mandatory MVP scope.

### Population Mode

```text
geometry_derived
```

### Required Intermediate Facts

| Required fact type | Meaning |
|---|---|
| `lane_centreline_nodes` | Candidate centreline points for each lane. |
| `reference_point` | The MAPEM intersection `refPoint` used as the geometry anchor. |
| `coordinate_reference_system_evidence` | Evidence that the CAD/GIS geometry can be converted into a real coordinate system. |
| `lane_geometry_candidate` | Extracted or inferred lane geometry from CAD/drawing. |
| `georeference_status` | Whether the source geometry is georeferenced, manually aligned, or unknown. |
| `node_position_offsets` | Relative x/y offsets that can be encoded as `NodeXY.delta`. |

### Source Priority

| Priority | Source category | Source subtype | Use |
|---|---|---|---|
| `P1` | `site_plans_and_cad_files` | `cad_drawing` | Primary source for lane centreline geometry. |
| `P2` | `road_condition_and_lidar_surveys` | `lidar` / `topographic_survey`, if available | Potential high-resolution geometry validation. |
| `P3` | `site_plans_and_cad_files` | `annotated_drawing_pdf` | Fallback only; may require manual digitisation. |
| `F` | `gis_data` | OSM / Ordnance Survey, if available | Possible approximate alignment or validation. |
| `N/A` | `site_configuration_information` | configuration PDF / UTC form / signal specification | Not expected to provide detailed lane centreline nodes. |

### Logic

The program should first attempt to extract lane geometry from CAD/DWG files. If a lane centreline is explicitly available, it can be used directly. If only lane edges or road markings are available, the centreline may need to be inferred. The resulting geometry must then be converted into MAPEM `NodeXY.delta` values relative to the intersection `refPoint`.

### Manual Review Triggers

| Trigger | Meaning |
|---|---|
| `cad_coordinate_system_unknown` | CAD geometry exists but has no clear CRS or georeference. |
| `lane_centreline_broken` | Extracted lane centreline is incomplete or discontinuous. |
| `lane_geometry_ambiguous` | It is unclear which geometry represents the lane centreline. |
| `refpoint_missing_or_uncertain` | `refPoint` is not available or cannot be linked to the geometry. |
| `pdf_digitisation_required` | Only a drawing PDF exists, so manual digitisation may be required. |
| `node_offset_out_of_range` | A node offset cannot be encoded within the selected NodeXY delta type. |

### Validation Rules

| Rule | Purpose |
|---|---|
| `nodes_must_follow_lane_centreline` | Ensure generated nodes represent the intended lane path. |
| `nodes_must_be_relative_to_refpoint` | Ensure coordinates are encoded correctly in MAPEM. |
| `lane_geometry_must_not_cross_unintended_conflict_area` | Avoid unrealistic or unsafe lane paths. |
| `node_offsets_must_be_valid_NodeXY_values` | Ensure ASN.1-compatible encoding. |
| `geometry_should_be_consistent_with_lane_direction` | Ensure node order follows ingress or egress direction. |

## 6. Element Detail: `connectsTo.connectingLane.lane`

### Definition

`connectsTo.connectingLane.lane` identifies the downstream lane that a given lane connects to. The value is not a road name or a phase label; it is the `laneID` of the target lane.

In simple terms:

```text
connectsTo.connectingLane.lane
= the target laneID that this lane can lead to
```

### Population Mode

```text
evidence_fused
```

It can be partly geometry-derived, but for robustness it should be treated as evidence-fused because lane-connection interpretation may require both physical geometry and movement semantics.

### Required Intermediate Facts

| Required fact type | Meaning |
|---|---|
| `lane_candidate` | Detected lane objects. |
| `lane_id_assignment` | Generated `laneID` for each lane. |
| `lane_connection_candidate` | Candidate connection from one lane to another. |
| `target_lane_candidate` | Candidate downstream lane. |
| `movement_direction_candidate` | Movement type or direction, such as left, straight, right, or roundabout circulation. |
| `lane_direction_candidate` | Whether the lane is ingress, egress, or internal/successive. |
| `stop_line_candidate` | Stop-line evidence supporting the start of an ingress lane. |

### Source Priority

| Priority | Source category | Source subtype | Use |
|---|---|---|---|
| `P1` | `site_plans_and_cad_files` | `cad_drawing` | Primary source for physical lane topology and downstream connections. |
| `P2` | `site_plans_and_cad_files` | `annotated_drawing_pdf` | Supports movement arrows, road layout and connection interpretation. |
| `P3` | `site_configuration_information` | `mova_schematic_docx` / `signal_specification_pdf` | Supports movement interpretation, especially where CAD topology is unclear. |
| `F` | `gis_data` | OSM / Ordnance Survey, if available | Approximate topology support only. |
| `N/A` | `asset_management_tools` | pole/signal asset exports | Not expected to define lane-to-lane connections directly. |

### Logic

The system should first identify all lanes and assign `laneID`s. It should then infer which ingress lanes connect to which egress or internal lanes using CAD geometry and lane direction. For a simple junction, this may be based on lane alignment and turning movement. For a signalised roundabout, internal lanes and circulating movements may require additional interpretation.

### Manual Review Triggers

| Trigger | Meaning |
|---|---|
| `multiple_target_lanes_plausible` | One lane could reasonably connect to more than one downstream lane. |
| `target_lane_missing` | The inferred target lane does not exist in the generated `laneSet`. |
| `roundabout_internal_connection_uncertain` | Internal roundabout movement cannot be confidently resolved. |
| `lane_direction_uncertain` | Ingress/egress direction is unclear. |
| `movement_arrow_conflicts_with_geometry` | Drawing movement arrow and CAD geometry suggest different connections. |
| `connection_crosses_invalid_area` | Connection appears to cross an unrealistic or prohibited path. |

### Validation Rules

| Rule | Purpose |
|---|---|
| `target_lane_id_must_exist` | `connectingLane.lane` must reference a valid generated `laneID`. |
| `ingress_lane_should_connect_to_valid_downstream_lane` | Ensure every ingress lane has a downstream connection. |
| `connection_should_follow_lane_direction` | Avoid reverse or invalid movement connections. |
| `connection_should_be_consistent_with_topology` | Ensure lane connection is physically plausible. |
| `roundabout_connections_should_preserve_circulatory_logic` | Important for signalised roundabout cases. |

## 7. Element Detail: `connectsTo.signalGroup`

### Definition

`connectsTo.signalGroup` identifies the signal group controlling a specific lane connection. It is the key link between MAPEM lane topology and SPATEM signal-state information.

In simple terms:

```text
connectsTo.signalGroup
= the signal group / phase controlling this specific lane movement
```

This element cannot be determined from geometry alone. CAD may show where the lane goes, but the signal group must be derived from signal-control evidence such as phase labels, stage-phase relationships, UTC forms, configuration PDFs, or signal specification documents.

### Population Mode

```text
evidence_fused
```

### Required Intermediate Facts

| Required fact type | Meaning |
|---|---|
| `phase_label` | Signal phase or group label, such as A, B, C. |
| `phase_type` | Whether the phase is traffic, pedestrian, dummy, arrow, etc. |
| `stage_phase_relationship` | Which phases appear in which stages. |
| `movement_phase_mapping` | Which physical movement is associated with which phase. |
| `lane_connection_candidate` | Physical lane connection to be controlled. |
| `signal_group_assignment_candidate` | Candidate signal group for a lane connection. |
| `control_stream_candidate` | Stream information, especially for complex multi-stream junctions. |
| `conflict_matrix_evidence` | Supporting evidence for whether movements conflict. |

### Source Priority

| Priority | Source category | Source subtype | Use |
|---|---|---|---|
| `P1` | `site_configuration_information` | `controller_configuration_pdf` | Primary control evidence for phases, stages and signal operation. |
| `P1` | `site_configuration_information` | `utc_form_docx` | Official site metadata, staging, phasing and SCOOT links. |
| `P1` | `site_configuration_information` | `signal_specification_pdf` | Leeds-style phase, stage, stream and movement evidence. |
| `P2` | `site_configuration_information` | `mova_schematic_docx` | Movement-phase interpretation support. |
| `P3` | `site_plans_and_cad_files` | `annotated_drawing_pdf` | Physical movement and signal-head annotation support. |
| `Supporting only` | `site_plans_and_cad_files` | `cad_drawing` | Confirms physical lane connection, but cannot alone determine signal group. |
| `Future support` | `asset_management_tools` | pole/signal-head asset export, if available | May support signal-head to signal-group validation. |

### Logic

The assignment of `signalGroup` should combine two types of evidence:

```text
1. Signal-control evidence
   -> phase labels, stages, streams, stage-phase relationships

2. Physical-movement evidence
   -> lane connection, movement direction, stop lines, signal-head location
```

The configuration or signal specification document should be treated as the primary source for signal-control semantics. CAD or drawing data should be used to determine which physical lane connection corresponds to that movement.

### Manual Review Triggers

| Trigger | Meaning |
|---|---|
| `phase_cannot_be_mapped_to_lane_connection` | A phase exists, but the corresponding lane movement cannot be identified. |
| `conflicting_signal_group_assignment` | Different sources suggest different signal groups. |
| `signal_group_missing_for_controlled_connection` | A signal-controlled connection lacks a signal group. |
| `movement_phase_mapping_uncertain` | Movement and phase relationship is unclear. |
| `dummy_phase_mistaken_as_control_phase` | Dummy/all-red phase may have been incorrectly assigned. |
| `pedestrian_phase_mapped_to_vehicle_connection` | Pedestrian phase is incorrectly assigned to a vehicle lane connection. |
| `multiple_streams_create_ambiguity` | Complex stream structure makes mapping unclear. |

### Validation Rules

| Rule | Purpose |
|---|---|
| `every_signal_controlled_connection_must_have_signal_group` | Ensure all controlled movements are linked to signal information. |
| `signal_group_must_be_consistent_with_stage_phase_relationship` | Check against phase-stage tables. |
| `signal_group_should_reference_valid_control_phase` | Avoid assigning dummy or invalid phases. |
| `signal_group_assignment_should_match_physical_movement` | Ensure the phase controls the relevant lane connection. |
| `pedestrian_and_vehicle_phases_should_not_be_confused` | Important where crossings are present. |
| `multi_stream_sites_require_stream_consistency_check` | Important for roundabouts or complex junctions. |

## 8. How This Section Supports Later Steps

### Step 2: Fact Extraction

The dictionary tells each parser what to extract:

| Source subtype | Example facts to extract |
|---|---|
| `cad_drawing` | `lane_centreline_nodes`, `lane_connection_candidate`, `stop_line_candidate`, `target_lane_candidate`. |
| `annotated_drawing_pdf` | `movement_annotation`, `crossing_candidate`, `signal_head_annotation`, `lane_type_candidate`. |
| `controller_configuration_pdf` | `phase_label`, `phase_type`, `stage_phase_relationship`, `conflict_matrix_evidence`. |
| `utc_form_docx` | `junction_description`, `phasing_candidate`, `staging_candidate`, `scoot_link`. |
| `mova_schematic_docx` | `movement_phase_mapping`, `detector_candidate`, `movement_direction_candidate`. |

### Step 3: Field Matching

The extracted facts are matched to the target MAPEM fields:

```text
lane_centreline_nodes + reference_point
-> nodeList.nodes[].delta

lane_connection_candidate + lane_id_assignment
-> connectsTo.connectingLane.lane

phase_label + stage_phase_relationship + lane_connection_candidate
-> connectsTo.signalGroup
```

### Step 4: Evidence Fusion

Evidence fusion applies the source priorities:

```text
For nodeList.nodes[].delta:
use CAD geometry first, then fall back to drawing digitisation only if necessary.

For connectsTo.connectingLane.lane:
use CAD topology first, then use drawings or movement schematics for clarification.

For connectsTo.signalGroup:
use official configuration/staging documents first, then combine with physical movement evidence from drawings or CAD.
```

### Step 5: Validation and Manual Review

If the dictionary triggers a review condition, the system should not silently populate the field. It should create a review item instead.

Examples:

```text
cad_coordinate_system_unknown
multiple_target_lanes_plausible
phase_cannot_be_mapped_to_lane_connection
conflicting_signal_group_assignment
```
