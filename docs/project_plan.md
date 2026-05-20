# Project Plan

This document defines the planned workflow for automated MAPEM file creation. The project is no longer designed only around Leeds PDF + DWG inputs. It now treats PDF, DOCX, DWG/DXF, ZIP, TXT/8TX, GIS/OSM, and possible survey / LiDAR data as input formats that may contain MAPEM-relevant information.

The current engineering approach is:

1. Confirm which MAPEM elements are required.
2. Use file-format parsers to extract MAPEM-relevant facts.
3. Match extracted facts directly to MAPEM fields.
4. Generate a field-source matrix.
5. Use evidence fusion to create the internal `SiteModel`.
6. Generate MAPEM outputs and validation reports.

The first version should avoid two extremes:

- Do not generate MAPEM directly from "PDF/CAD" assumptions, because the same PDF format may contain different types of information.
- Do not add a separate source-category classification step, because it does not directly help extract the required MAPEM fields and adds unnecessary complexity.

Therefore, the first version uses a practical workflow: **file-format extraction first, MAPEM field matching second**.

## 1. Planned Workflow

Overview:

| Step | Purpose | Output File | Related GitHub Folder |
| --- | --- | --- | --- |
| Step 1 | Build a file inventory for each site | `site_inventory.partial.json` | `configs/`, `src/mapemgen/ingestion/` |
| Step 2 | Extract MAPEM-relevant facts by file format | `extracted_facts.partial.json` | `src/mapemgen/ingestion/` |
| Step 3 | Match extracted facts to MAPEM fields and generate a field-source matrix | `mapped_evidence.partial.json`, `field_source_matrix.md` | `src/mapemgen/`, `docs/` |
| Step 4 | Fuse mapped evidence and automatically create a MAPEM-style SiteModel and MAPEM outputs | `site_model.json`, `mapem.json`, `mapem.asn1` | `src/mapemgen/`, `src/mapemgen/generators/`, `schemas/` |
| Step 5 | Validate outputs and generate low-confidence / manual review items | `validation_report.json` | `src/mapemgen/validation/` |
| Step 6 | Run robustness testing with development and held-out validation sites | `robustness_summary.json` | `tests/`, `docs/` |
| Step 7 | Calculate conversion quality scores | `validation_report.json` | `src/mapemgen/validation/`, `docs/` |

Note: "Related GitHub Folder" means where the code, configuration, or documentation for that step should mainly live in the repository. It does not mean the output files must be stored there.

### Step 1: Build File Inventory

For each site, the program should automatically generate a local `site_inventory.partial.json`. This inventory is based on file path, file extension, and filename keywords. It records what files are available for the site, their formats, useful filename hints, readability status, and the parser that should handle each file.

```text
site_id
site_name
local_authority_or_dataset
source_files:
  - file_path
  - file_type
  - filename_hints
  - readable_status
  - parser_to_use
  - notes
junction_type
controller_type
control_method
stream_count
stage_count
phase_labels
known_special_logic
confidence
manual_questions
```

Parser routing:

```text
PDF       -> pdf text/table/drawing parser
DOCX      -> docx text/table parser
DWG/DXF   -> CAD geometry parser
ZIP       -> package inventory parser, then root DWG / xref handling
TXT/8TX   -> RAM / text parser
MOVA      -> binary/proprietary file; first version only records availability
GIS/OSM   -> GIS/public data parser
LiDAR     -> survey/point-cloud parser, if data is available
```

Filename hints should be recorded automatically:

| Filename keyword | Generated hint | Possible use |
| --- | --- | --- |
| `Spec`, `2500Config`, `Configuration` | possible configuration file | phases, stages, streams, controller settings |
| `Drawing`, `AsBuilt`, `DetailedDesign` | possible drawing / layout file | road layout, crossings, detectors, stage diagram |
| `UTCForm` | possible UTC form | SCN, site metadata, SCOOT links, staging |
| `SCOOTDets` | possible SCOOT detector data | detector IDs, approach links |
| `RAMData` | possible RAM / override data | timing changes, intergreen overrides, detector overrides |
| `MOVA` | possible MOVA/control logic data | MOVA detector/control information |
| `.zip` containing `.dwg` | possible CAD package | root drawing, xref drawings, OS/topographic drawing |

Example:

```json
{
  "site_id": "1003",
  "source_files": [
    {
      "file_path": "1003_UTCForm_May24.docx",
      "file_type": "docx",
      "filename_hints": ["possible UTC form", "possible site metadata", "possible staging"],
      "readable_status": "text_readable",
      "parser_to_use": "docx_parser"
    },
    {
      "file_path": "T1003 Cleveland Place.dwg",
      "file_type": "dwg",
      "filename_hints": ["possible CAD drawing"],
      "readable_status": "needs_dxf_conversion",
      "parser_to_use": "cad_parser_after_conversion"
    }
  ]
}
```

Output file: `site_inventory.partial.json`  
Related GitHub folders: `configs/`, `src/mapemgen/ingestion/`

`configs/` should hold site configuration and parser rules. `src/mapemgen/ingestion/` should hold the code that reads input files and generates the file inventory.

### Step 2: Extract MAPEM-relevant Facts by File Format

This step uses format-specific extractors to convert each input file into intermediate MAPEM-relevant facts. The goal is not to extract everything from every file. The goal is to extract everything relevant to MAPEM.

Processing flow:

```text
input files
        |
        +-- PDF extractor
        +-- DOCX extractor
        +-- CAD/DXF extractor
        +-- ZIP inventory extractor
        +-- TXT/8TX RAM extractor
        +-- GIS/OSM extractor
        |
        +-- extracted_facts.partial.json
```

First-version parser responsibilities:

| Parser | Input | Output fact types |
| --- | --- | --- |
| PDF parser | spec PDF, drawing PDF, config PDF, MOVA report PDF | page text, tables, phase/stage tables, drawing labels, stage diagrams, detector labels |
| DOCX parser | UTC form, RAM record, MOVA drawing notes | site metadata, SCN, IP, staging, SCOOT links, timing data, RAM notes |
| CAD/DXF parser | DWG converted DXF, root drawing, xrefs | lane candidates, stop line candidates, crossing candidates, signal head candidates, layer names, coordinate range |
| ZIP parser | DWG packages | root drawing, xref list, OS/topographic drawing availability |
| TXT/8TX parser | RAM differences report | changed timings, intergreen overrides, detector overrides, I/O allocation differences |
| GIS/OSM parser | public GIS / OSM | road names, approximate topology, speed limits, approximate refPoint |
| LiDAR/survey parser | survey/LiDAR data if available | kerbs, lane edges, high-resolution topographic evidence |

Example `extracted_facts.partial.json`:

```json
{
  "site_id": "1003",
  "source_file": "1003_UTCForm_May24.docx",
  "file_type": "docx",
  "extracted_facts": [
    {
      "fact_type": "site_name",
      "value": "1003 A4 London Rd / Cleveland Place",
      "evidence_location": "UTC Junction Description",
      "confidence": 0.95
    },
    {
      "fact_type": "scoot_link",
      "value": "N04211A London Rd WB Ahead",
      "evidence_location": "SCOOT Links table",
      "confidence": 0.90
    }
  ]
}
```

Output file: `extracted_facts.partial.json`
Related folder: `src/mapemgen/ingestion/`

### Step 3: MAPEM Field Matching and Field-source Matrix

This step matches the facts from Step 2 to MAPEM fields. The field-source matrix is not assumed upfront. It is generated from the extracted facts and the matching rules.

Processing flow:

```text
extracted_facts.partial.json
        |
        +-- fact_type to MAPEM field matching rules
        |
        +-- mapped_evidence.partial.json
        |
        +-- field_source_matrix.md
```

Example matching rules:

| Fact type | Possible MAPEM field | Notes |
| --- | --- | --- |
| `site_name` | `IntersectionGeometry.name` | site name or junction description |
| `junction_centre_candidate` | `IntersectionGeometry.refPoint` | inferred reference point from CAD/GIS/drawing |
| `lane_candidate` | `GenericLane.nodeList` | later converted into MAPEM `NodeXY` |
| `stop_line_candidate` | lane start/end and approach assignment | helps infer lane direction and ingress/egress |
| `phase_label` | `connectsTo.signalGroup` candidate | phase labels must be matched to movement / lane connection |
| `stage_phase_table` | `connectsTo.signalGroup`, `maneuvers` | provides phase/stage/movement relationship |
| `scoot_link` | lane / approach semantic evidence | helps infer approach and movement |
| `ram_intergreen_override` | validation evidence for timing/control | mainly used for validation or override evidence |

Example `field_source_matrix.md`:

| MAPEM field | Matched facts | Source files | Evidence location | Confidence |
| --- | --- | --- | --- | ---: |
| `IntersectionGeometry.refPoint` | `junction_centre_candidate`, `gis_intersection_point` | CAD/DXF, OSM | CAD coordinates, OSM node | 0.82 |
| `GenericLane.nodeList` | `lane_candidate` | CAD/DXF | CAD layer / polyline | 0.78 |
| `connectsTo.signalGroup` | `phase_label`, `stage_phase_table` | config PDF, UTC form DOCX | PDF table, DOCX section | 0.86 |
| `signalHeadLocations` | `signal_head_candidate`, `pole_candidate` | CAD/DXF, asset data | CAD symbol / asset record | 0.74 |

This step has two engineering responsibilities:

1. Make the program aware of which facts can populate which MAPEM fields.
2. Make the report show which files, facts, evidence locations, and confidence values support each MAPEM field.

Example `mapped_evidence.partial.json`:

```json
{
  "site_id": "1003",
  "mapem_field": "IntersectionGeometry.refPoint",
  "matched_fact_type": "junction_centre_candidate",
  "value": "...",
  "source_file": "T1003 Cleveland Place.dwg",
  "file_type": "dwg",
  "evidence_location": "CAD layer / coordinates",
  "confidence": 0.82
}
```

Output files: `mapped_evidence.partial.json`, `field_source_matrix.md`
Related folders: `src/mapemgen/`, `docs/`

### Step 4: Evidence Fusion and Automatic Conversion to MAPEM-style SiteModel

This step combines mapped evidence into the internal `SiteModel`. It is not just concatenation. It must handle complementary evidence, conflicts, and confidence.

Processing flow:

```text
mapped_evidence.partial.json
        |
        +-- group by site_id
        |
        +-- group by mapem_field
        |
        +-- collect candidate values for each MAPEM field
        |
        +-- select final value using source priority + confidence + consistency
        |
        +-- write final value into SiteModel
        |
        +-- unresolved fields become manual_review_items
```

Step 2 produces raw facts. Step 3 maps those facts to MAPEM fields. Step 4 turns the mapped evidence into final `SiteModel` fields.

Initial fusion rules:

| Situation | Program action | SiteModel result |
| --- | --- | --- |
| One high-confidence evidence item | accept it | write the field |
| Multiple evidence items agree | use preferred source or highest-confidence value | write the field and keep provenance |
| Multiple evidence items are close but not identical | choose the highest-confidence value and reduce field confidence | write the field and generate warning |
| Multiple evidence items conflict clearly | do not decide automatically | leave field empty or use a low-confidence candidate, and create `manual_review_item` |
| No evidence | mark missing field | leave field empty and report in validation |

Example for `refPoint`:

```json
[
  {
    "mapem_field": "IntersectionGeometry.refPoint",
    "value": { "lat": 53.8123, "lon": -1.5762 },
    "source_file": "T1003 Cleveland Place.dwg",
    "confidence": 0.85
  },
  {
    "mapem_field": "IntersectionGeometry.refPoint",
    "value": { "lat": 53.8121, "lon": -1.5760 },
    "source_file": "OpenStreetMap",
    "confidence": 0.70
  }
]
```

If the two candidate points are close, the program can select the CAD value because CAD is the preferred source for `refPoint` and has higher confidence:

```json
{
  "mapData": {
    "intersections": [
      {
        "refPoint": {
          "lat": 53.8123,
          "lon": -1.5762
        }
      }
    ]
  }
}
```

The internal SiteModel may keep provenance and confidence for validation:

```json
{
  "field": "IntersectionGeometry.refPoint",
  "selected_source": "T1003 Cleveland Place.dwg",
  "confidence": 0.85,
  "alternative_sources": ["OpenStreetMap"]
}
```

If CAD and GIS disagree significantly, the program should not hard-code one value. It should create a `manual_review_item`. After review, the final value is written back to `SiteModel`.

Automatic conversion logic:

```text
geometry facts
        |
        +-- mapped geometry evidence
            laneSet / nodeList / stop lines / crossings / signalHeadLocations

control facts
        |
        +-- mapped control evidence
            phases / stages / streams / signalGroup / intergreens

location and road facts
        |
        +-- mapped location and road evidence
            refPoint / road names / speedLimits / approximate topology

asset / survey facts
        |
        +-- mapped asset / survey evidence
            poles / signal heads / detector positions

evidence fusion
        |
        +-- SiteModel
        |
        +-- mapem.json
        |
        +-- mapem.asn1
```

Output files: `site_model.json`, `mapem.json`, `mapem.asn1`

This step produces the first automatic conversion result. It has not yet gone through low-confidence checks or manual review in Step 5.

`site_model.json` is the first internal intermediate model. `mapem.json` and `mapem.asn1` are initial MAPEM drafts generated from that `site_model.json`. After manual review, the updated MAPEM outputs must be regenerated.

Conversion from `site_model.json` to MAPEM outputs:

```text
site_model.json
        |
        +-- read as SiteModel
        |
        +-- generator filters / normalises / encodes MAPEM fields
        |
        +-- mapem.json
        |
        +-- mapem.asn1
```

The current `SiteModel` is close to the MAPEM hierarchy, so the first conversion may look like a direct export. Conceptually, they remain different:

- `site_model.json` is the internal project model.
- `mapem.json` is the filtered, normalised, MAPEM-facing output.

The generator is responsible for:

- removing internal debugging fields
- converting field names where needed
- checking required MAPEM fields
- converting geometry into MAPEM `NodeXY` representation
- converting lane connections into MAPEM `connectsTo`
- placing `signalGroup` at the correct connection level
- producing ASN.1-style or standards-compliant ASN.1 output

Related folders: `src/mapemgen/`, `src/mapemgen/generators/`, `schemas/`

### Step 5: Output Low-confidence and Manual Review Items

`validation_report.json` is generated in this step. It reads the intermediate outputs from previous steps and the `site_model.json` / `SiteModel` produced in Step 4. It checks file inventory, fact extraction, field matching, evidence fusion, and the SiteModel itself.

Validation inputs:

```text
site_inventory.partial.json
        |
        +-- file readability / parser availability

extracted_facts.partial.json
        |
        +-- fact extraction success / missing facts

mapped_evidence.partial.json
        |
        +-- field matching success / unmatched facts

field_source_matrix.md
        |
        +-- missing MAPEM fields / weak evidence coverage

site_model.json
        |
        +-- completeness / geometry consistency / semantic consistency
```

Output file: `validation_report.json`  
Related folder: `src/mapemgen/validation/`

Example `validation_report.json`:

```json
{
  "site_id": "397L",
  "status": "needs_review",
  "summary": {
    "error_count": 0,
    "warning_count": 3,
    "manual_review_count": 2
  },
  "scores": {
    "file_readability_score": 95,
    "fact_extraction_score": 86,
    "field_matching_score": 82,
    "fusion_consistency_score": 80,
    "sitemodel_completeness_score": 88,
    "geometry_score": 76,
    "semantic_score": 82,
    "manual_effort_score": 84,
    "overall_quality_score": 84
  },
  "errors": [],
  "warnings": [
    "DWG georeference is missing",
    "Lane direction confidence is low"
  ],
  "manual_review_items": []
}
```

`manual_review_items` is a list inside `validation_report.json`. It stores low-confidence fields, extraction failures, conflicts, and items that require manual confirmation.

Each site should automatically output:

```text
manual_review_items
|
+-- review_id
+-- item_id
+-- severity
+-- mapem_field
+-- issue_type
+-- current_value
+-- candidate_values
+-- evidence_source
+-- evidence_location
+-- confidence
+-- suggested_action
+-- affects_quality_score
```

These items feed directly into `manual_effort_score`.

| Low-confidence / manual review item | Affected MAPEM field | Automatic detection method | Evidence shown to reviewer | Effect on `manual_effort_score` |
| --- | --- | --- | --- | --- |
| Phase / stage / control fact extraction failed | `connectsTo.signalGroup`, `maneuvers`, stage/phase metadata | phase/stage/stream data missing, abnormal table rows, missing phase labels | file name, page/section, failed table, raw text snippet | High |
| Phase / stage / control facts conflict internally | `signalGroup`, `maneuvers` | phase appears in stage table but not in phase list, or files disagree | conflicting phase label and evidence | High |
| Geometry evidence is insufficient | `GenericLane.nodeList`, `connectsTo`, `signalHeadLocations` | PDF / CAD / survey cannot reliably identify lanes, stop lines, crossings, or signal heads | file name, CAD layer, drawing area, candidate objects | High |
| File cannot be read or parser is unavailable | depends on file | corrupt file, unextractable PDF, DWG not converted, ZIP missing root drawing | file name, file type, failure reason, suggested parser | Medium-high |
| Fact cannot be matched to a MAPEM field | affected MAPEM field | extracted fact exists but has no matching rule or no matched result | fact type, source file, suggested MAPEM field | Medium |
| Field-source matrix shows no source for a field | affected MAPEM field | required MAPEM field has no matched evidence | missing MAPEM field, attempted files, impact | High |
| Fusion cannot decide final value automatically | affected MAPEM field | multiple candidate values are valid but no rule can select one | candidate values, source files, suggested manual choice | High |
| SiteModel reference error | lane references, `connectsTo`, `signalGroup` | `connectsTo` points to missing lane, or `signalGroup` reference is missing | error field, reference ID, related evidence | High |
| Evidence conflict across files | affected MAPEM field | CAD, drawing PDF, GIS, or asset data gives conflicting positions or attributes | conflicting files, candidate values, confidence | Medium-high |
| Coordinate system is unclear | `refPoint`, `nodeList.nodes`, `signalHeadLocations` | DWG/DXF lacks recognisable georeference, or coordinate range does not match WGS84 / local grid | CAD file name, coordinate range, CRS evidence | High |
| DWG has no georeference | `refPoint`, all geometry offsets | no EPSG, world file, or known control point | request manual refPoint or control points | High |
| CAD symbol layer is inconsistent or unrecognised | `signalHeadLocations`, signal head to `signalGroup` mapping | layer rules fail to match signal head / pole symbols, or symbols appear on unknown layers | unmatched layer names, symbol count, candidate object coordinates | Medium-high |
| Lane centreline is broken or too short | `GenericLane.nodeList.nodes` | polyline too short, too few nodes, or large gaps between segments | lane candidate ID, coordinates, CAD layer | High |
| Lane direction is uncertain | `ingressApproach`, `egressApproach`, `connectsTo` | polyline direction conflicts with approach, stop line, or movement inference | candidate direction, road label, stop line location | Medium-high |
| `connectsTo` has multiple candidate target lanes | `GenericLane.connectsTo` | one ingress lane matches multiple downstream lanes with similar scores | source lane, candidate target lanes, confidence values | High |
| Movement inference is uncertain | `maneuvers`, `connectsTo.connectingLane.maneuver` | geometry angle conflicts with stage arrow or phase description | left/straight/right candidates, angle, evidence | High |
| `signalGroup` cannot be matched to lane movement | `connectsTo.signalGroup` | phase label exists but cannot be matched to lane connection | phase label, evidence location, candidate lanes | High |
| `signalGroup` is shared by conflicting movements | `connectsTo.signalGroup`, consistency checks | conflict matrix shows conflicting phases but mapping assigns shared movement group | conflicting phases, affected lanes, conflict table location | High |
| Stop line cannot be recognised | lane start/end, approach assignment | layer rules cannot find stop line, or stop line is too far from lane endpoint | candidate lane, nearest stop line distance, layer evidence | Medium |
| Pedestrian crossing geometry is missing | pedestrian lanes / crossings, `signalHeadLocations` | pedestrian / puffin phase exists but crossing geometry is missing | phase label, evidence location, missing geometry evidence | Medium |
| Roundabout internal lanes cannot be connected reliably | `laneSet`, `connectsTo` | internal lanes cannot be matched uniquely to entry/exit lanes | affected stream, candidate lanes, matching score | High |
| Speed limit is missing | `speedLimits` | not found in PDF/GIS/OSM | site ID and missing field | Low |
| Restrictions are missing | `restrictionList` | not extracted from notes or CAD markings | site ID and missing field | Low-medium |

Example `manual_review_items` output:

```json
{
  "manual_review_items": [
    {
      "review_id": "R1",
      "item_id": "397L-CAD-001",
      "severity": "high",
      "mapem_field": "IntersectionGeometry.refPoint",
      "issue_type": "dwg_georeference_missing",
      "current_value": null,
      "candidate_values": [
        { "lat": 53.8123, "lon": -1.5762, "source": "estimated junction centre" }
      ],
      "evidence_source": "DWG/DXF",
      "evidence_location": "UTMC_300097_397L_04.dwg",
      "confidence": 0.30,
      "suggested_action": "Accept the estimated refPoint or select a corrected reference point in the review interface.",
      "affects_quality_score": ["geometry_score", "manual_effort_score"]
    }
  ]
}
```

Each `manual_review_item` should make clear:

- the short review ID shown in the interface, for example `R1`
- which MAPEM field needs confirmation
- the current value
- possible candidate values
- where the uncertainty comes from
- what the user should do, such as `accept` or `correct`

`manual_effort_score` can be calculated from these items:

```text
manual_effort_score = 100 - weighted_manual_review_cost

weighted_manual_review_cost =
  high_severity_count * 8
+ medium_severity_count * 4
+ low_severity_count * 1
+ manual_override_count * 3
```

Manual review should be handled through an interface that writes feedback back into `SiteModel`. The client should not edit JSON in a terminal.

Review workflow:

```text
1. Automatic conversion
   mapped evidence -> SiteModel -> mapem.json / mapem.asn1

2. Automatic validation
   Generate validation_report.json
   List manual_review_items

3. Client reviews items in the interface
   Each item shows:
   - what the issue is
   - which MAPEM field is affected
   - system candidate value
   - confidence
   - source file / PDF page / DOCX section / CAD layer / GIS feature / coordinate evidence

4. Client chooses action
   - Accept: accept the automatic result
   - Correct: enter or select a corrected value

5. System writes the review result back
   - update SiteModel
   - update validation_report.json
   - recalculate quality score
   - regenerate mapem.json / mapem.asn1
```

Manual actions:

| Action | Meaning | Required input |
| --- | --- | --- |
| `accept` | The automatic result is correct | No extra input |
| `correct` | The automatic result is wrong | New `candidate_values` only |

The review interface should summarise `manual_review_items` for the client rather than exposing raw JSON. The client should see each `review_id`, the issue, affected MAPEM field, candidate value, confidence, evidence, and suggested action.

When the client selects `accept` or `correct`, the program uses `review_id` to locate the affected `mapem_field` and update the internal `SiteModel`:

```json
{
  "mapData": {
    "intersections": [
      {
        "refPoint": {
          "lat": 53.8123,
          "lon": -1.5762
        }
      }
    ]
  }
}
```

The system also records the review status in `validation_report.json`:

```json
{
  "review_id": "R1",
  "item_id": "397L-CAD-001",
  "resolution": {
    "status": "corrected",
    "candidate_values": [
      { "lat": 53.8123, "lon": -1.5762, "source": "manual correction from review interface" }
    ]
  }
}
```

After review, the system recalculates the quality score and regenerates `mapem.json` / `mapem.asn1`.

### Step 6: Robustness Testing with Development and Held-out Validation Sites

Robustness testing should happen after automatic extraction and `manual_review_items` generation. Robustness should not only test the six Leeds sites. It should cover different file combinations, different available fields, and different geometry complexity levels.

Output file: `robustness_summary.json`  
Related folders: `tests/`, `docs/`

Recommended split:

| Data use | Purpose | Example |
| --- | --- | --- |
| Development subset | explore parsers, field matching rules, and evidence fusion | part of Leeds + part of DCIS/Bathnes |
| Held-out validation subset | not used for rule development; used to test generality and robustness | remaining typical sites |

Development data should cover:

| Combination type | Representative data | Why it is needed |
| --- | --- | --- |
| signal spec PDF + DWG | Leeds sites | baseline specification + CAD pipeline |
| config PDF + UTC form DOCX + drawing PDF + DWG zip | DCIS/Bathnes sites | multi-file and multi-format facts |
| pedestrian / Toucan / Puffin crossing | 397L, 378L, 1084, 5062 | simpler sites with pedestrian phases |
| bus gate / shuttle | 1013 | restrictions, special movements, non-standard layout |
| multi-stream junction | 1062, 950L | streams, stages, signalGroup mapping |
| roundabout | 573L, 337L | complex `connectsTo` and internal lanes |
| MOVA / SCOOT rich site | 1003, 5040, 1084 | control logic and detector evidence |

Leeds sites can remain a complexity baseline:

1. `397L`: simplest, Toucan, 1 stream, 2 stages.
2. `378L`: Toucan, but with more PDF template and MOVA content.
3. `982L`: 3-way junction, 8 phases, puffin + all-red demand.
4. `950L`: MOVA/VA, puffin upgrade, dummy phases, hurry call.
5. `573L`: roundabout, 5 streams.
6. `337L`: largest roundabout, 8 streams, 24 stages.

Additional DCIS/Bathnes data expands file-combination coverage:

1. `1084`: Puffin pedestrian crossing, with config PDF, UTC form, drawing PDF, MOVA Tools Report, DWG zip.
2. `5062`: pedestrian crossing, with PTC-1 config, UTC form, as-built drawing, MOVA drawing, MOVA file, DWG zip.
3. `1013`: Bus Gate / Shuttle, with config PDF, UTC form, as-built drawing, RAM data, DWG zip.
4. `1003`: London Rd / Cleveland Place, with SCOOT, config PDF, UTC form, drawing, DWG xrefs.
5. `1062`: London Rd / Morrisons, multi-stream, with SCOOT detectors, config PDF, UTC form, DWG zip.
6. `5040`: A37 / A39 White Cross, with MOVA drawing, MOVA file, UTC form, config PDF, DWG zip.

This design helps evaluate:

- whether MAPEM-relevant fact extraction is stable across file formats
- whether field matching is accurate when the same file format contains different semantic content
- whether CAD geometry extraction is stable across DWG layer styles and xref structures
- whether `connectsTo.signalGroup` remains clear as stream / stage / phase complexity increases
- whether complex roundabout geometry needs additional rules
- whether evidence fusion produces useful confidence and manual review items when sources conflict
- whether `manual_review_items` increase significantly with complexity

Robustness measures stability across site types and file combinations:

| Robustness metric | Meaning |
| --- | --- |
| site_success_rate | how many validation sites can produce a valid `SiteModel` |
| average_quality_score | average quality score across validation sites |
| worst_site_score | lowest site score, to prevent averages hiding failures |
| score_variance | variation in scores across sites |
| field_matching_error_count | number of incorrect or failed fact-to-field matches |
| parser_failure_count | number of PDF/DOCX/CAD/GIS parser failures |
| evidence_conflict_count | number of evidence conflicts across files |
| manual_intervention_rate | average number of manual corrections per site |
| complexity_drop | score drop from simple pedestrian crossing to roundabout / multi-stream site |

### Step 7: Conversion Quality Scoring

Success should not be judged only by whether `mapem.json` / `mapem.asn1` can be generated. Each site should produce a `validation_report.json` with a 0-100 quality score.

Output file: `validation_report.json`  
Related folders: `src/mapemgen/validation/`, `docs/`

```text
conversion_quality_score
|
+-- file_readability_score       whether files can be read and routed to parsers
+-- fact_extraction_score        whether MAPEM-relevant facts are extracted
+-- field_matching_score         quality of extracted facts to MAPEM fields matching
+-- fusion_consistency_score     evidence fusion and conflict handling quality
+-- sitemodel_completeness_score completeness of required SiteModel fields
+-- geometry_score               geometry quality
+-- semantic_score               phase / movement / signalGroup semantic correctness
+-- manual_effort_score          cost of manual correction
```

`conversion_quality_score` is a single-site 0-100 score. `robustness_score` should not be included in the single-site quality score. Cross-site robustness is reported separately in Step 6 through `robustness_summary.json`.

Suggested weights:

| Score item | Weight | What it measures | Main evidence |
| --- | ---: | --- | --- |
| File readability | 10% | whether input files are found, readable, and routed to suitable parsers | `site_inventory.partial.json`, parser availability, file read errors |
| Fact extraction | 15% | whether MAPEM-relevant facts are extracted | `extracted_facts.partial.json`, parser failures, missing fact types |
| Field matching | 15% | whether extracted facts are correctly matched to MAPEM fields | `mapped_evidence.partial.json`, unmatched facts, matching rules |
| Fusion consistency | 10% | whether evidence is fused correctly and conflicts are identified | candidate values, confidence, manual review items |
| SiteModel completeness | 15% | whether required MAPEM fields are populated | `mapData`, `intersections`, `laneSet`, `nodeList`, `connectsTo`, `signalGroup` |
| Geometry quality | 15% | whether lane geometry is accurate, continuous, and correctly directed | DXF geometry, spot checks, original CAD comparison |
| Semantic quality | 10% | whether movement, phase, and signalGroup mapping is correct | PDF/DOCX stage/phase facts, phase labels, checks |
| Manual effort | 10% | amount of manual correction required | `manual_review_items`, severity, manual overrides, review time |

Cross-site robustness is reported separately and does not contribute to the single-site 100-point score. This keeps two questions separate: the quality of one site's conversion, and whether the pipeline is stable across different sites.

Single-site score interpretation:

```text
90-100  High quality: close to production-grade output
75-89   Usable: main structure is correct, with limited manual checking
60-74   Partially usable: suitable for research demonstration, but key fields need correction
<60     Unreliable: should be treated as a failure case
```

Suggested final per-site report:

| Site | Dataset | Type | File coverage | Quality score | Main deductions | Manual effort | Robustness observation |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| 397L | Leeds | Toucan | spec PDF + DWG | TBD | TBD | TBD | MVP baseline |
| 378L | Leeds | Toucan | spec PDF + DWG | TBD | TBD | TBD | PDF template comparison |
| 982L | Leeds | 3-way junction | spec PDF + DWG | TBD | TBD | TBD | puffin / all-red demand |
| 337L | Leeds | Large roundabout | spec PDF + DWG | TBD | TBD | TBD | stress test |
| 1084 | DCIS/Bathnes | Puffin crossing | config PDF + UTC form + drawing PDF + MOVA report + DWG zip | TBD | TBD | TBD | multi-file baseline |
| 1013 | DCIS/Bathnes | Bus Gate / Shuttle | config PDF + UTC form + as-built drawing + RAM + DWG zip | TBD | TBD | TBD | restriction / special layout |
| 1062 | DCIS/Bathnes | Multi-stream junction | config PDF + UTC form + SCOOT detectors + DWG zip | TBD | TBD | TBD | multi-stream stage mapping |
| 5040 | DCIS/Bathnes | MOVA junction | config PDF + UTC form + MOVA drawing + MOVA file + DWG zip | TBD | TBD | TBD | MOVA / detector evidence |

This allows the project to answer:

1. How good is the MAPEM conversion for each individual site?
2. Is the method robust across site types, file combinations, available fields, and geometry complexity?

## 2. Weekly Plan

The project progresses on three parallel lines:

- Data line: Leeds + DCIS/Bathnes file inventory, file-format extraction, training / validation split, site-by-site testing.
- Prototype line: Python package, file parsers, MAPEM field matching, evidence fusion, SiteModel, MAPEM output, validation report, review interface.
- Report line: MAPEM requirements, field-source matrix, methodology, per-site quality metrics, robustness analysis, case study evidence, final recommendations.

### Timeline Summary

| Week | Dates | Main Focus | Related Plan Steps | Main Outputs |
| --- | --- | --- | --- | --- |
| Week 0 | 11-19 May 2026 | Project understanding, MAPEM requirements, Leeds data inventory | Preparation, Step 1 | MAPEM requirement notes, Leeds data inventory, first project plan |
| Week 1 | 20-26 May 2026 | Update engineering workflow, confirm MVP scope and parser architecture | Step 1, Step 2 preparation | file inventory design, MVP data scope, repository scaffold, parser design |
| Week 2 | 25-31 May 2026 | Automatic file inventory and file-format facts extraction | Step 1, Step 2 | `site_inventory.partial.json`, `extracted_facts.partial.json`, parser failure notes |
| Week 3 | 1-7 June 2026 | MAPEM field matching, field-source matrix, evidence fusion, and MAPEM generator | Step 3, Step 4 | `mapped_evidence.partial.json`, `field_source_matrix.md`, first `site_model.json`, `mapem.json`, `mapem.asn1` |
| Week 4 | 8-14 June 2026 | Validation report, manual review workflow, single-site quality score | Step 5, Step 7 | `validation_report.json`, `manual_review_items`, per-site quality score |
| Week 5 | 15-21 June 2026 | Held-out robustness testing and failure-case analysis | Step 6 | `robustness_summary.json`, per-site comparison, case study evidence, report draft |
| Final Week | 22-26 June 2026 | Final polish, submission, presentation and poster | All steps | final report, prototype package, slides, poster, demo outputs |

### Week 0: 11-19 May 2026

**Theme:** Project understanding, MAPEM requirements, and Leeds data inventory.

| Area | Work |
| --- | --- |
| Main goal | Understand what MAPEM requires and what Leeds data is available. |
| Key tasks | Read MAPEM/SPATEM reference material; distinguish `mapem.asn1`, `mapem.json`, and `validation_report.json`; inventory six Leeds sites; identify site type, PDF/DWG availability, streams, stages, phases, and complexity. |
| Prototype focus | Establish the initial repository structure and define the first `SiteModel` shape. |
| Report focus | Prepare MAPEM data requirement notes and Leeds site data inventory notes. |
| Deliverables | MAPEM requirements document, Leeds site data inventory, first project plan, client questions list. |

### Week 1: 20-26 May 2026

**Theme:** Update the engineering workflow, define MVP scope, and prepare extraction architecture.

| Area | Work |
| --- | --- |
| Main goal | Move from a direct PDF/CAD-to-MAPEM approach to a file inventory -> file-format facts extraction -> MAPEM field matching -> evidence fusion -> validation workflow. |
| Key tasks | Review Leeds + DCIS/Bathnes data; define file inventory fields such as `file_path`, `file_type`, filename keywords, and parser availability; define which MAPEM-relevant facts each parser can extract in version one; choose development subset and held-out validation subset; keep `397L` as the simple MVP baseline. |
| Prototype focus | Prepare ingestion module boundaries: PDF parser, DOCX parser, CAD/DXF parser, ZIP parser, RAM/TXT parser, GIS parser, field matcher, generators, validation. |
| Report focus | Explain why the project extracts facts before matching MAPEM fields; explain that file inventory is generated from file path, extension, and filename keywords. |
| Deliverables | file inventory design, parser module plan, updated project plan, first quality metric design. |

### Week 2: 25-31 May 2026

**Theme:** File-format extraction and first MAPEM-relevant facts.

| Area | Work |
| --- | --- |
| Main goal | Automatically build file inventory and extract MAPEM-relevant facts by file format. |
| Key tasks | Generate `site_inventory.partial.json` for Leeds + DCIS/Bathnes sites; extract facts from PDF, DOCX, CAD/DXF, ZIP, TXT/8TX, and GIS: phases, stages, streams, intergreens, signalGroup candidates, lane geometry, stop lines, crossings, signal heads, detector/control notes; record parser failures and low-confidence facts. |
| Prototype focus | Generate `site_inventory.partial.json` and `extracted_facts.partial.json`; keep source file, evidence location, and confidence for each fact. |
| Report focus | Document file-format extraction method, limitations, and cases where the same format produces different fact types. |
| Deliverables | site inventory files, extracted facts, parser failure notes, low-confidence fact examples. |

### Week 3: 1-7 June 2026

**Theme:** Field-source matrix, evidence fusion, and MAPEM generator.

| Area | Work |
| --- | --- |
| Main goal | Match extracted facts to MAPEM fields, generate a field-source matrix, and use evidence fusion to create the first `SiteModel` and MAPEM outputs. |
| Key tasks | Build fact type -> MAPEM field matching rules; match lane candidates, stop lines, crossings, signal heads, and phase/stage facts to `refPoint`, `laneSet`, `nodeList`, `connectsTo`, `signalGroup`; generate `mapped_evidence.partial.json` and `field_source_matrix.md`; identify CRS/refPoint issues; build lane-level geometry. |
| Prototype focus | Use `mapped_evidence.partial.json` for evidence fusion, then generate first `site_model.json`, `mapem.json`, and `mapem.asn1` drafts. |
| Report focus | Explain extracted facts, field-source matrix, `NodeXY`, `laneSet`, `connectsTo`, `signalGroup`, SiteModel, and MAPEM output relationship. |
| Deliverables | mapped evidence, field-source matrix, first SiteModel, first MAPEM JSON, first ASN.1-style output. |

### Week 4: 8-14 June 2026

**Theme:** Validation report, low-confidence review, and quality scoring.

| Area | Work |
| --- | --- |
| Main goal | Make the prototype explain each site's conversion quality and which items need human review. |
| Key tasks | Generate `validation_report.json`; check `site_inventory.partial.json`, `extracted_facts.partial.json`, `mapped_evidence.partial.json`, `field_source_matrix.md`, and `site_model.json`; add errors, warnings, scores, and `manual_review_items`; define `review_id`, `current_value`, `candidate_values`, evidence location, confidence, and suggested action; design the review interface workflow using `accept` and `correct`. |
| Prototype focus | Implement validation checks for file readability, fact extraction, field matching, fusion consistency, SiteModel completeness, lane references, signalGroup references, geometry confidence, and manual review item generation. |
| Report focus | Define the per-site quality scoring system and explain why `validation_report.json` is separate from `mapem.json` / `mapem.asn1`. |
| Deliverables | `validation_report.json`, manual review item format, per-site quality score, review interface workflow. |

### Week 5: 15-21 June 2026

**Theme:** Robustness testing across site types and report drafting.

| Area | Work |
| --- | --- |
| Main goal | Test whether the fixed pipeline remains effective across different site types and file combinations. |
| Key tasks | Use the development subset to adjust rules and the held-out validation subset to test; cover Leeds PDF+DWG and DCIS/Bathnes config PDF+UTC form+drawing PDF+DWG zip+RAM/MOVA; compare site success rate, parser failure count, field matching error count, evidence conflict count, manual intervention rate, worst site score, and score variance. |
| Prototype focus | Generate `robustness_summary.json` and record parser, field matching, and fusion rule limitations from failure cases. |
| Report focus | Draft case studies, file coverage analysis, robustness analysis, quality metrics, limitations, and recommendations. |
| Deliverables | `robustness_summary.json`, per-site quality table, case study outputs, 60-80% report draft. |

### Final Week: 22-26 June 2026

**Theme:** Final polish, submission, presentation, and poster.

| Area | Work |
| --- | --- |
| Main goal | Finalise the prototype, evidence, report, presentation, and poster. |
| Key tasks | Freeze the final pipeline; organise demo outputs; finalise `site_model.json`, `mapem.json`, `mapem.asn1`, `validation_report.json`, `robustness_summary.json`, and quality scoring evidence; polish the final report; prepare demo narrative and poster. |
| Prototype focus | Clean README, run final tests, package reproducible examples and demo outputs. |
| Report focus | Complete final report, reflective report, appendix, figures, tables, references, and recommendations. |
| Deliverables | Final project report, reflective report, prototype package, demo outputs, final slides, poster. |

## 3. Key Conclusions

1. PDF, DOCX, DWG, DXF, GIS, and LiDAR are input formats, not final MAPEM semantics. The same PDF may produce phase/stage facts or drawing/layout facts.
2. MAPEM geometry fields mainly depend on geometry facts, such as `laneSet`, `nodeList`, stop lines, and signal head locations.
3. MAPEM control semantics mainly depend on phase/stage/control facts, such as stages, phases, streams, and `connectsTo.signalGroup`.
4. The pipeline should first extract MAPEM-relevant facts by file format, then match facts to MAPEM fields, and finally use evidence fusion to generate `SiteModel`.
5. Conversion quality should measure file readability, fact extraction, field matching, fusion consistency, SiteModel completeness, geometry, semantic quality, manual effort, and robustness.
6. Leeds plus part of DCIS/Bathnes should be used as the development subset, while remaining typical sites should be used for held-out validation to test generality and robustness.
