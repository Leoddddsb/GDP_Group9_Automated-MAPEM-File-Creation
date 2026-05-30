# Process for Developing the MAPEM Mandatory Element–Source Priority Dictionary

## 1. Purpose

This document defines a clear and reusable process for creating the **MAPEM Mandatory Element–Source Priority Dictionary** for the Automated MAPEM Generation project.

The dictionary is a **design and configuration artefact**. It does not claim that a particular site file has already supplied every MAPEM value. Instead, it defines:

- which **mandatory MAPEM element** must be populated in the MVP;
- whether that element is **constant, configured, managed, extracted, derived, generated, or fused**;
- which intermediate **MAPEM-relevant facts** must be extracted;
- which information-source category should be treated as **primary, supporting, or fallback evidence**;
- when the system must create a **manual-review item** rather than making an unreliable automatic decision; and
- which validation rule should be applied after population.

The dictionary is intended to support the later workflow:

```text
Input files
    ↓
Step 2: Extract MAPEM-relevant facts by file format
    ↓
Step 3: Match extracted facts to MAPEM mandatory elements
    ↓
Step 4: Fuse evidence and create SiteModel / MAPEM outputs
    ↓
Step 5: Validate output and generate manual-review items
```

---

## 2. Key Principle

The dictionary must be **element-centred**, not file-format-centred.

Incorrect logic:

```text
PDF is good for MAPEM.
DWG is good for MAPEM.
```

Adjusted logic:

```text
For each mandatory MAPEM element:
1. Determine how the element should be populated.
2. Identify the fact(s) required to populate it.
3. Identify which source category and source subtype can provide those facts.
4. Rank those sources for that specific element.
5. Record review and validation rules.
```

This matters because the same file format can contain different semantic information. For example, one PDF may be a controller configuration document, while another PDF may be a physical layout drawing.

---

## 3. Dictionary Scope: Mandatory MVP Elements Only

The first dictionary should cover only the **minimum mandatory MAPEM structure** adopted for the MVP.

### 3.1 Corrected Mandatory Skeleton

> Note: `IntersectionGeometry.id.region` must be included alongside `IntersectionGeometry.id.id`, because the intersection reference identifier contains both the road-regulator identifier and the intersection identifier.

```text
MAPEM
│
├── header
│   ├── protocolVersion
│   ├── messageID
│   └── stationID
│
└── map (MapData)
    ├── msgIssueRevision
    └── intersections[]
        └── IntersectionGeometry
            ├── id
            │   ├── region
            │   └── id
            ├── revision
            ├── refPoint
            │   ├── lat
            │   └── long
            └── laneSet[]
                └── GenericLane
                    ├── laneID
                    ├── ingressApproach / egressApproach
                    ├── laneAttributes
                    │   ├── directionalUse
                    │   ├── sharedWith
                    │   └── laneType
                    ├── nodeList
                    │   └── nodes[]
                    │       └── delta
                    └── connectsTo[]
                        └── Connection
                            ├── connectingLane
                            │   └── lane
                            └── signalGroup
```

### 3.2 Excluded from the Active MVP Dictionary

The following elements may be documented later as optional extensions, but should not be mixed into the first mandatory dictionary:

| Optional / extension element | MVP treatment |
|---|---|
| `laneWidth` | Exclude from active mandatory dictionary |
| `speedLimits` | Exclude from active mandatory dictionary |
| `restrictionList` | Exclude from active mandatory dictionary |
| `regional.signalHeadLocations` | Record as possible future extension |
| `connectsTo.connectingLane.maneuver` | Possible future enhancement |
| `GenericLane.maneuvers` | Must not be used under the adopted C-Roads modelling rule |

---

## 4. Source Framework

### 4.1 Use the Project Brief Source Categories as the Top Level

The dictionary should use the source categories identified in the project brief, because these describe the categories of information potentially available for UK traffic-signal sites.

| Source category | Meaning in this project | Current status |
|---|---|---|
| `site_plans_and_cad_files` | Site layout drawings and vector geometry sources | Confirmed in supplied data |
| `gis_data` | Public or authoritative geographic data, such as OSM or Ordnance Survey | Potential source; not yet confirmed in supplied data |
| `site_configuration_information` | Signal-control, phase, stage, stream and official site metadata | Confirmed in supplied data |
| `asset_management_tools` | Pole or signal-equipment location records | Potential source; independent export not yet confirmed |
| `road_condition_and_lidar_surveys` | Topographic or high-resolution geometry evidence | Potential source; not yet confirmed |

### 4.2 Add Source Subtypes Based on Actual Supplied Files

The source category is the high-level classification. The source subtype records the actual kind of document or file received.

| Source category | Source subtype | Confirmed example | Main evidence content |
|---|---|---|---|
| `site_plans_and_cad_files` | `cad_drawing` | Leeds DWG; `T5040 Whitecross.dwg`; `5040 Whitecross.dwg` | Vector geometry and physical layout |
| `site_plans_and_cad_files` | `annotated_drawing_pdf` | `5040_Drawing.pdf` | Layout, detector/pole/head annotations, movement interpretation |
| `site_plans_and_cad_files` | `embedded_layout_in_specification_pdf` | Layout pages in the 337L specification PDF | Supporting visual layout evidence |
| `site_configuration_information` | `signal_specification_pdf` | `337L RODLEY RBOUT SPEC 15_6_15.pdf` | Site identity, streams, phases, stages, stage–phase relationships |
| `site_configuration_information` | `controller_configuration_pdf` | `5040_2500Config_Nov22.pdf` | Controller configuration, phases, stages, streams, conflict data |
| `site_configuration_information` | `utc_form_docx` | `5040_UTCForm_Sep22.docx` | Junction description, SCN, phasing, staging, SCOOT links |
| `site_configuration_information` | `mova_schematic_docx` | `5040_MOVADrawing_Oct22.docx` | Movement/phase and detector-supporting schematic |
| `site_configuration_information` | `ram_8tx` | `5040_RAMData_Nov25.8TX` | Potential changed/override evidence; parser not yet confirmed |
| `site_configuration_information` | `mova_proprietary_file` | `5040_MOVATools_Oct22.mova` | Potential control support; parser not yet confirmed |
| `package_handling_only` | `cad_manifest_txt` | `T5040 Whitecross.txt` | Root DWG and external-reference identification only |

### 4.3 Important Distinction

```text
File format        = PDF / DOCX / DWG / TXT / 8TX / MOVA
Source category    = site plans and CAD files / site configuration information / GIS / etc.
Source subtype     = controller configuration PDF / UTC form DOCX / CAD drawing / etc.
Actual source file = 5040_2500Config_Nov22.pdf / 5040_UTCForm_Sep22.docx / etc.
```

The dictionary should rank **source categories and subtypes**, not generic file extensions.

---

## 5. Population Modes

Before assigning source priority, every MAPEM element must be classified by how it is populated.

| Population mode | Definition | Example mandatory elements |
|---|---|---|
| `constant` | Fixed according to the MAPEM message/profile requirements | `header.protocolVersion`, `header.messageID` |
| `client_configured` | Must be provided or confirmed by client/deployment configuration | `header.stationID`, `id.region` |
| `project_managed` | Maintained by the MAPEM lifecycle/versioning process | `map.msgIssueRevision`, `IntersectionGeometry.revision` |
| `directly_extracted` | Can be read directly from official source content | `id.id` |
| `geometry_derived` | Calculated or inferred from spatial/geometry evidence | `refPoint`, `nodeList.nodes[].delta`, approaches |
| `system_generated` | Assigned by the prototype after objects have been extracted | `laneID` |
| `evidence_fused` | Requires combined evidence from multiple source types | `laneType`, `connectingLane.lane`, `signalGroup` |

### Why Population Mode Must Be Assigned First

This prevents incorrect source assumptions:

| MAPEM element | Incorrect approach | Correct approach |
|---|---|---|
| `revision` | Copy a PDF/drawing issue number | Manage as MAPEM topology revision |
| `laneID` | Look for a lane ID in CAD | Generate stable ID after lane extraction |
| `directionalUse` | Search for a direct text value | Derive from classified lane direction |
| `signalGroup` | Infer from geometry alone | Fuse phase/control evidence with physical connection evidence |

---

## 6. Dictionary-Making Process

## Step 1 — Freeze the Mandatory Key List

Create the definitive list of mandatory MAPEM paths to be handled by the first prototype.

**Output:** `mandatory_mapem_paths`

Example:

```yaml
mandatory_mapem_paths:
  - header.protocolVersion
  - header.messageID
  - header.stationID
  - map.msgIssueRevision
  - map.intersections[].id.region
  - map.intersections[].id.id
  - map.intersections[].revision
  - map.intersections[].refPoint.lat
  - map.intersections[].refPoint.long
  - map.intersections[].laneSet[].laneID
  - map.intersections[].laneSet[].ingressApproach
  - map.intersections[].laneSet[].egressApproach
  - map.intersections[].laneSet[].laneAttributes.directionalUse
  - map.intersections[].laneSet[].laneAttributes.sharedWith
  - map.intersections[].laneSet[].laneAttributes.laneType
  - map.intersections[].laneSet[].nodeList.nodes[].delta
  - map.intersections[].laneSet[].connectsTo[].connectingLane.lane
  - map.intersections[].laneSet[].connectsTo[].signalGroup
```

---

## Step 2 — Assign a Population Mode to Every Element

For each mandatory path, decide whether it is constant, configured, managed, extracted, geometry-derived, system-generated or evidence-fused.

**Output:** a first dictionary column named `population_mode`.

Example:

| MAPEM path | Population mode |
|---|---|
| `header.protocolVersion` | `constant` |
| `header.stationID` | `client_configured` |
| `map.intersections[].id.id` | `directly_extracted` |
| `map.intersections[].refPoint.lat / long` | `geometry_derived` |
| `map.intersections[].laneSet[].laneID` | `system_generated` |
| `map.intersections[].laneSet[].connectsTo[].signalGroup` | `evidence_fused` |

**Rule:** Elements marked `constant`, `project_managed` or `system_generated` do not need a normal source-priority ranking in the same way as extracted elements.

---

## Step 3 — Define Required Intermediate Fact Types

For every evidence-dependent MAPEM element, define what the Week 2 extractors must output.

**Output:** `required_fact_types`

| MAPEM element | Required fact types |
|---|---|
| `id.id` | `official_intersection_id`, `scn`, `orn` |
| `refPoint.lat / long` | `junction_centre_candidate`, `coordinate_reference_system_evidence`, `georeference_status` |
| `laneSet` | `controlled_lane_candidate`, `crosswalk_lane_candidate` |
| `ingressApproach / egressApproach` | `lane_direction_candidate`, `stop_line_candidate`, `road_arm_candidate` |
| `laneAttributes.laneType` | `lane_type_candidate`, `crossing_candidate`, `pedestrian_phase_candidate` |
| `nodeList.nodes[].delta` | `lane_centreline_nodes`, `reference_point`, `coordinate_reference_system_evidence` |
| `connectsTo.connectingLane.lane` | `lane_connection_candidate`, `movement_direction_candidate` |
| `connectsTo.signalGroup` | `phase_label`, `stage_phase_relationship`, `movement_phase_mapping`, `lane_connection_candidate` |

**Rule:** Step 2 extracts facts. It should not prematurely claim that the final MAPEM field has been resolved.

---

## Step 4 — Register Source Categories, Subtypes and Availability

For every source category:

1. Record whether it is confirmed in the supplied dataset.
2. Record the actual available subtypes.
3. Record actual example files.
4. Record whether it is an active MVP dependency or a future extension.

**Output:** `source_registry`

Example:

| Source category | Confirmed? | Active MVP dependency? | Notes |
|---|---:|---:|---|
| `site_plans_and_cad_files` | Yes | Yes | Essential for geometry |
| `site_configuration_information` | Yes | Yes | Essential for control semantics |
| `gis_data` | No | No | Possible fallback / future validation |
| `asset_management_tools` | No independent export | No | May support optional signal-head work later |
| `road_condition_and_lidar_surveys` | No | No | Future geometry-validation source |
| `project_or_client_configuration` | Required | Yes for certain fields | Needed for station/authority/version management |

---

## Step 5 — Assign Element-Specific Source Priority

For each element that depends on evidence, rank the source categories/subtypes that can supply its required facts.

Use:

| Code | Meaning |
|---|---|
| `P1` | Primary source: preferred for automatic population |
| `P2` | Supporting source: confirms or complements P1 evidence |
| `P3` | Fallback source: usable only when stronger evidence is unavailable or with lower confidence |
| `MANUAL` | Value must be supplied or confirmed through review |
| `N/A` | The source is not relevant to the element |

**Rule:** A source does not have one fixed priority for all MAPEM elements. Priority is defined separately for each element.

### Example A: `refPoint.lat / long`

| Priority | Source category / subtype | Condition |
|---|---|---|
| `P1` | `site_plans_and_cad_files → cad_drawing` | Only if CAD is georeferenced or CRS is reliably known |
| `P2` | `gis_data → ordnance_survey / authoritative GIS` | If later supplied |
| `P3` | `gis_data → open_street_map` | Approximate fallback or cross-check |
| `MANUAL` | `annotated_drawing_pdf` only | Cannot produce geographic lat/long without alignment |

### Example B: `nodeList.nodes[].delta`

| Priority | Source category / subtype | Condition |
|---|---|---|
| `P1` | `site_plans_and_cad_files → cad_drawing` | Vector lane geometry available |
| `P2` | `road_condition_and_lidar_surveys` | If later supplied |
| `P3` | `site_plans_and_cad_files → annotated_drawing_pdf` | Digitised fallback only |
| `N/A` | `site_configuration_information` | Does not normally contain centreline geometry |

### Example C: `connectsTo.signalGroup`

| Priority | Source category / subtype | Use |
|---|---|---|
| `P1` | `site_configuration_information → configuration PDF / UTC form / signal specification PDF` | Phase/stage/control semantics |
| `P2` | `site_configuration_information → MOVA schematic DOCX` | Movement-to-phase interpretation support |
| `P3` | `site_plans_and_cad_files → annotated drawing PDF` | Physical movement confirmation only |
| Required complementary evidence | `site_plans_and_cad_files → CAD drawing` | Identifies the physical lane connection; does not determine signal group alone |

---

## Step 6 — Add Source Conditions and Manual-Review Triggers

A source may only be reliable under certain conditions. These conditions must be explicitly written into the dictionary.

**Output fields:**

```yaml
source_conditions:
manual_review_triggers:
```

Examples:

| MAPEM element | Source condition | Manual-review trigger |
|---|---|---|
| `refPoint.lat / long` | CAD must have a known CRS or georeference | `cad_coordinate_system_unknown` |
| `nodeList.nodes[].delta` | Lane centreline geometry must be extractable and referenced to `refPoint` | `lane_centreline_broken` |
| `laneType` | Geometry/drawing classification should agree with pedestrian/cycle control evidence | `lane_type_sources_conflict` |
| `connectingLane.lane` | One connection candidate must be clearly preferred | `multiple_target_lanes_plausible` |
| `signalGroup` | Control phase must be linkable to one physical lane connection | `phase_cannot_be_mapped_to_connection` |

---

## Step 7 — Define Validation Rules

Validation rules check whether a populated element is structurally and semantically acceptable.

**Output:** `validation_rules`

| MAPEM element | Example validation rule |
|---|---|
| `header.protocolVersion` | Must match the required protocol constant |
| `header.messageID` | Must identify MAPEM |
| `id.id` | Must be populated and unique within the road-regulator domain |
| `revision` | Must not be copied from ordinary document issue number; must match corresponding SPATEM revision when paired |
| `refPoint` | Latitude and longitude must be present; point should lie near the conflict-area centre |
| `laneID` | Must be unique within the intersection |
| `nodeList.nodes[].delta` | Must encode geometry relative to `refPoint` and follow the lane centreline |
| `connectingLane.lane` | Must reference an existing `laneID` |
| `signalGroup` | Every signal-controlled connection must have a signal-group assignment |

---

## Step 8 — Produce Two Outputs

The dictionary-making process should generate two related artefacts.

### Output A: Machine-Readable Dictionary

**Filename:** `mapem_element_source_priority_dictionary.yaml`

Used by the prototype for:

- required fact extraction;
- fact-to-field matching;
- source-priority selection;
- manual-review trigger generation; and
- validation checks.

### Output B: Human-Readable Overview

**Filename:** `mapem_element_source_priority_overview.md`

Used in the report or presentation to show:

| MAPEM element | Population mode | P1 source | P2 source | Key limitation / review trigger |
|---|---|---|---|---|

---

## 7. Minimum Dictionary Table to Complete

This is the minimum table that the group should populate before writing the full YAML configuration.

| MAPEM mandatory element | Population mode | Required fact type(s) | P1 source category / subtype | P2 supporting source | P3 / fallback | Manual-review trigger | Validation rule |
|---|---|---|---|---|---|---|---|
| `header.protocolVersion` | `constant` | — | System constant | — | — | Incorrect constant | Must match required protocol value |
| `header.messageID` | `constant` | — | System constant | — | — | Incorrect message type | Must identify MAPEM |
| `header.stationID` | `client_configured` | `station_id` | Project/client configuration | Official source only if explicit | — | Missing/conflicting ID | Must be populated |
| `map.msgIssueRevision` | `project_managed` | `mapem_message_revision` | MAPEM lifecycle record | — | — | Not initialised | Must not be copied from document issue |
| `id.region` | `client_configured` | `road_regulator_id` | Project/client configuration | Official council metadata if explicit | — | Authority identifier unconfirmed | Must be populated |
| `id.id` | `directly_extracted` | `official_intersection_id` | Site configuration: UTC/config/spec document | Drawing title block | Filename with review | Conflicting IDs | Must identify one intersection |
| `revision` | `project_managed` | `topology_revision` | MAPEM lifecycle record | Client confirmation | — | Document issue mistaken as revision | Update only for topology change |
| `refPoint.lat / long` | `geometry_derived` | `junction_centre_candidate`, `crs_evidence` | CAD drawing if georeferenced | Authoritative GIS, if supplied | OSM / manual alignment | CRS unknown or coordinates conflict | Must lie near conflict-area centre |
| `laneSet` | `geometry_derived` | `controlled_lane_candidate`, `crosswalk_candidate` | CAD drawing | Annotated drawing | Manual digitisation | Controlled lane not geometrically resolved | All signal-controlled lanes included |
| `laneID` | `system_generated` | `lane_candidate` | System allocation | — | — | Duplicate IDs | Unique within intersection |
| `ingressApproach / egressApproach` | `geometry_derived` | `lane_direction_candidate`, `stop_line_candidate` | CAD drawing | Annotated drawing / schematic | Manual assignment | Direction uncertain | Consistent with lane direction |
| `directionalUse` | `geometry_derived` | `classified_lane_direction` | Derived from approach assignment | Drawing validation | Manual correction | Approach unresolved | Correct directional bit(s) set |
| `sharedWith` | `evidence_fused` | `shared_use_candidate` | CAD/drawing markings | Configuration notes | Manual confirmation | Shared use unclear | Mandatory value populated |
| `laneType` | `evidence_fused` | `lane_type_candidate`, `crossing_candidate`, `phase_type` | CAD / annotated drawing | Site configuration evidence | Manual classification | Sources disagree | Mandatory lane type selected |
| `nodeList.nodes[].delta` | `geometry_derived` | `lane_centreline_nodes`, `refPoint` | CAD drawing | LiDAR if later supplied | Digitised drawing | Geometry broken / unreferenced | Nodes follow lane centreline |
| `connectsTo.connectingLane.lane` | `evidence_fused` | `lane_connection_candidate` | CAD topology | Annotated drawing / schematic | Manual mapping | Multiple targets plausible | Target lane exists |
| `connectsTo.signalGroup` | `evidence_fused` | `phase_label`, `stage_phase_relationship`, `movement_phase_mapping` | Site configuration document | MOVA schematic | Annotated drawing support only | Phase cannot map to connection | Every controlled connection assigned |

---

## 8. Minimum YAML Skeleton

The first implementation does not need every numerical confidence rule. It should contain only the configuration required to support extraction, matching, fusion and review.

```yaml
dictionary_metadata:
  name: mapem_element_source_priority_dictionary
  scope: mandatory_mvp_elements
  purpose: >
    Define how mandatory MAPEM elements are populated from supplied
    traffic-signal site data and how uncertainty is handled.

source_categories:
  site_plans_and_cad_files:
    confirmed_in_current_dataset: true
    active_mvp_dependency: true
    confirmed_subtypes:
      - cad_drawing
      - annotated_drawing_pdf
      - embedded_layout_in_specification_pdf

  site_configuration_information:
    confirmed_in_current_dataset: true
    active_mvp_dependency: true
    confirmed_subtypes:
      - signal_specification_pdf
      - controller_configuration_pdf
      - utc_form_docx
      - mova_schematic_docx
      - ram_8tx
      - mova_proprietary_file

  gis_data:
    confirmed_in_current_dataset: false
    active_mvp_dependency: false
    possible_subtypes:
      - open_street_map
      - ordnance_survey

  asset_management_tools:
    confirmed_in_current_dataset: false
    active_mvp_dependency: false
    possible_subtypes:
      - pole_asset_export
      - signal_head_asset_export

  road_condition_and_lidar_surveys:
    confirmed_in_current_dataset: false
    active_mvp_dependency: false
    possible_subtypes:
      - lidar
      - topographic_survey

  project_or_client_configuration:
    active_mvp_dependency: true
    provides:
      - station_id
      - road_regulator_id
      - mapem_revision_management

elements:

  map.intersections[].id.id:
    mandatory_in_mvp: true
    population_mode: directly_extracted
    required_fact_types:
      - official_intersection_id
    source_priority:
      - priority: P1
        source_category: site_configuration_information
        preferred_subtypes:
          - utc_form_docx
          - controller_configuration_pdf
          - signal_specification_pdf
      - priority: P2
        source_category: site_plans_and_cad_files
        preferred_subtypes:
          - annotated_drawing_pdf
        use_for: title_block_confirmation
    manual_review_triggers:
      - conflicting_official_intersection_ids
      - missing_official_intersection_id
    validation_rules:
      - intersection_id_must_be_present

  map.intersections[].refPoint:
    mandatory_in_mvp: true
    population_mode: geometry_derived
    required_fact_types:
      - junction_centre_candidate
      - coordinate_reference_system_evidence
    source_priority:
      - priority: P1
        source_category: site_plans_and_cad_files
        preferred_subtypes:
          - cad_drawing
        condition: georeference_available
      - priority: P2
        source_category: gis_data
        preferred_subtypes:
          - ordnance_survey
          - open_street_map
        condition: if_available
      - priority: P3
        source_category: site_plans_and_cad_files
        preferred_subtypes:
          - annotated_drawing_pdf
        condition: manual_geographic_alignment_required
    manual_review_triggers:
      - cad_coordinate_system_unknown
      - candidate_reference_points_conflict
    validation_rules:
      - latitude_and_longitude_must_be_present
      - reference_point_should_be_near_conflict_area_centre

  map.intersections[].laneSet[].nodeList.nodes[].delta:
    mandatory_in_mvp: true
    population_mode: geometry_derived
    required_fact_types:
      - lane_centreline_nodes
      - reference_point
    source_priority:
      - priority: P1
        source_category: site_plans_and_cad_files
        preferred_subtypes:
          - cad_drawing
      - priority: P2
        source_category: road_condition_and_lidar_surveys
        condition: if_available
      - priority: P3
        source_category: site_plans_and_cad_files
        preferred_subtypes:
          - annotated_drawing_pdf
        condition: fallback_digitisation_only
    manual_review_triggers:
      - lane_centreline_broken
      - geometry_not_georeferenced
    validation_rules:
      - nodes_must_follow_lane_centreline
      - nodes_must_be_encoded_relative_to_refpoint

  map.intersections[].laneSet[].connectsTo[].signalGroup:
    mandatory_in_mvp: true
    population_mode: evidence_fused
    required_fact_types:
      - phase_label
      - stage_phase_relationship
      - movement_phase_mapping
      - lane_connection_candidate
    source_priority:
      - priority: P1
        source_category: site_configuration_information
        preferred_subtypes:
          - controller_configuration_pdf
          - utc_form_docx
          - signal_specification_pdf
      - priority: P2
        source_category: site_configuration_information
        preferred_subtypes:
          - mova_schematic_docx
      - priority: P3
        source_category: site_plans_and_cad_files
        preferred_subtypes:
          - annotated_drawing_pdf
        use_for: physical_movement_confirmation_only
    manual_review_triggers:
      - phase_cannot_be_mapped_to_lane_connection
      - conflicting_signal_group_assignment
    validation_rules:
      - every_signal_controlled_connection_must_have_signal_group
```

---

## 9. How the Dictionary Is Used in Later Steps

### Step 2: Extract MAPEM-Relevant Facts

The parser uses `required_fact_types` to determine what should be extracted.

| Source subtype | Example facts to extract |
|---|---|
| `signal_specification_pdf` | `official_intersection_id`, `phase_label`, `stage_phase_relationship`, `pedestrian_phase_candidate` |
| `controller_configuration_pdf` | `official_intersection_id`, `phase_label`, `stage_phase_relationship`, `stream_count` |
| `utc_form_docx` | `official_intersection_id`, `junction_description`, `phasing_candidate`, `scoot_link` |
| `cad_drawing` | `lane_candidate`, `lane_centreline_nodes`, `stop_line_candidate`, `lane_connection_candidate` |
| `annotated_drawing_pdf` | `crossing_candidate`, `lane_type_candidate`, `movement_annotation` |
| `mova_schematic_docx` | `movement_phase_mapping`, `detector_candidate` |

**Output:** `extracted_facts.partial.json`

### Step 3: Match Facts to MAPEM Elements

The matcher uses the dictionary to identify target MAPEM paths.

```text
official_intersection_id
→ map.intersections[].id.id

lane_centreline_nodes + reference_point
→ map.intersections[].laneSet[].nodeList.nodes[].delta

phase_label + stage_phase_relationship + lane_connection_candidate
→ map.intersections[].laneSet[].connectsTo[].signalGroup
```

**Output:** `mapped_evidence.partial.json` and `field_source_matrix.md`

### Step 4: Fuse Evidence and Generate SiteModel

The evidence-fusion step uses `source_priority` and `source_conditions`.

Example:

```text
For connectsTo.signalGroup:
- prefer phase/stage evidence extracted from official site configuration;
- use MOVA schematic evidence for supporting interpretation;
- use CAD/drawing geometry to associate the phase with a physical lane connection;
- send the field to review if a unique connection cannot be determined.
```

**Output:** `site_model.json`, `mapem.json`, `mapem.asn1`

### Step 5: Validate and Review

The validation process uses `manual_review_triggers` and `validation_rules`.

Example triggers:

```text
cad_coordinate_system_unknown
phase_cannot_be_mapped_to_lane_connection
multiple_target_lanes_plausible
lane_centreline_broken
```

**Output:** `validation_report.json` and `manual_review_items`

---

## 10. Definition of Done for the Initial Dictionary

The initial dictionary is complete when:

- [ ] It contains every mandatory MVP MAPEM element, including `IntersectionGeometry.id.region`.
- [ ] It distinguishes mandatory MVP elements from optional future extensions.
- [ ] Every element has a `population_mode`.
- [ ] Every evidence-dependent element has `required_fact_types`.
- [ ] The top-level source categories align with the project brief.
- [ ] Actual Leeds and 5040 source subtypes are registered under those categories.
- [ ] Potential but unconfirmed sources are clearly marked as non-MVP dependencies.
- [ ] Source priority is assigned element-by-element rather than globally.
- [ ] Key source conditions and manual-review triggers are recorded.
- [ ] Minimum validation rules are recorded.
- [ ] The dictionary can guide Step 2 extraction and Step 3 field matching without becoming a site-specific evidence result table.

---

## 11. Reference Documents Used

1. **Project Brief — Automated MAPEM Generation**: identifies potentially available traffic-signal information sources and the requirement to identify a minimum viable data set.
2. **Project Plan**: defines the workflow from file-format extraction to MAPEM field matching, evidence fusion, output generation and validation.
3. **C-ITS European Handbook for MAPEM and SPATEM Creation, Version 3.2.0**: defines MAPEM data elements and modelling guidance.
4. **MAPEM Mandatory Elements — Definitions** and **MAPEM Minimal Mandatory Skeleton (Clean)**: define the group's intended mandatory MVP structure.
5. **Leeds Example Site: 337L Rodley Roundabout Specification and DWG**: confirms a signal specification PDF plus CAD drawing site package.
6. **BathNES Example Site: 5040 White Cross files**: confirms a multi-format package including configuration PDF, UTC form DOCX, detailed drawing PDF, MOVA schematic, CAD drawings and associated supporting files.
