# Site Inventory Scoring Method and Worked Example

## Purpose

This scoring method ranks MAPEM source-data sites from simple to complex while also measuring how complete each site's evidence is.

Use two independent 0-100 scores:

- **Completeness Score**: how much useful evidence is present and machine-usable.
- **Complexity Score**: how difficult the site is likely to be for parser development, geometry extraction, and MAPEM assembly.

The scores are heuristics for dataset selection. They are not traffic-engineering validation results.

## Recommended Dataset Use

For software development, use a balanced set:

- **Development/test set**: sites with high completeness and low-to-medium complexity. These are good for building parsers and checking repeatability.
- **Validation set**: sites with high completeness and medium-to-high complexity. These should be held back until the software is stable.
- **Stress set**: sites with low completeness, high ambiguity, scanned PDFs, unclear CAD roots, MOVA/proprietary files, or conflicting evidence.

## Completeness Score

Completeness measures whether the site contains the source material needed to build MAPEM data.

Maximum score: **100**

| Category | Max | Scoring rule |
|---|---:|---|
| Source coverage | 25 | CAD/layout evidence, signal/control evidence, detector evidence, timing/override evidence, and site metadata |
| Machine readability | 20 | Whether core files have parser routes and key evidence is readable without manual conversion |
| Extracted control model | 25 | Controller type, SCN/IP/config metadata, streams, stages, phases, and SCOOT/link evidence |
| Geometry readiness | 20 | DXF/root CAD availability, supporting DWG/overlay files, drawing PDFs, and low root-drawing ambiguity |
| QA / uncertainty | 10 | Inventory confidence and number of unresolved manual questions |

Detailed scoring:

### 1. Source Coverage, 25 points

| Evidence | Points |
|---|---:|
| CAD/layout source present, preferably DXF or DWG | 7 |
| Signal/control source present, such as UTC Form or controller config | 7 |
| Detector/SCOOT source present | 4 |
| Timing/override source present, such as RAM data | 4 |
| Site metadata present, such as SCN, IP, site description, controller type | 3 |

### 2. Machine Readability, 20 points

| Evidence | Points |
|---|---:|
| Every source file has a parser route or explicit review route | 8 |
| Core control evidence is machine-readable | 4 |
| Core geometry evidence is machine-readable or already converted to DXF | 4 |
| Timing/override evidence is machine-readable text | 2 |
| Conversion burden is low | 2 |

### 3. Extracted Control Model, 25 points

| Evidence | Points |
|---|---:|
| Controller type extracted | 5 |
| Junction SCN, IP, and configuration number extracted | 5 |
| Stream count and stage count extracted | 6 |
| Phase labels extracted | 5 |
| SCOOT links or detector/link references extracted | 4 |

### 4. Geometry Readiness, 20 points

| Evidence | Points |
|---|---:|
| Root DXF or equivalent CAD geometry source available | 8 |
| Supporting DWG/overlay files available | 4 |
| Drawing PDF or layout document available | 3 |
| Root drawing ambiguity is low | 5 |

### 5. QA / Uncertainty, 10 points

| Evidence | Points |
|---|---:|
| Inventory confidence: high = 8, medium = 5, low = 2 | 8 |
| No unresolved manual questions | 2 |

## Complexity Score

Complexity measures how difficult a site is likely to be for an automated MAPEM pipeline.

Maximum score: **100**

| Category | Max | Scoring rule |
|---|---:|---|
| Junction topology | 15 | More arms, roundabouts, or unusual layouts increase complexity |
| Control method / controller | 15 | SCOOT, UTC, MOVA, adaptive, or mixed control increases complexity |
| Staging and phase complexity | 15 | More streams, stages, and phases increase complexity |
| CAD geometry/package complexity | 15 | More DWG/DXF files, overlays, xrefs, topographic drawings, or large packages increase complexity |
| Detector/SCOOT complexity | 10 | Detector tables, SCOOT links, upstream nodes, and link-stage data increase complexity |
| Special logic / timing complexity | 10 | RAM overrides, intergreens, MOVA, or proprietary logic increase complexity |
| File-format burden | 10 | Mixed PDF/DOCX/DWG/DXF/RAM packages are harder than clean text/DXF-only sites |
| Ambiguity / cleanup burden | 10 | Missing, conflicting, duplicated, or unclear evidence increases complexity |

Detailed scoring:

### 1. Junction Topology, 15 points

| Topology | Points |
|---|---:|
| Simple pedestrian crossing | 3 |
| T junction / three-arm junction | 7 |
| Four-arm junction | 10 |
| Multi-arm junction, roundabout, or large complex site | 15 |

### 2. Control Method / Controller, 15 points

| Control evidence | Points |
|---|---:|
| Unknown or no control evidence | 2 |
| UTC only | 5 |
| SCOOT + UTC | 10 |
| MOVA, adaptive, or special control | 13 |
| Mixed/proprietary/multiple controller logic | 15 |

### 3. Staging and Phase Complexity, 15 points

Use:

```text
score = min(15, 2 * stage_count + 2 * stream_count + 0.5 * phase_count)
```

### 4. CAD Geometry / Package Complexity, 15 points

| CAD evidence | Points |
|---|---:|
| One clean DXF only | 3 |
| DXF plus a small number of DWG files | 6 |
| Multiple DWGs, overlays, or topographic drawings | 10 |
| ZIP/xrefs/large CAD package with many drawings | 12 |
| Very large, messy, or conflicting CAD package | 15 |

### 5. Detector / SCOOT Complexity, 10 points

| Detector evidence | Points |
|---|---:|
| No detector data | 0 |
| Detector file present but not parsed | 4 |
| SCOOT links and detector references present | 7 |
| Detector/link-stage/upstream-node mapping is dense or multi-node | 10 |

### 6. Special Logic / Timing Complexity, 10 points

| Evidence | Points |
|---|---:|
| None visible | 0 |
| RAM data present | 4 |
| RAM/intergreen/timing differences visible | 6 |
| MOVA or proprietary control logic | 8 |
| Multiple interacting special-logic sources | 10 |

### 7. File-Format Burden, 10 points

| Evidence | Points |
|---|---:|
| Mostly text/DXF/DOCX | 2 |
| PDF tables included | 4 |
| DWG conversion needed | 6 |
| Mixed PDF/DOCX/DWG/DXF/RAM package | 8 |
| Scanned PDFs or proprietary binary files dominate | 10 |

### 8. Ambiguity / Cleanup Burden, 10 points

| Evidence | Points |
|---|---:|
| No manual questions; root evidence is clear | 0 |
| Minor ambiguity or duplicate supporting drawings | 2 |
| Root drawing or control source unclear | 5 |
| Missing or conflicting core evidence | 8 |
| Site needs substantial manual reconstruction | 10 |

## Worked Example: 1084 LBROakStPed

Inventory source:

```text
configs/1084_LBROakStPed.site_inventory.partial.json
```

Site data root:

```text
data/1084_LBROakStPed
```

Key inventory facts:

| Field | Value |
|---|---|
| site_id | 1084 |
| site_name | LBROakStPed |
| junction_type | pedestrian_crossing |
| controller_type | ST950 |
| control_method | MOVA + UTC |
| stream_count | 1 |
| stage_count | 2 |
| phase_count | 4 |
| phase_labels | O, M, A, B |
| confidence | high |
| manual_questions | 0 |
| source file count | 10 |

Source file types:

| File type | Count |
|---|---:|
| PDF | 4 |
| DOCX | 1 |
| 8TX | 1 |
| DWG | 2 |
| DXF | 1 |
| TXT | 1 |

Important extracted content:

| Extracted field | Value | Source |
|---|---|---|
| UTC junction description | Lower Bristol Rd/ Oak St Ped | 1084_UTCForm_Nov23.docx |
| Outstation SCN and type | ST950/ X02340 | 1084_UTCForm_Nov23.docx |
| Junction SCN | J02345 | 1084_UTCForm_Nov23.docx |
| IP address | 10.249.151.7 | 1084_UTCForm_Nov23.docx |
| TOPAS2500 config number | 1084 | 1084_UTCForm_Nov23.docx |
| Stream labels | single_stream | 1084_UTCForm_Nov23.docx |
| Stage count by stream | single_stream = 2 | 1084_UTCForm_Nov23.docx |
| Root CAD drawing | T1084 Oak Street Puffin.dwg | T1084 Oak Street Puffin.txt |
| External reference | 1084 Oak Street Puffin.dwg | T1084 Oak Street Puffin.txt |

## Completeness Calculation for 1084

### 1. Source Coverage: 25 / 25

| Evidence | Points | Reason |
|---|---:|---|
| CAD/layout source | 7 / 7 | DXF is present; root DWG and xref DWG are also present |
| Signal/control source | 7 / 7 | UTC Form DOCX, TOPAS2500 config PDF, and MOVA tools report are present |
| Detector/control source | 4 / 4 | MOVA report and UTC Form detector/control references are present |
| Timing/override source | 4 / 4 | RAMData .8tx is present |
| Site metadata | 3 / 3 | Description, SCN, IP, controller type, and config number were extracted |

### 2. Machine Readability: 18 / 20

| Evidence | Points | Reason |
|---|---:|---|
| Parser route coverage | 8 / 8 | All files have a parser or conversion route |
| Control evidence readable | 4 / 4 | UTC Form DOCX was parsed automatically |
| Geometry evidence readable | 4 / 4 | DXF is available |
| Timing evidence readable | 2 / 2 | RAMData .8tx is text-readable |
| Conversion burden | 0 / 2 | Supporting DWGs and MOVA PDF still need deeper conversion/parsing if required later |

### 3. Extracted Control Model: 21 / 25

| Evidence | Points | Reason |
|---|---:|---|
| Controller type | 5 / 5 | ST950 extracted |
| SCN/IP/config metadata | 5 / 5 | J02345, 10.249.151.7, and config 1084 extracted |
| Streams/stages | 6 / 6 | Single stream and 2 stages extracted |
| Phase labels | 5 / 5 | 4 phase labels extracted |
| SCOOT/link/detector evidence | 0 / 4 | MOVA and detector sources are available, but full detector/link extraction is not implemented in the inventory parser yet |

### 4. Geometry Readiness: 20 / 20

| Evidence | Points | Reason |
|---|---:|---|
| Root CAD/DXF available | 8 / 8 | 1084 Oak Street Puffin.dxf is present |
| Supporting DWG/overlay files | 4 / 4 | Root DWG and external reference DWG are present |
| Drawing PDF | 3 / 3 | Detailed design drawing PDF is present |
| Low root ambiguity | 5 / 5 | Transmittal TXT identifies T1084 Oak Street Puffin.dwg as the root drawing |

### 5. QA / Uncertainty: 10 / 10

| Evidence | Points | Reason |
|---|---:|---|
| Confidence | 8 / 8 | Inventory confidence is high |
| Manual questions | 2 / 2 | No unresolved manual questions |

### Completeness Result

```text
25 + 18 + 21 + 20 + 10 = 94 / 100
```

**Completeness Score: 94 / 100**

Interpretation: this is a very complete site. The main remaining gap is that MOVA/detector details are recorded as available but not deeply parsed yet.

## Complexity Calculation for 1084

### 1. Junction Topology: 3 / 15

`junction_type = pedestrian_crossing`, so the physical junction topology is simpler than a three-arm or four-arm road junction.

### 2. Control Method / Controller: 13 / 15

`control_method = MOVA + UTC`, so the control logic is more complex than a basic UTC or SCOOT-only site.

### 3. Staging and Phase Complexity: 8 / 15

Formula:

```text
score = min(15, 2 * stage_count + 2 * stream_count + 0.5 * phase_count)
      = min(15, 2 * 2 + 2 * 1 + 0.5 * 4)
      = min(15, 4 + 2 + 2)
      = 8
```

### 4. CAD Geometry / Package Complexity: 8 / 15

The site has one large DXF, a root DWG, and an external reference DWG. This is more complex than a single clean DXF but simpler than a multi-overlay CAD package.

### 5. Detector / SCOOT Complexity: 7 / 10

The site has MOVA-related detector/control evidence and UTC Form detector references. It is not scored at the maximum because full detector/link extraction is not yet represented in the inventory JSON.

### 6. Special Logic / Timing Complexity: 8 / 10

RAMData is present and a MOVA tools report is present, so special/adaptive control logic is likely relevant.

### 7. File-Format Burden: 8 / 10

The site uses a mixed package: PDF, DOCX, DWG, DXF, TXT, and 8TX.

### 8. Ambiguity / Cleanup Burden: 3 / 10

There are no unresolved manual questions and the transmittal identifies the root drawing, but the as-built PDF says "still to be provided" and the MOVA report still needs deeper parsing.

### Complexity Result

```text
3 + 13 + 8 + 8 + 7 + 8 + 8 + 3 = 58 / 100
```

**Complexity Score: 58 / 100**

Interpretation: this is a medium-complexity site. The road geometry is simple, but the MOVA/control evidence and mixed file formats make it more challenging than a basic pedestrian crossing dataset.

## Recommendation for 1084

| Score | Value |
|---|---:|
| Completeness Score | 94 / 100 |
| Complexity Score | 58 / 100 |

Recommended dataset role:

```text
Development/test core site or early validation site
```

Reason:

- Very complete evidence set.
- Good contrast with 1062: simpler physical topology but more MOVA-oriented control evidence.
- Useful for developing support for pedestrian crossings, MOVA files, root drawing / xref handling, and large DXF files.
- If used as a validation site, avoid using it heavily during parser tuning.
