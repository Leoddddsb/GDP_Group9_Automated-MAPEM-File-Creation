# Project Plan

This document defines the planned workflow for automated MAPEM file creation from Leeds City Council site data. It covers the extraction pipeline, validation and manual review process, robustness testing, quality scoring, and weekly delivery plan.

## 1. Planned Workflow

Overview:

| Step | Purpose | Output File | Current Repository Area |
| --- | --- | --- | --- |
| Step 1 | Build a basic inventory for each site | `site_inventory.partial.json` | `configs/`, `src/mapemgen/ingestion/` |
| Step 2 | Extract phase / stage / stream tables from PDFs | `phase_logic.partial.json` | `src/mapemgen/ingestion/` |
| Step 3 | Convert DWG to DXF and extract CAD geometry | `site.dxf`, `cad_geometry.partial.json` | `src/mapemgen/ingestion/`, `configs/` |
| Step 4 | Automatically convert data into a MAPEM-style SiteModel and MAPEM outputs | `site_model.json`, `mapem.json`, `mapem.asn1` | `src/mapemgen/`, `src/mapemgen/generators/`, `schemas/` |
| Step 5 | Validate the output and generate low-confidence review items | `validation_report.json` | `src/mapemgen/validation/` |
| Step 6 | Test robustness across the six Leeds sites | `robustness_summary.json` | `tests/`, `docs/` |
| Step 7 | Calculate conversion quality scores | `validation_report.json` | `src/mapemgen/validation/`, `docs/` |

### Step 1: Build Site Inventory

For each site, generate a local `site_inventory.partial.json`:

```text
site_id
site_name
pdf_path
dwg_path
pdf_pages
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

Output file: `site_inventory.partial.json`  
Related folders: `configs/`, `src/mapemgen/ingestion/`

### Step 2: PDF Table Extraction

Extract the following tables from signal specification PDFs:

- `USE OF PHASES`
- `USE OF STAGES - STAGE/PHASE RELATIONSHIP`
- `PHASES CONFLICTING/OPPOSING PHASES`
- `PHASE INTERGREEN TIMES`
- `BASIC STAGE DATA`

Expected output:

```text
phase_logic.partial.json
|
+-- phases
+-- phase_types
+-- stages
+-- stage_to_phase
+-- conflicts
+-- intergreens
+-- streams
```

Output file: `phase_logic.partial.json`  
Related folder: `src/mapemgen/ingestion/`

### Step 3: Convert DWG to DXF and Extract Geometry

DWG is not a stable direct parsing format for the project pipeline. The first practical step is to convert DWG files to DXF using ODA File Converter.

The CAD parser should then extract:

- lane centrelines
- stop lines
- kerbs / road edges
- signal poles / heads
- pedestrian crossings
- road names / labels
- layer names

Expected output:

```text
cad_geometry.partial.json
|
+-- refPoint candidate
+-- lane candidates
+-- stop line candidates
+-- signal head candidates
+-- crossing candidates
+-- layer evidence
```

Output files: `site.dxf`, `cad_geometry.partial.json`  
Related folders: `src/mapemgen/ingestion/`, `configs/`

### Step 4: Automatic Data Conversion to MAPEM-style SiteModel

Automatic conversion logic:

```text
PDF phase/stage data
        |
        +-- signalGroup / movement control

CAD/DXF geometry
        |
        +-- laneSet / nodeList / signalHeadLocations

site config / defaults
        |
        +-- site ID / default lane width / configured CRS

automatic conversion result
        |
        +-- SiteModel
            |
            +-- mapData
                |
                +-- intersections
                    |
                    +-- IntersectionGeometry
                        |
                        +-- laneSet
                            |
                            +-- GenericLane
```

Output files: `site_model.json`, `mapem.json`, `mapem.asn1`

This step produces the first automatic conversion result. It has not yet gone through the low-confidence checks or manual review process in Step 5.

`site_model.json` is the first internal intermediate model. `mapem.json` and `mapem.asn1` are initial MAPEM drafts generated from that first `site_model.json`. After manual review, the updated MAPEM outputs need to be regenerated.

Conversion from `site_model.json` to `mapem.json` / `mapem.asn1`:

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

The current `SiteModel` is already close to the MAPEM hierarchy, so the first conversion may look like a direct export. Conceptually, they remain different:

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

`validation_report.json` is generated in this step. It reads the `site_model.json` / `SiteModel` produced in Step 4 and checks completeness, geometry consistency, semantic mapping, low-confidence fields, and locations requiring manual review.

Output file: `validation_report.json`  
Related folder: `src/mapemgen/validation/`

`validation_report.json` is a structured JSON report. It should approximately contain:

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
    "completeness_score": 88,
    "geometry_score": 76,
    "semantic_score": 82,
    "consistency_score": 90,
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

`manual_review_items` is a list inside `validation_report.json`. It stores low-confidence fields, extraction failures, conflicts, and any items that require manual confirmation.

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
| PDF table extraction failed | `connectsTo.signalGroup`, `maneuvers`, stage/phase metadata | Missing `USE OF PHASES`, missing `USE OF STAGES`, abnormal table row count, missing phase labels | PDF file name, page number, failed table name, raw text snippet | High |
| PDF stage/phase table conflicts with phase list | `signalGroup`, `maneuvers` | A phase appears in a stage table but not in `USE OF PHASES`, or the reverse | Conflicting phase label and table page | High |
| Coordinate system is unclear | `refPoint`, `nodeList.nodes`, `signalHeadLocations` | DXF lacks recognisable georeference or coordinate range does not match WGS84 / local grid | CAD file name, coordinate range, CRS evidence | High |
| DWG has no georeference | `refPoint`, all geometry offsets | No EPSG, world file, or known control point | Need user to select `refPoint` or provide control points | High |
| CAD symbol layer is inconsistent or unrecognised | `signalHeadLocations`, signal head to `signalGroup` mapping | Layer rules fail to match signal head / pole symbols, or similar symbols appear on unknown layers | Unmatched layer names, symbol count, candidate object coordinates | Medium-high |
| Lane centreline is broken or too short | `GenericLane.nodeList.nodes` | Polyline too short, too few nodes, or large gaps between segments | Lane candidate ID, coordinates, CAD layer | High |
| Lane direction is uncertain | `ingressApproach`, `egressApproach`, `connectsTo` | Polyline direction conflicts with approach, stop line, or movement inference | Candidate direction, road label, stop line location | Medium-high |
| `connectsTo` has multiple candidate target lanes | `GenericLane.connectsTo` | One ingress lane matches multiple downstream lanes with similar scores | Source lane, candidate target lanes, confidence values | High |
| Movement inference is uncertain | `maneuvers`, `connectsTo.connectingLane.maneuver` | Geometry angle conflicts with PDF stage arrow or phase description | left/straight/right candidates, angle, PDF evidence | High |
| `signalGroup` cannot be matched to lane movement | `connectsTo.signalGroup` | Phase label exists but cannot be matched to lane connection | Phase label, PDF location, candidate lanes | High |
| `signalGroup` is shared by conflicting movements | `connectsTo.signalGroup`, consistency checks | Conflict matrix shows conflicting phases but mapping assigns shared movement group | Conflicting phase labels, affected lanes, conflict table location | High |
| Stop line cannot be recognised | lane start/end, approach assignment | Layer rules cannot find stop line, or stop line is too far from lane endpoint | Candidate lane, nearest stop line distance, layer evidence | Medium |
| Pedestrian crossing geometry is missing | pedestrian lanes / crossings, `signalHeadLocations` | PDF has pedestrian / puffin phase but CAD has no crossing geometry | Phase label, PDF location, missing CAD evidence | Medium |
| Roundabout internal lanes cannot be connected reliably | `laneSet`, `connectsTo` | Internal roundabout lanes cannot be matched uniquely to entry/exit lanes | Affected stream, candidate lanes, matching score | High |
| Speed limit is missing | `speedLimits` | Not found in PDF/GIS/OSM | Site ID and missing field | Low |
| Restrictions are missing | `restrictionList` | Not extracted from PDF notes or CAD markings | Site ID and missing field | Low-medium |

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

The preferred manual review method is an interface that writes review feedback back into `SiteModel`. The client should not edit JSON in a terminal.

Review workflow:

```text
1. Automatic conversion
   PDF + DWG -> SiteModel -> mapem.json / mapem.asn1

2. Automatic validation
   Generate validation_report.json
   List low-confidence / manual_review_items

3. Client reviews items in the interface
   Each item shows:
   - what the issue is
   - which MAPEM field is affected
   - system candidate value
   - confidence
   - PDF page / CAD layer / coordinate evidence

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

The review interface should summarise `manual_review_items` for the client rather than exposing raw JSON. The client should see each `review_id`, the issue, the affected MAPEM field, the candidate value, confidence, PDF/CAD evidence, and suggested action.

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

### Step 6: Robustness Testing by Site Complexity

After automatic extraction and `manual_review_items` generation, the pipeline should be tested across sites in increasing complexity. Robustness measures whether the conversion process remains stable across different site types after low-confidence review.

Output file: `robustness_summary.json`  
Related folders: `tests/`, `docs/`

Recommended order:

1. `397L`: simplest, Toucan, 1 stream, 2 stages.
2. `378L`: Toucan, but with more PDF template and MOVA content.
3. `982L`: 3-way junction, 8 phases, puffin + all-red demand.
4. `950L`: MOVA/VA, puffin upgrade, dummy phases, hurry call.
5. `573L`: roundabout, 5 streams.
6. `337L`: largest roundabout, 8 streams, 24 stages.

This order helps evaluate:

- whether the PDF parser remains stable across site types
- whether the CAD parser remains stable across layer styles
- whether `connectsTo.signalGroup` remains understandable as stream / stage / phase complexity increases
- whether roundabout geometry requires additional rules
- whether the number and severity of `manual_review_items` increases with complexity

Robustness is not only a single-site score. It measures stability across all six sites:

| Robustness metric | Meaning |
| --- | --- |
| site_success_rate | How many of the six sites can produce a valid `SiteModel` |
| average_quality_score | Average quality score across all six sites |
| worst_site_score | Lowest site score, to prevent averages hiding failures |
| score_variance | Variation in scores across sites |
| parser_failure_count | Number of PDF/CAD parser failures |
| manual_intervention_rate | Average amount of manual review needed per site |
| complexity_drop | Score drop from `397L` to `337L` as complexity increases |

### Step 7: Conversion Quality Scoring

The project should not judge success only by whether `mapem.json` / `mapem.asn1` can be generated. Each site should produce a `validation_report.json` with a 0-100 quality score.

Output file: `validation_report.json`  
Related folders: `src/mapemgen/validation/`, `docs/`

```text
conversion_quality_score
|
+-- completeness_score
+-- geometry_score
+-- semantic_score
+-- consistency_score
+-- provenance_score
+-- manual_effort_score
+-- robustness_score
```

Suggested weights:

| Score item | Weight | What it measures | Main evidence |
| --- | ---: | --- | --- |
| Completeness | 20% | Whether required MAPEM fields are populated | `mapData`, `intersections`, `laneSet`, `nodeList`, `connectsTo`, `signalGroup` |
| Geometry quality | 25% | Whether lane geometry is accurate, continuous, and correctly directed | DXF geometry, manual spot checks, CAD comparison |
| Semantic quality | 25% | Whether movement, phase, and signalGroup mapping is correct | PDF stage/phase tables, phase labels, manual checks |
| Internal consistency | 10% | Whether the data is internally coherent | unique lane IDs, valid `connectsTo`, valid `signalGroup` references |
| Provenance | 10% | Whether each field has an identifiable source | CAD layer, PDF page/table, manual override records |
| Manual effort | 10% | Amount of manual correction required | `manual_review_items`, severity, manual overrides, review time |

Single-site score interpretation:

```text
90-100  High quality: close to production-grade output
75-89   Usable: main structure is correct, with limited manual checking
60-74   Partially usable: suitable for research demonstration, but key fields need correction
<60     Unreliable: should be treated as a failure case
```

Suggested final per-site report:

| Site | Type | Streams | Stages | Quality score | Main deductions | Manual effort | Robustness observation |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| 397L | Toucan | 1 | 2 | TBD | TBD | TBD | MVP baseline |
| 378L | Toucan | 1 or template 1-4 | 0-2 | TBD | TBD | TBD | PDF template comparison |
| 982L | 3-way junction | template 1-4 | 0,1,2,5,6 | TBD | TBD | TBD | puffin / all-red demand |
| 950L | Signal junction | template 1-4 | 1-6 | TBD | TBD | TBD | dummy phase / hurry call |
| 573L | Roundabout | 5 | 0-12 | TBD | TBD | TBD | multi-stream roundabout |
| 337L | Large roundabout | 8 | 1-24 | TBD | TBD | TBD | stress test |

This allows the project to answer:

1. How good is the MAPEM conversion for each individual site?
2. Is the method robust across site types, PDF templates, and geometry complexity?

## 2. Weekly Plan

The project progresses on three parallel lines from the start:

- Data line: Leeds site data inventory, PDF/DWG extraction, site-by-site testing.
- Prototype line: Python package, SiteModel, MAPEM output, validation report, review interface.
- Report line: requirements, methodology, quality metrics, case study evidence, final recommendations.

### Timeline Summary

| Week | Dates | Main Focus | Related Plan Steps | Main Outputs |
| --- | --- | --- | --- | --- |
| Week 0 | 11-19 May 2026 | Project understanding, MAPEM requirements, data inventory | Step 1 | MAPEM requirement notes, Leeds data inventory, first project plan |
| Week 1 | 20-26 May 2026 | Confirm MVP scope and repository structure | Step 1, Step 2 preparation | MVP data scope, repository scaffold, parser design |
| Week 2 | 25-31 May 2026 | PDF extraction and first automatic `SiteModel` skeleton | Step 1, Step 2, Step 4 skeleton | `site_inventory.partial.json`, `phase_logic.partial.json`, first `site_model.json` |
| Week 3 | 1-7 June 2026 | CAD/DXF geometry extraction and MAPEM generator | Step 3, Step 4 | `cad_geometry.partial.json`, first `mapem.json`, first `mapem.asn1` |
| Week 4 | 8-14 June 2026 | Validation report, review interface logic, quality checks | Step 5, Step 7 | `validation_report.json`, `manual_review_items`, quality score draft |
| Week 5 | 15-21 June 2026 | Multi-site robustness testing and report drafting | Step 6, Step 7 | robustness results, case study comparison, report draft |
| Final Week | 22-26 June 2026 | Final polish, submission, presentation and poster | All steps | final report, prototype package, slides, poster, demo outputs |

### Week 0: 11-19 May 2026

**Theme:** Project understanding, MAPEM requirements, and Leeds data inventory.

| Area | Work |
| --- | --- |
| Main goal | Understand what MAPEM requires and what Leeds data is available. |
| Key tasks | Read MAPEM/SPATEM reference material; distinguish `mapem.asn1`, `mapem.json`, and `validation_report.json`; inventory all six Leeds sites; identify site type, PDF/DWG availability, streams, stages, phases, and complexity. |
| Prototype focus | Establish the initial repository structure and define the first `SiteModel` shape. |
| Report focus | Prepare MAPEM data requirement notes and Leeds site data inventory notes. |
| Deliverables | MAPEM requirements document, Leeds site data inventory, first project plan, client questions list. |

### Week 1: 20-26 May 2026

**Theme:** Define MVP scope and prepare the extraction architecture.

| Area | Work |
| --- | --- |
| Main goal | Define what the first working automated conversion prototype should produce. |
| Key tasks | Select the first MVP site, prioritising `397L`; define minimum required MAPEM fields; clarify the roles of PDF, DWG/DXF, config/defaults, and manual review; align repository folders with project modules. |
| Prototype focus | Prepare ingestion module boundaries: PDF tables, CAD/DXF, GIS/refPoint, generators, validation. |
| Report focus | Explain the conversion pipeline and why PDF and CAD must be combined. |
| Deliverables | MVP field list, parser module plan, updated project plan, first quality metric design. |

### Week 2: 25-31 May 2026

**Theme:** PDF extraction and first automatic `SiteModel` skeleton.

| Area | Work |
| --- | --- |
| Main goal | Extract real signal-control information from Leeds PDF specs and produce the first structured site model. |
| Key tasks | Build `site_inventory.partial.json` for all six sites; parse `USE OF PHASES`, `USE OF STAGES`, conflict tables, intergreen tables, and stream/stage metadata; prioritise `397L`; record parser failures and low-confidence PDF fields. |
| Prototype focus | Generate `phase_logic.partial.json` and the first `site_model.json` skeleton for `397L`. |
| Report focus | Document PDF table extraction method, limitations, and fields obtained from PDF. |
| Deliverables | Site inventory files, phase logic extraction output, first `site_model.json`, PDF extraction notes. |

### Week 3: 1-7 June 2026

**Theme:** CAD/DXF geometry extraction and MAPEM generator.

| Area | Work |
| --- | --- |
| Main goal | Extract or prepare lane geometry and convert the first `SiteModel` into MAPEM-style outputs. |
| Key tasks | Convert DWG to DXF; inspect CAD layers; extract lane candidates, stop lines, crossings, signal heads, and text labels; identify CRS/refPoint issues; build `nodeList` and lane-level geometry; connect geometry with PDF phase/stage data. |
| Prototype focus | Produce `cad_geometry.partial.json`, first `mapem.json`, and first `mapem.asn1` draft from `site_model.json`. |
| Report focus | Explain geometry extraction, `NodeXY`, `laneSet`, `connectsTo`, and `signalGroup` mapping. |
| Deliverables | CAD geometry extraction output, first MAPEM JSON, first ASN.1-style output, geometry extraction method notes. |

### Week 4: 8-14 June 2026

**Theme:** Validation report, low-confidence review, and quality scoring.

| Area | Work |
| --- | --- |
| Main goal | Make the prototype explain which conversion results are reliable and which items need human review. |
| Key tasks | Generate `validation_report.json`; add errors, warnings, scores, and `manual_review_items`; define `review_id`, `current_value`, `candidate_values`, evidence location, confidence, and suggested action; design the review interface workflow using `accept` and `correct`. |
| Prototype focus | Implement validation checks for completeness, lane references, signalGroup references, geometry confidence, and manual review item generation. |
| Report focus | Define the quality scoring system and explain why the validation report is separate from MAPEM output. |
| Deliverables | `validation_report.json`, manual review item format, quality score draft, review interface workflow. |

### Week 5: 15-21 June 2026

**Theme:** Robustness testing across site types and report drafting.

| Area | Work |
| --- | --- |
| Main goal | Test whether the conversion method remains useful across different Leeds site types. |
| Key tasks | Run the pipeline in complexity order: `397L`, `378L`, `982L`, `950L`, `573L`, `337L`; compare parser success, missing fields, manual review count, geometry quality, semantic quality, and overall score; improve fallback rules. |
| Prototype focus | Generate a robustness summary and improve the pipeline based on failure cases. |
| Report focus | Draft case studies, robustness analysis, quality metrics, limitations, and recommendations. |
| Deliverables | Robustness summary, per-site quality table, case study outputs, 60-80% report draft. |

### Final Week: 22-26 June 2026

**Theme:** Final polish, submission, presentation, and poster.

| Area | Work |
| --- | --- |
| Main goal | Finalise the prototype, evidence, report, presentation, and poster. |
| Key tasks | Freeze the final pipeline; package demo outputs; finalise `mapem.json`, `mapem.asn1`, `validation_report.json`, robustness summary, and quality scoring evidence; polish the final report; prepare demo narrative and poster. |
| Prototype focus | Clean README, run final tests, package reproducible examples and non-confidential outputs. |
| Report focus | Complete final report, reflective report, appendix, figures, tables, references, and recommendations. |
| Deliverables | Final project report, reflective report, prototype package, demo outputs, final slides, poster. |

## 3. Key Conclusions

1. All six sites currently have both PDF and DWG sources.
2. PDFs provide signal specification information, including stages, phases, streams, conflicts, intergreens, and controller notes.
3. DWG is the main source for MAPEM geometry, especially `laneSet`, `nodeList`, stop lines, and signal head locations.
4. PDF alone cannot generate complete MAPEM because it does not reliably provide lane centreline geometry.
5. CAD alone cannot generate complete MAPEM because it usually does not reliably describe stage/phase/signalGroup control relationships.
6. Conversion quality must be measured through a scoring system, not only by whether output files are generated.
7. The first MVP should use `397L`; `337L` should be kept as the final robustness stress test.
