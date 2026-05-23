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
| Supporting DWG/overlay/topographic files available | 4 |
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

## Worked Example: 1062 LondonRdMorrisons

Inventory source:

```text
configs/1062_LondonRdMorrisons.site_inventory.partial.json
```

Site data root:

```text
data/1062_LondonRdMorrisons
```

Key inventory facts:

| Field | Value |
|---|---|
| site_id | 1062 |
| site_name | LondonRdMorrisons |
| junction_type | three_arm |
| controller_type | Yunex Gemini 2 |
| control_method | SCOOT + UTC |
| stream_count | 2 |
| stage_count | 3 |
| phase_count | 8 |
| phase_labels | X, G, B, A, C, Y, Z, D |
| confidence | high |
| manual_questions | 0 |
| source file count | 14 |

Source file types:

| File type | Count |
|---|---:|
| PDF | 3 |
| DOCX | 1 |
| 8TX | 1 |
| DWG | 7 |
| DXF | 1 |
| TXT | 1 |

Important extracted content:

| Extracted field | Value | Source |
|---|---|---|
| UTC junction description | London Rd/ Morrisons | 1062_UTCForm_Jan24.docx |
| Outstation SCN and type | Yunex Gemini 2/ X04120 | 1062_UTCForm_Jan24.docx |
| Junction SCN | J04121 | 1062_UTCForm_Jan24.docx |
| IP address | 172.16.52.53 | 1062_UTCForm_Jan24.docx |
| TOPAS2500 config number | EPR203 | 1062_UTCForm_Jan24.docx |
| Stream labels | Str 0, Str 1 | 1062_UTCForm_Jan24.docx |
| Stage count by stream | Str 0 = 3, Str 1 = 2 | 1062_UTCForm_Jan24.docx |

## Completeness Calculation for 1062

### 1. Source Coverage: 25 / 25

| Evidence | Points | Reason |
|---|---:|---|
| CAD/layout source | 7 / 7 | DXF is present; multiple DWGs and drawing PDF are also present |
| Signal/control source | 7 / 7 | UTC Form DOCX and TOPAS2500 config PDF are present |
| Detector/SCOOT source | 4 / 4 | SCOOT detector PDF and SCOOT link descriptions are present |
| Timing/override source | 4 / 4 | RAMData .8tx is present |
| Site metadata | 3 / 3 | Description, SCN, IP, controller type, and config number were extracted |

### 2. Machine Readability: 18 / 20

| Evidence | Points | Reason |
|---|---:|---|
| Parser route coverage | 8 / 8 | All files have a parser or conversion route |
| Control evidence readable | 4 / 4 | UTC Form DOCX was parsed automatically |
| Geometry evidence readable | 4 / 4 | Root DXF is available |
| Timing evidence readable | 2 / 2 | RAMData .8tx is text-readable |
| Conversion burden | 0 / 2 | Several supporting DWGs still need conversion if they are required later |

### 3. Extracted Control Model: 25 / 25

| Evidence | Points | Reason |
|---|---:|---|
| Controller type | 5 / 5 | Yunex Gemini 2 extracted |
| SCN/IP/config metadata | 5 / 5 | J04121, 172.16.52.53, and EPR203 extracted |
| Streams/stages | 6 / 6 | 2 streams and max 3 stages extracted |
| Phase labels | 5 / 5 | 8 phase labels extracted |
| SCOOT/link evidence | 4 / 4 | SCOOT link descriptions extracted |

### 4. Geometry Readiness: 19 / 20

| Evidence | Points | Reason |
|---|---:|---|
| Root CAD/DXF available | 8 / 8 | T1062 Safeway Store.dxf is present |
| Supporting DWG/overlay files | 4 / 4 | Multiple DWG overlays and OS/topographic drawings are present |
| Drawing PDF | 3 / 3 | 1062_Drawing_Sep24.pdf is present |
| Low root ambiguity | 4 / 5 | Root DXF appears clear, but supporting overlays still need later interpretation |

### 5. QA / Uncertainty: 10 / 10

| Evidence | Points | Reason |
|---|---:|---|
| Confidence | 8 / 8 | Inventory confidence is high |
| Manual questions | 2 / 2 | No unresolved manual questions |

### Completeness Result

```text
25 + 18 + 25 + 19 + 10 = 97 / 100
```

**Completeness Score: 97 / 100**

Interpretation: this is a very complete site for software development. It has control, staging, phase, geometry, detector, and RAM evidence.

## Complexity Calculation for 1062

### 1. Junction Topology: 7 / 15

`junction_type = three_arm`, so this is more complex than a simple pedestrian crossing but less complex than a four-arm or roundabout site.

### 2. Control Method / Controller: 10 / 15

`control_method = SCOOT + UTC`, so the site includes coordinated signal-control evidence rather than only a simple UTC form.

### 3. Staging and Phase Complexity: 14 / 15

Formula:

```text
score = min(15, 2 * stage_count + 2 * stream_count + 0.5 * phase_count)
      = min(15, 2 * 3 + 2 * 2 + 0.5 * 8)
      = min(15, 6 + 4 + 4)
      = 14
```

### 4. CAD Geometry / Package Complexity: 11 / 15

The site has one DXF, seven DWGs, overlays, and OS/topographic drawings. This is more complex than a single clean DXF, but not as difficult as an unresolved xref/ZIP package with no root drawing.

### 5. Detector / SCOOT Complexity: 7 / 10

SCOOT detector evidence and SCOOT link descriptions are present. The detector PDF still needs a deeper parser if detector geometry or full detector tables are required later.

### 6. Special Logic / Timing Complexity: 5 / 10

RAMData is present and may contain timing, intergreen, or detector overrides. No MOVA/proprietary special logic has been identified.

### 7. File-Format Burden: 8 / 10

The site uses a mixed package: PDF, DOCX, DWG, DXF, TXT, and 8TX.

### 8. Ambiguity / Cleanup Burden: 2 / 10

There are no unresolved manual questions, but the supporting DWG overlays may still require interpretation later.

### Complexity Result

```text
7 + 10 + 14 + 11 + 7 + 5 + 8 + 2 = 64 / 100
```

**Complexity Score: 64 / 100**

Interpretation: this is a medium-high complexity site. It is not the simplest first test case, but it is very useful because the data is complete and the control structure is non-trivial.

## Recommendation for 1062

| Score | Value |
|---|---:|
| Completeness Score | 97 / 100 |
| Complexity Score | 64 / 100 |

Recommended dataset role:

```text
Development/test core site
```

Reason:

- Very complete evidence set.
- Good automatic extraction from UTC Form.
- Has SCOOT + UTC, RAM, phases, streams, stages, detector evidence, and CAD geometry.
- Complex enough to exercise the software, but not so ambiguous that it should be reserved only for stress testing.

If the project needs a strict validation hold-out set, do not use 1062 as a final validation-only site, because it has already been used to develop and test the current inventory parser.
