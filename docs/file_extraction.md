# Step 2 File-format Fact Extraction Design

## Goal

Implement Step 2 of the MAPEM pipeline: recursively scan a complete site folder,
dispatch every source file to a format-specific parser, and write a unified
`extracted_facts.partial.json`. Step 2 is independent from the Step 1
`site_inventory.partial.json` output.

The first version extracts MAPEM-relevant candidates and provenance. It does not
map candidates to final MAPEM fields or fuse evidence. For scanned PDF pages, it
can run optional OCR/CV and records the result as low-confidence candidate facts.

## Architecture

Use a unified extraction coordinator with independent parser modules. The
coordinator scans the complete site folder, selects a parser by file type,
catches file-specific parsing errors, and returns one result per source file in
stable path order.

Each parser implements the same conceptual boundary:

```python
def extract_<format>_facts(path: str | Path) -> list[dict]:
    ...
```

Each returned fact has:

```json
{
  "fact_type": "phase_label",
  "value": "A",
  "evidence_location": "site-folder/forms/1062_UTCForm_Jan24.docx -> table 2 row 4",
  "confidence": 0.9
}
```

`evidence_location` is a provenance chain. The coordinator prefixes every fact
with the source-file path discovered under the site folder. Parsers then append
their format-specific internal location, such as a page, line, paragraph, table
row, CAD entity, GIS feature, or ZIP member.

Examples:

```text
site-folder/reports/config.pdf -> page 1 line 16
site-folder/packages/drawings.zip -> archive member xref/OS-TOPO.dwg -> modelspace
```

This duplicates some information from the file-level `source_file` field
intentionally: a fact remains traceable when it is inspected, filtered, or
copied independently from its wrapper.

### Confidence Scores

`confidence` is a rule-based evidence-strength score in the range `0.0` to
`1.0`. It is not a statistically calibrated probability and does not mean that
the candidate has already been accepted as a final MAPEM field. Step 2 uses the
score to describe how directly the parser observed or derived the fact. A later
evidence-fusion step must resolve conflicts, compare independent sources, and
decide whether a candidate is usable.

Use the following interpretation:

| Range | Meaning |
| --- | --- |
| `1.0` | Deterministic observation or workflow state, such as a ZIP member, rejected unsafe path, file size, missing PDF text, or required MOVA Tools export |
| `0.85` to `0.95` | Strong structured evidence read directly from a field, tag, parsed CAD structure, or exact metadata pattern |
| `0.70` to `0.80` | Structured candidate that still needs semantic interpretation, such as geometry, a table row, PDF image-page feature, CAD label, or filename classification |
| `0.60` to `0.69` | Heuristic candidate based on a keyword or derived approximation |
| Below `0.60` | Weak image-derived or OCR-derived candidates that require corroboration or manual review |

Current defaults:

| Fact source | Confidence | Reason |
| --- | --- | --- |
| TXT, DOCX, or PDF keyword candidate | `0.65` | Keyword presence identifies a relevant line, but does not fully interpret its meaning |
| Exact site description, SCN, or IP pattern | `0.90` | Parsed from an explicit metadata pattern |
| DOCX or PDF table row | `0.80` | Row content is directly extracted, but column semantics may still require matching |
| PDF image-page feature summary | `0.80` | Page size and embedded-image boxes are directly observed, but no road feature has been recognised yet |
| PDF vector page summary | `0.85` | Vector drawing object counts are directly read from the PDF page |
| PDF vector line, curve, or rectangle candidate | `0.70` to `0.75` | Geometry is directly read from PDF drawing objects, but not yet classified as road semantics |
| PDF drawing semantic candidate | `0.40` to `0.45` | Low-confidence road marking, lane line, stop line, crossing, arrow, or signal-head symbol candidate derived from drawing geometry |
| PDF OCR text candidate | `0.55` | Text was recognised from rendered page pixels, so it is weaker than native PDF text |
| PDF CV line candidate | `0.50` | Line segment was detected from pixels and has not yet been classified as lane, marking, stop line, or drawing noise |
| ZIP member or rejected unsafe member | `1.00` | Direct archive observation |
| ZIP DWG filename classification | `0.80` to `0.85` | Derived from path depth or filename hints |
| CAD layer names or entity counts | `0.95` | Directly read from parsed DXF structure |
| CAD geometry, label, or block candidate | `0.70` to `0.80` | Directly extracted structure with unresolved MAPEM semantics |
| CAD coordinate bounds | `0.90` | Deterministically calculated from extracted geometry |
| GIS road name | `0.85` | Directly read from a GIS property or OSM tag |
| GIS geometry | `0.75` | Directly read geometry that still needs semantic matching |
| GIS coordinate bounds | `0.90` | Deterministically calculated from source geometry |
| GIS junction centre candidate | `0.60` | Approximation calculated as the centre of the geometry bounds |
| MOVA export requirement and file size | `1.00` | Direct workflow state and file metadata, not decoded MOVA control facts |

Facts recursively extracted from ZIP members retain the score assigned by the
inner parser. DWG files are converted with ODA File Converter and then use the
same confidence rules as DXF files.

The coordinator wraps facts with file-level status:

```json
{
  "site_id": "1062",
  "source_files": [
    {
      "source_file": "1062_UTCForm_Jan24.docx",
      "file_type": "docx",
      "parser": "docx_parser",
      "status": "parsed",
      "extracted_facts": []
    }
  ]
}
```

## Retained Data by File Format

Step 2 keeps extracted facts and provenance, not a second copy of each original
file. The following table describes the data retained by the current parsers.
Candidate facts are intentionally conservative: Step 3 will match, deduplicate,
and fuse them into MAPEM fields.

| File format | Data scanned | Data retained in `extracted_facts.partial.json` | Why it is retained |
| --- | --- | --- | --- |
| TXT, 8TX | Decoded non-empty text lines | Keyword candidates for phase, stage, stream, intergreen, detector, I/O allocation, SCOOT, timing, override, and control; exact site description, SCN, and IP matches | Controller and RAM reports often expose useful control evidence as text |
| PDF | Extractable page text, tables, page-level image objects, vector drawing objects, and rendered page pixels for pages with images | Keyword and metadata candidates; complete non-empty table rows; `needs_future_recognition` for pages without text; `pdf_image_page_candidate` for pages with images; OCR text candidates; CV line candidates; `pdf_vector_page_candidate`; vector line, curve, and rectangle candidates; low-confidence drawing semantic candidates | Configuration reports, schedules, and drawings may contain text tables, raster images, and vector drawing geometry |
| DOCX | Paragraph text and tables | Keyword and metadata candidates; complete non-empty table rows | UTC forms and supporting notes contain structured site and control information |
| DXF | Modelspace entities, layers, geometry, text, and block inserts | Layer names; entity counts; line and polyline geometry candidates; text labels; block references; coordinate bounds | CAD structure provides later lane, stop-line, crossing, and signal-head evidence |
| DWG | DWG converted to DXF through ODA File Converter, then scanned as DXF | The same facts as DXF | DWG is binary; ODA conversion exposes the CAD structure for the Python parser |
| GeoJSON, JSON | GIS features, properties, and coordinates | Road-name candidates; geometry candidates; coordinate bounds; approximate bounds-centre junction candidate | GIS data provides road names and map geometry |
| OSM | Nodes, ways, and way tags | Road-name candidates; coordinate bounds; approximate bounds-centre junction candidate | OSM data provides reference road names and coordinates |
| Shapefile, GeoPackage | GIS features, properties, and coordinates through Fiona | Road-name candidates; geometry candidates; coordinate bounds; approximate bounds-centre junction candidate | Structured GIS files provide spatial reference evidence |
| ZIP | Archive paths and supported nested members | Archive-member facts; rejected unsafe paths; nested parseable-file availability; root and xref DWG candidates; topographic drawing availability; recursively extracted inner facts | ZIP is a container; retaining the member chain preserves the original source provenance |
| MOVA | File path, optional executable configuration, and file size | `mova_tools_not_configured_skipped` when MOVA Tools is unavailable; `mova_tools_manual_export_required` when it is configured; file-size metadata | `.mova` is a proprietary binary dataset and is treated as low-priority supplemental evidence. It does not block lane extraction |
| Unsupported extension | File path and extension | File-level `status: "unsupported"` with no extracted facts | The file remains visible for manual review without guessing its contents |

Every retained fact includes an `evidence_location` chain. For example, a CAD
fact extracted from a DWG inside a ZIP keeps the ZIP path, archive-member path,
and modelspace entity location.

### Extraction Noise Control

The extraction stage applies conservative filtering before assignment or MAPEM
matching:

| Noise source | Rule |
| --- | --- |
| Empty CAD text | `TEXT` and `MTEXT` entities with blank or whitespace-only content are not emitted as `cad_text_label` facts |
| Non-site CAD files | CAD files with a leading site id that does not match `--site-id` are returned with `status: "skipped"` and `skip_reason: "non_site_cad_source"` |
| Topographic CAD | Files such as `OS-TOPO.dwg` are parsed only for CAD metadata and bounds; dense drawing geometry and labels are not emitted from the standalone topo file |
| ZIP / standalone CAD duplicates | If a CAD file exists both as a standalone file and as a ZIP member with the same basename, the standalone file is preferred and the ZIP member emits `duplicate_archive_member_skipped` instead of recursively extracting duplicate CAD facts |
| PDF semantic drawing candidates | PDF vector/CV semantic facts remain low-confidence candidates and are not promoted to final road semantics in Step 2 |

This keeps `extracted_facts.partial.json` useful for later matching without
turning topographic background drawings, unrelated site drawings, or duplicated
archive members into lane-level evidence.

### Structured Movement Mapping Facts

Some controller and UTC documents explicitly describe the relationship between
phase letters, SCOOT links, stages, and traffic movements. Step 2 now extracts
these relationships as structured facts so the adapter can route `signalGroup`
through `movement_ref` before resolving the movement to a lane.

| Fact name | Source pattern | Meaning |
| --- | --- | --- |
| `phase_movement_mapping_from_controller_config` | Controller config `Phase Type and Conditions`, for example `A LONDON ROAD INBOUND AHEAD` | Maps a controller phase to a movement description, road name, direction, maneuver, and `movement_ref` |
| `scoot_link_movement_from_utc_form` | UTC form `Link SCN | Link Description` table | Maps a SCOOT link letter/SCN to a movement description and `movement_ref` |
| `phase_scoot_link_mapping_from_utc_form` | UTC form `Controller Phase Letter | SCOOT Link Letter` table | Maps controller phase letters to SCOOT link refs and, when available, the linked `movement_ref` |
| `scoot_link_stage_mapping_from_utc_form` | UTC form `Link Letter | ... | UTC Green Stage No's` table | Maps SCOOT link refs to UTC green stage numbers |

These facts intentionally emit `movement_ref`, `phase_ref`, `scoot_link_ref`,
and `stage_refs`, not `lane_ref`. `lane_ref` is created by geometry assignment,
so the later adapter/matching step should join movement semantics to assigned
lanes using road name, direction, maneuver, CAD labels, and geometry context.

### Fact Names for Future MAPEM Matching

The final `fact_type` in `extracted_facts.partial.json` should use the `Fact
Name` column from `configs/MAPEM Dictionary.xlsx`, sheet `Fact`, whenever a
parser output can be safely mapped to that dictionary. This prepares Step 3
without implementing MAPEM field matching yet.

Parsers should emit the dictionary fact name directly. For example:

```json
{
  "fact_type": "phase_label_from_ram_8tx"
}
```

Facts that do not yet have a safe dictionary equivalent keep their current
parser-level name until the matcher rules are defined. The extraction output
does not add a separate legacy-name mapping layer.

## Components

### Extraction Coordinator

Add `src/mapemgen/ingestion/facts.py`.

Responsibilities:

- validate the site folder path
- scan all nested source files recursively
- dispatch by file type
- preserve full source-file and internal-location provenance with deterministic
  ordering
- record `parser_error` for an individual corrupt or malformed file
- allow required dependency errors to propagate with a clear installation
  message

Add an `extract` CLI command:

```powershell
python -m mapemgen.cli extract `
  --site-folder <site-folder> `
  --site-id <site-id> `
  --out-dir <output-folder>
```

The fixed output name is `extracted_facts.partial.json`.

### TXT and 8TX Parser

Add `src/mapemgen/ingestion/ram_text.py`.

Read text with a small encoding fallback set. Preserve non-empty source lines and
extract candidate facts for:

- RAM override lines
- phase labels
- stages
- streams
- intergreens
- detectors
- I/O allocation

The parser emits conservative candidates with line-number evidence. It does not
claim full semantic interpretation of every vendor-specific report.

### ZIP Parser

Add `src/mapemgen/ingestion/zip_packages.py`.

Read the archive member list and recursively parse supported members. Emit:

- archive member facts
- root DWG candidates
- xref DWG candidates
- OS or topographic drawing availability
- nested parseable-file availability facts

Supported members are copied one at a time to temporary files, parsed through
the same format dispatcher, and removed after parsing. Nested ZIP files are
parsed recursively. Archive-member paths remain in `evidence_location`.

For safety, the parser rejects absolute paths, `..` path traversal, members over
100 MB, and ZIP nesting deeper than five levels.

### DOCX Parser

Add `src/mapemgen/ingestion/docx_tables.py`.

Use `python-docx` to read paragraphs and tables. Emit candidates for:

- site description and metadata
- SCN
- IP address
- phase labels
- stages
- streams
- SCOOT links
- timing and intergreen values

Evidence locations identify paragraph numbers or table row and cell positions.

### PDF Parser

Implement `src/mapemgen/ingestion/pdf_tables.py`.

Use `pdfplumber` to read extractable page content and tables. Emit:

- page text candidates relevant to control data
- phase, stage, stream, detector and timing candidates
- table row facts with page and table location
- `needs_future_recognition` when a page has no usable text
- `pdf_image_page_candidate` with page size, embedded image count, and image
  bounding boxes for any page that contains embedded image objects
- `pdf_ocr_text_candidate` and OCR keyword candidates from rendered pages with
  images
- `pdf_cv_line_candidate` for line segments detected from rendered pages with
  images
- `pdf_vector_page_candidate`, `pdf_vector_line_candidate`,
  `pdf_vector_curve_candidate`, and `pdf_vector_rect_candidate` for vector PDF
  drawing objects such as lines, curves, and rectangles
- low-confidence drawing semantic candidates such as
  `road_marking_candidate_from_pdf_vector`, `lane_line_candidate_from_pdf_vector`,
  `stop_line_candidate_from_pdf_vector`, `crossing_candidate_from_pdf_vector`,
  `arrow_candidate_from_pdf_vector`, `signal_head_symbol_candidate_from_pdf_vector`,
  `road_marking_candidate_from_pdf_cv`, and `lane_line_candidate_from_pdf_cv`

Step 2 runs OCR/CV for any PDF page that contains image objects, even when the
same page also has extractable text or tables. Missing OCR/CV packages are
treated as required dependency errors when a PDF page with images needs
recognition. Vector PDF drawing objects are extracted directly from the PDF page
structure and do not require OCR/CV packages.

### DXF and DWG Parser

Implement `src/mapemgen/ingestion/cad.py`.

Use `ezdxf` for DXF parsing. Emit:

- layer names
- entity counts
- coordinate bounds
- line and polyline geometry candidates
- text labels with insertion-point coordinates when available
- block references with insertion-point coordinates when available
- CAD movement-label candidates when text contains a movement-like direction or
  manoeuvre, such as `inbound ahead`, `WB left`, or `right turn`
- CAD arrow-block candidates when a block name indicates an arrow, turn, or
  lane direction
- lane, stop line, crossing and signal-head candidates based on configurable
  layer-name and text-label rules

For DWG input, call ODA File Converter through `ezdxf.addons.odafc`, create a
temporary DXF, and run the same DXF parser. ODA File Converter is a required
runtime dependency when a site inventory contains `.dwg`. If it is not
installed, extraction stops with a clear error.

CAD text and block coordinates are important upstream data. The assignment
stage cannot infer `movement_ref -> lane_ref` from a phase table alone; it needs
a spatial movement label, arrow block, or lane label near a lane geometry. For
that reason `cad_text_label`, `cad_block_reference`,
`cad_movement_label_candidate`, and `cad_arrow_block_candidate` retain their
modelspace coordinates whenever the CAD entity exposes an insertion point.

CAD block/text semantics are configured in
`configs/cad_symbol_semantics.json`. The parser reads that table before scanning
CAD entities. `CAD_SYMBOL_RULES_PATH` can point to a different JSON rule file
for local experiments.

Current starter rules:

| CAD symbol/text rule | Output fact | Meaning |
| --- | --- | --- |
| Block name `HD*`, for example `HD084` or `HD001S` | `cad_signal_head_candidate` | Signal-head candidate with modelspace coordinates |
| Xref-prefixed `...$HD001P` or Leeds `Signal-Symbol-001P` names | `cad_signal_head_candidate` | Signal-head candidate from vendor/xref block naming |
| Block name `HD003P` or `HD004P` | `cad_arrow_block_candidate` | Directional signal-arrow candidate from block-definition geometry; kept as `requires_context_match` |
| Block name `pole`, `WBPOLE-sym`, `poleno`, `stubpole`, `crpole`, or `polesock` | `cad_pole_candidate` | Pole/post candidate with modelspace coordinates |
| Block name `tactpblk`, `TACTPBLK`, `tactknob`, or `tactpave`, including xref-prefixed variants | `cad_pedestrian_facility_candidate` | Tactile paving or pedestrian crossing facility candidate |
| Block name containing `arrow`, `left`, `right`, `1038l`, or `1038r` | `cad_arrow_block_candidate` | Directional arrow candidate, with left/right hint when visible |
| Text containing `LEFT`, `RIGHT`, `AHEAD`, `WB`, `EB`, `NB`, `SB`, `INBOUND`, or `OUTBOUND` | `cad_movement_label_candidate` | Movement label with derived `movement_ref` |
| Text `KEEP CLEAR` | `cad_lane_use_label_candidate` | Lane-use or road-marking label |

CAD layer semantics are configured separately in
`configs/cad_layer_semantics.json`. The parser reads the entity layer before
emitting geometry facts. `CAD_LAYER_RULES_PATH` can point to a different JSON
rule file for local authority-specific CAD templates. Geometry facts emitted by
layer rules keep `geometry`, `layer`, and `semantic_type` in the payload.

Current starter layer rules:

| CAD layer pattern | Output fact | Meaning |
| --- | --- | --- |
| `stopline`, `stoplines`, `SCT_LOOPS`, `SLC` | `stop_line_from_cad` | Stop-line or stop-line loop candidate |
| `RoadMarkings`, `ROAD MARKINGS WHITE`, `PRO-MARKINGS`, `RD MKS`, `1038`, `STUDS`, `ZIG ZAGS` | `road_marking_candidate_from_cad` | Road marking candidate |
| `TACTPAVE`, `Tactiles`, `Toucan-Xings`, `XING`, `crossing` | `crossing_candidate_from_cad` | Crossing or tactile paving geometry candidate |
| `UTC SIGNALS`, `Signals`, `KTS_SIGNALS`, `traffic signal` | `signal_geometry_candidate_from_cad` | Signal layout/equipment geometry candidate |
| `LOOPS`, `UTC_LOOPS`, `MOVA LOOPS`, `TRAFFIC LOOPS` | `detector_loop_candidate_from_cad` | Detector-loop geometry candidate |
| `KERB`, `CarriagewayKerb`, `ROAD-EDGE`, `Road Or Track`, `channel` | `cad_context_geometry_candidate` | Road/kerb context geometry, not direct lane evidence |
| `OS`, `TOPO`, `ExBase`, `BASE` | `cad_context_geometry_candidate` | Background/topographic context geometry |

Lane centreline extraction uses an additional conservative heuristic because
many local CAD drawings do not have a literal `LANE_*` layer. Long line or
polyline geometry on terminal `LINES`, `KTS_LINES`, `centreline`,
`centerline`, `roadcentre`, `roadcenter`, or `R_CL` layers can be emitted as
`lane_geometry_candidate_from_cad` with:

```json
{
  "semantic_type": "lane_centreline_candidate",
  "recognition_basis": "cad_layer_geometry_heuristic",
  "requires_context_match": true
}
```

These candidates use lower confidence (`0.60`) than explicitly named lane
layers. Broad or noisy layers such as `GENLINE`, `ROAD`, `GENPECK`,
`Construction Lines`, `YELLOW_LINES`, `existing-LINES-OFF`, duct, loop, signal,
kerb, OS/base/topographic, text, title, frame, building, vegetation, water, rail
and utility layers are not promoted to lane geometry. This prevents CADs such
as 950L from producing hundreds of false lanes from background road geometry.

When a CAD file is recognised as a standalone topographic/background file, such
as `OS-TOPO.dwg`, extraction still limits it to CAD metadata and coordinate
bounds at the site-folder coordinator level. This prevents dense background
geometry from becoming MAPEM lane evidence.

Layer names are useful hints, not guaranteed semantics. Some CAD files contain
hundreds of layers, and the naming can vary by local authority, contractor,
year, xref source, and drawing template. The same concept may appear as
`RoadMarkings`, `PRO-MARKINGS`, `RD MKS`, or
`x_prop_road markings Rev B$0$Lines`; one layer can also contain mixed object
types. For this reason, layer-derived facts remain candidate facts and later
matching/fusion must corroborate them with block symbols, text labels, geometry
context, GIS, PDFs, or manual rules before filling final MAPEM fields.

Recommended CAD source-data practice:

| Recommendation | Why it matters |
| --- | --- |
| Put signal heads, poles, stop lines, crossings, detector loops, and road markings on clear, consistent layers | The parser can emit more accurate candidate facts from layer rules |
| Avoid mixing OS/topographic background, construction notes, and traffic-signal evidence on the same layer | Reduces background noise and false lane evidence |
| Keep road names, phase labels, movement labels, and detector labels as CAD text with insertion coordinates | Later assignment can spatially relate text semantics to lanes and signal equipment |
| Provide a layer dictionary or drawing legend when layer names are vendor-specific | The project can encode those names in `configs/cad_layer_semantics.json` |
| Keep xref names stable or document their source | Xref-prefixed layer and block names can still be parsed when their naming is consistent |

### GIS Parser

Implement `src/mapemgen/ingestion/gis.py`.

Support:

- GeoJSON and `.json`
- OSM XML
- Shapefile `.shp`
- GeoPackage `.gpkg`

Use the standard library for GeoJSON and OSM. Use `fiona` for Shapefile and
GeoPackage. Emit:

- road-name candidates
- geometry candidates
- coordinate bounds
- intersection reference-point candidates

Required GIS libraries must be installed. Missing dependencies are errors, not
warnings or silent fallbacks.

### MOVA Parser

Add `src/mapemgen/ingestion/mova.py`.

`.mova` is a proprietary binary dataset format used by the official MOVA Tools
application. MOVA data can be useful later for controller logic, but it is
lower priority than CAD/PDF geometry for lane extraction. If MOVA Tools is not
configured, the parser records `mova_tools_not_configured_skipped` and continues
with the rest of the site folder.

Full MOVA extraction must use MOVA Tools as an external conversion boundary, in
the same way that DWG extraction uses ODA File Converter:

```text
.mova binary dataset
        |
        v
official MOVA Tools export
        |
        v
exported text / report files
        |
        v
Python parser
        |
        v
detector, control, phase, stage, stream, timing, and plan facts
```

The external tool is required for detailed MOVA facts because the repository
samples are opaque binary files, the binary schema is not published, and
guessing byte offsets would produce unreliable MAPEM evidence. TRL describes
MOVA Tools as the official program for creating, editing, and converting MOVA
dataset files.

When MOVA evidence is needed, set `MOVA_TOOLS_PATH` to the installed MOVA Tools
executable. The exact automated export command must be confirmed against the
installed MOVA Tools version before it is enabled. If that version provides only
a graphical export workflow, export the files manually and place them in the
site folder for the Python parsers.

## Dependency Policy

Add the libraries required by the implemented parsers to `pyproject.toml`.

Python packages are ordinary project dependencies. ODA File Converter and MOVA
Tools are external applications and must be documented in the README.

Dependency failures are handled as follows:

| Situation | Behaviour |
| --- | --- |
| Required Python package missing | Stop with an actionable error |
| `.dwg` encountered without ODA File Converter | Stop with an actionable error |
| `.mova` encountered without MOVA Tools | Record `mova_tools_not_configured_skipped`, keep file metadata, and continue extraction |
| Individual source file is corrupt or malformed | Record file-level `parser_error` and continue |
| PDF page has no extractable text | Emit `needs_future_recognition` |
| PDF page contains image objects | Emit `pdf_image_page_candidate`, run OCR/CV, and require the optional `cv` packages |
| PDF page contains vector drawing objects | Emit `pdf_vector_page_candidate` and vector drawing candidates without OCR/CV packages |
| MOVA Tools version has no confirmed CLI export command | Require manual export from MOVA Tools and parse the exported files |

## Installation

### Python environment

Open PowerShell and replace `<project-root>` with the absolute path of this
repository on the local machine. It is the folder that contains
`pyproject.toml`, `README.md`, `src/`, and `tests/`.

On Windows, use Python 3.13. Fiona currently provides a Windows wheel for
CPython 3.13, but not for CPython 3.14. Using Python 3.14 makes pip attempt a
local Fiona build that requires a separate GDAL development installation.

Template:

```powershell
cd "<project-root>"
py -3.13 -m venv mapem313
.\mapem313\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Example for the current machine:

```powershell
cd C:\Users\leovo\Desktop\GDP
py -3.13 -m venv mapem313
.\mapem313\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

`mapem313` is the dedicated virtual environment for this project. Install all
future Python packages for this repository after activating this environment.
Each time a new PowerShell window is opened, activate it again:

```powershell
cd "<project-root>"
.\mapem313\Scripts\Activate.ps1
```

Example for the current machine:

```powershell
cd C:\Users\leovo\Desktop\GDP
.\mapem313\Scripts\Activate.ps1
```

`python -m pip install -e .` installs the packages declared in
`pyproject.toml`:

| Package | Used for |
| --- | --- |
| `python-docx` | DOCX paragraphs and tables |
| `pdfplumber` | PDF text and tables |
| `ezdxf` | DXF parsing and the Python boundary for DWG conversion |
| `fiona` | Shapefile and GeoPackage parsing |
| `pyproj` | British National Grid to WGS84 coordinate conversion |

TXT, 8TX, ZIP, GeoJSON, JSON, and OSM extraction use Python standard-library
modules and do not need additional parser packages. Full MOVA extraction can
use the external MOVA Tools application described below, but missing MOVA Tools
does not block extraction.

To install the parser packages explicitly instead of installing the project:

```powershell
python -m pip install "python-docx>=1.1" "pdfplumber>=0.11" "ezdxf>=1.3" "fiona>=1.10" "pyproj>=3.7"
```

OCR/CV for scanned PDF drawings uses optional packages:

```powershell
python -m pip install -e ".[cv]"
```

This installs `opencv-python`, `pytesseract`, and `pymupdf`. Tesseract OCR also
requires the external Tesseract executable on the machine before
`pytesseract` can run OCR. These packages are required when Step 2 encounters a
PDF page that contains image objects and must be recognised from pixels.

On Windows, install the external Tesseract executable with:

```powershell
winget install UB-Mannheim.TesseractOCR
```

After installation, open a new PowerShell window and verify:

```powershell
tesseract --version
```

If PowerShell cannot find `tesseract`, add the installed folder to `PATH`. A
common example path is:

```text
C:\Program Files\Tesseract-OCR
```

For the current PowerShell session only, set `PATH` explicitly before running
extraction:

```powershell
$env:PATH = "C:\Program Files\Tesseract-OCR;$env:PATH"
tesseract --version
```

`pytesseract` is only the Python wrapper. The wrapper is not enough by itself;
the external `tesseract.exe` must be installed and discoverable on `PATH`.

### ODA File Converter for DWG

DWG is not decoded by a pure Python package. Install
[ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)
on the local machine. The code calls it through `ezdxf.addons.odafc`.

After activating the virtual environment, first check the default installation
path used by `ezdxf`:

```powershell
python -c "from ezdxf.addons import odafc; print(odafc.is_installed())"
```

If ODA File Converter was installed in a different folder, explicitly set the
`ezdxf` option `odafc-addon.win_exec_path`. Replace
`<path-to-ODAFileConverter.exe>` with the actual path of the executable:

```powershell
python -c "import ezdxf; from ezdxf.addons import odafc; ezdxf.options.set('odafc-addon', 'win_exec_path', r'<path-to-ODAFileConverter.exe>'); print(odafc.is_installed())"
```

Example when the executable is stored in `E:\ODA`:

```powershell
python -c "import ezdxf; from ezdxf.addons import odafc; ezdxf.options.set('odafc-addon', 'win_exec_path', r'E:\ODA\ODAFileConverter.exe'); print(odafc.is_installed())"
```

The Python assignment above only applies to that single check command. Before
running `mapemgen extract`, set `ODAFC_PATH` in the same PowerShell session:

```powershell
$env:ODAFC_PATH="E:\ODA\ODAFileConverter.exe"
python -m mapemgen.cli extract `
  --site-folder "<site-folder>" `
  --site-id "<site-id>" `
  --out-dir "<output-folder>"
```

The successful command must print:

```text
True
```

If a site folder contains `.dwg` and ODA File Converter is unavailable,
extraction stops with an actionable error.

### MOVA Tools for MOVA datasets

Install the official [MOVA Tools](https://trlsoftware.com/products/traffic-control/mova/mova-downloads/)
application from TRL Software. Python cannot reliably decode `.mova` binary
datasets directly because the binary schema is proprietary and not published.
MOVA Tools is the official application for creating, editing, and converting
these datasets.

MOVA is lower-priority supplemental evidence for this extraction stage. If
MOVA Tools is not installed or `MOVA_TOOLS_PATH` is not set, `mapemgen extract`
does not fail. It records `mova_tools_not_configured_skipped` and continues with
CAD, PDF, DOCX, text, GIS, and ZIP extraction.

After installation, replace `<path-to-MOVATools.exe>` with the actual path of
the installed executable:

```powershell
Test-Path "<path-to-MOVATools.exe>"
$env:MOVA_TOOLS_PATH="<path-to-MOVATools.exe>"
```

Example path:

```powershell
Test-Path "E:\MOVA Tools\MOVATools.exe"
$env:MOVA_TOOLS_PATH="E:\MOVA Tools\MOVATools.exe"
```

`Test-Path` must print:

```text
True
```

Important: the public MOVA Tools download page does not document command-line
export arguments. Confirm the export options exposed by the installed version.
If it only supports graphical export, open the `.mova` file in MOVA Tools,
export the available text or report files, and place those exported files in the
same site folder before running `mapemgen extract`.

## Data Flow

```text
site folder
        |
        v
facts extraction coordinator
        |
        +-- TXT / 8TX parser
        +-- ZIP parser
        +-- DOCX parser
        +-- PDF parser
        +-- DXF parser
        +-- DWG -> ODA File Converter -> DXF parser
        +-- GIS parser
        +-- MOVA -> official MOVA Tools export -> exported-file parser
        |
        v
extracted_facts.partial.json
        |
        v
geometry and semantic scope assignment
        |
        v
geometry_assignments.partial.json
```

## Geometry and Semantic Scope Assignment

Scope assignment is the step after parsing and before MAPEM field matching. It
does not choose MAPEM fields, build `SiteModel`, or decide final lane
connectivity. Its job is to add routing references to extracted facts so that
multi-lane sites do not merge all evidence into one undifferentiated fact pool.

This stage handles two different relationships:

| Relationship | Applies to | Output |
| --- | --- | --- |
| Geometry relationship | Lane lines, stop lines, crossings, road markings, signal-head symbols, CAD/GIS/PDF drawing geometry | `target_scope.intersection_ref`, and `target_scope.lane_ref` when a nearest lane can be identified in the same coordinate space |
| Semantic relationship | Phase labels, stage relationships, detector labels, signal-group labels, road names, control/timing labels | `target_scope.intersection_ref` plus direct semantic references such as `phase_ref`, `stage_ref`, `detector_ref`, `signal_group_ref`, `approach_ref`, or `label_ref` |

Input:

```text
extracted_facts.partial.json
```

Output:

```text
geometry_assignments.partial.json
```

Run it with:

```powershell
python -m mapemgen.cli assign-geometry `
  --input "outputs/1003_LondonRdClevelandBridge/extracted_facts.partial.json" `
  --out-dir "outputs/1003_LondonRdClevelandBridge"
```

The output contains:

| Field | Meaning |
| --- | --- |
| `intersections[]` | Intersection references inferred from junction-centre facts, or a default site intersection when no centre is available |
| `approaches[]` | Groups of nearby parallel lanes in the same source file and coordinate space, with shared CAD-context validation evidence |
| `lanes[]` | Stable `lane_ref` values created from lane-like geometry facts |
| `assigned_facts[]` | Geometry facts with `target_scope.intersection_ref`, `target_scope.approach_ref`, and, when possible, `target_scope.lane_ref` |
| `semantic_assignments[]` | Non-geometry facts with intersection-level scope and direct semantic refs such as `phase_ref`, `stage_ref`, `detector_ref`, or `approach_ref` |
| `movement_lane_mappings[]` | Conservative `movement_ref -> lane_ref` links when lane source labels directly expose the movement; unmatched movements are retained with `requires_context_match: true` |
| `geometry_summary` | Centroid, bounds, coordinate space, and PDF page reference when applicable |

Geometry assignment example:

```json
{
  "fact_id": "fact_00123",
  "fact_name": "stop_line_from_cad",
  "target_scope": {
    "intersection_ref": "intersection_1",
    "approach_ref": "approach_1",
    "lane_ref": "lane_3"
  },
  "assignment_method": "nearest_lane_centroid",
  "distance_to_lane": 1.7
}
```

Semantic assignment example:

```json
{
  "fact_id": "fact_00456",
  "fact_name": "phase_label_from_controller_config",
  "target_scope": {
    "intersection_ref": "intersection_1",
    "lane_ref": null,
    "phase_ref": "phase_A"
  },
  "assignment_method": "semantic_reference_extraction",
  "assignment_basis": "direct_text_reference"
}
```

Movement-to-lane mapping example:

```json
{
  "movement_ref": "movement_london_road_inbound_ahead",
  "movement_text": "London Road inbound ahead",
  "phase_refs": ["phase_A"],
  "lane_ref": "lane_3",
  "intersection_ref": "intersection_1",
  "assignment_method": "lane_label_movement_match",
  "requires_context_match": false
}
```

Unmatched movement example:

```json
{
  "movement_ref": "movement_cleveland_bridge_right",
  "movement_text": "Cleveland Bridge right",
  "phase_refs": ["phase_B"],
  "lane_ref": null,
  "intersection_ref": null,
  "assignment_method": "needs_context_match",
  "requires_context_match": true,
  "unmatched_reason": "no_lane_movement_label"
}
```

Rules:

- CAD and GIS geometry can be assigned by nearest geometry centroid.
- Lane definitions use the highest-priority available lane source: CAD first,
  then Ordnance Survey, then PDF fallback. If PDF fallback is suppressed because
  it creates too many generic clusters, directional CAD signal-arrow blocks can
  create low-confidence lane proxies as the final fallback. Lower-priority
  lane-like facts remain evidence, but they do not create additional lanes when
  a stronger source is available.
- CAD lane candidates from standalone topographic/reference drawings, CAD files
  whose filename indicates a different site id, or non-vehicle/background lane
  layers such as cycle coloured-area layers are retained as facts but are not
  allowed to define MAPEM lanes.
- Heuristic CAD lane-centreline candidates are clustered into lane corridors
  before `lane_ref` values are created. This avoids one CAD segment becoming
  one output lane when a CAD layer splits the same centreline into many small
  entities.
- Nearby parallel lanes from the same source file and coordinate space are then
  grouped into `approaches[]`. This lets the extractor confirm a controlled
  approach automatically when stop lines, signal heads, arrows, movement labels,
  CAD blocks, poles, or road markings are distributed across adjacent lanes
  instead of attached to every individual lane.
- Heuristic CAD lanes keep `requires_context_match: true` in `lanes[]`. They
  are useful routing geometry for later matching, but they are not treated as
  fully confirmed lane semantics until corroborated by labels, arrows, GIS,
  CAD blocks, or other source context.
- After geometry assignment, heuristic CAD lanes are validated against other
  CAD facts assigned to the same lane or the same confirmed approach in the
  same modelspace. Evidence groups include stop lines, signal heads, signal
  geometry, directional arrows, movement labels, road/text labels, CAD blocks,
  poles, and road markings. A lane is marked
  `lane_validation_status: "cad_context_confirmed"` and
  `requires_context_match: false` when either the lane itself or its approach
  has at least two evidence groups from at least two distinct CAD entity
  locations. Otherwise it remains
  `lane_validation_status: "needs_context_match"`.
- `lane_confirmation_basis` records whether confirmation came from
  `direct_lane_context_validation` or `approach_context_validation`.
- If an unconfirmed heuristic CAD lane is close to CAD context evidence already
  assigned to a confirmed approach, it can be adopted into that approach with
  `lane_confirmation_basis: "nearby_confirmed_approach_adoption"`. This handles
  common drawings where adjacent approach lanes are split into separate CAD
  segments and not every segment has its own signal-head or stop-line evidence.
- If an unconfirmed heuristic CAD lane is far from every confirmed CAD context,
  it is marked `lane_validation_status: "out_of_scope_candidate"` with
  `lane_confirmation_basis: "distant_insufficient_context"`. This keeps likely
  background or non-target lane candidates out of later MAPEM matching without
  deleting the original extracted facts.
- Validation evidence is summarized with `validation_evidence_groups`,
  `validation_evidence_counts`, `validation_evidence_fact_ids`, and
  `validation_evidence_fact_count`. The fact id list is capped so the output
  does not become dominated by repeated CAD block references.
- Unconfirmed heuristic CAD lanes also include `unconfirmed_reason`,
  `missing_validation_evidence_group_count`, and
  `nearest_validation_candidates[]`. These diagnostics show why the lane still
  needs context matching and list the nearest CAD context candidates in the same
  CAD modelspace, including fact id, fact name, evidence group, evidence
  location, assigned lane, and distance to this lane.
- Nearest validation candidates are for manual review and rule tuning. A nearby
  candidate is not automatically treated as confirmation if it was assigned to a
  different lane or does not satisfy the independent evidence threshold.
- When PDF is the only lane source, similar PDF lane-line segments are clustered
  into lane corridors so the output does not create one lane per vector segment.
- Phase-to-movement facts can be routed to lanes through `movement_lane_mappings[]`
  only when assignment can read a matching `movement_ref`, `movement_text`,
  lane label, or road-name label from the lane source facts.
- CAD movement labels with coordinates can also produce `movement_lane_mappings[]`
  after assignment places the label near a lane; these mappings use
  `assignment_method: "cad_movement_label_nearest_lane"`. Labels on key,
  legend, note, dimension, or title layers are not auto-mapped because they
  often describe drawing symbols rather than real lane movements.
- Directional CAD signal-arrow lane proxies can map only matching turn
  movements, such as `right_turn` or `left_turn`; these mappings use
  `assignment_method: "cad_signal_arrow_direction_match"` and still keep
  `requires_context_match: true` because the proxy is not full lane geometry.
- If assignment still cannot see which lane belongs to a structured movement,
  it creates a `semantic_movement_lane_proxy` so the movement still has a stable
  `lane_ref`. These mappings use
  `assignment_method: "semantic_movement_lane_proxy"` and always keep
  `requires_context_match: true` because the proxy was created from movement
  semantics rather than observed lane geometry.
- Facts that cannot be converted to points, bounds, or centroids remain
  unassigned.
- Raw geometry remains available; assignment adds scope but does not remove or
  rewrite parser facts.
- Later matching/fusion must still decide which assigned facts fill MAPEM
  fields such as `laneSet[].nodeList`, `connectsTo`, or `signalGroup`.

## Testing

Add synthetic, non-confidential tests for:

- coordinator dispatch and stable output order
- CLI output path
- TXT and 8TX keyword candidates
- ZIP member classification without extraction
- DOCX paragraphs and tables
- PDF text pages, tables, and image-page recognition deferral
- DXF layers, entities, labels, coordinate bounds, and geometry candidates
- DWG ODA invocation boundary using a mock
- GeoJSON, JSON, OSM, Shapefile, and GeoPackage parsing
- required dependency errors
- MOVA Tools configuration and exported-file parsing
- corrupt individual files producing `parser_error` while other files continue

Tests must use generated synthetic fixtures under `outputs/` or temporary test
directories. Do not commit confidential raw source files.

## Out of Scope

Step 2 does not:

- treat OCR/CV output as final MAPEM geometry or signal semantics
- directly decode or reverse-engineer proprietary MOVA binary data without MOVA Tools
- match facts to MAPEM fields
- fuse evidence into `SiteModel`
- generate MAPEM JSON or ASN.1 output

## Usage

This is the direct operation for Step 2: inspect the source folder, extract all
facts from the complete site folder, then assign geometry and semantic scope.

### Template: EDA, Extraction, and Scope Assignment

Replace every value in angle brackets:

| Placeholder | What to enter |
| --- | --- |
| `<project-root>` | Absolute path of the repository root on the local machine |
| `<venv-path>` | Path of the virtual environment activation script, for example `.\mapem313\Scripts\Activate.ps1` |
| `<site-folder>` | Folder containing all files for one traffic-signal site; nested folders are scanned recursively |
| `<site-id>` | Site identifier written into the output files |
| `<site-name>` | Human-readable site name for the optional EDA inventory |
| `<dataset>` | Data source or local authority for the optional EDA inventory |
| `<output-folder>` | Folder where the generated JSON files should be written |
| `<path-to-ODAFileConverter.exe>` | Required only when the site folder contains `.dwg`; use the actual ODA executable path |
| Tesseract OCR | Required only when PDF pages contain images and OCR/CV is needed; verify with `tesseract --version` |

```powershell
cd "<project-root>"
<venv-path>
$env:PYTHONPATH='src'

# Required only when DWG files are present.
$env:ODAFC_PATH="<path-to-ODAFileConverter.exe>"

# Required only when PDF image OCR is needed.
# Use the next line if Tesseract is installed but not visible in this shell.
$env:PATH = "C:\Program Files\Tesseract-OCR;$env:PATH"
tesseract --version

# EDA / source-data inspection. This is optional and does not feed Step 2.
python -m mapemgen.cli inventory `
  --site-folder "<site-folder>" `
  --site-id "<site-id>" `
  --site-name "<site-name>" `
  --dataset "<dataset>" `
  --out-dir "<output-folder>"

# Extract facts from the complete site folder.
python -m mapemgen.cli extract `
  --site-folder "<site-folder>" `
  --site-id "<site-id>" `
  --out-dir "<output-folder>"

# Assign geometry and semantic relationships for later MAPEM matching.
python -m mapemgen.cli assign-geometry `
  --input "<output-folder>\extracted_facts.partial.json" `
  --out-dir "<output-folder>"
```

Expected outputs:

| Output | Purpose |
| --- | --- |
| `site_inventory.partial.json` | Optional EDA summary of files found in the site folder |
| `extracted_facts.partial.json` | Parser output from all supported source files |
| `geometry_assignments.partial.json` | Geometry assignments plus semantic assignments for later matching |

### Example: 1003 London Road Cleveland Bridge

```powershell
cd C:\Users\leovo\Desktop\GDP
.\mapem313\Scripts\Activate.ps1
$env:PYTHONPATH='src'
$env:ODAFC_PATH="E:\ODA\ODAFileConverter.exe"

python -m mapemgen.cli inventory `
  --site-folder "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge" `
  --site-id "1003" `
  --site-name "London Rd Cleveland Bridge" `
  --dataset "DCIS/Bathnes" `
  --out-dir "outputs/1003_LondonRdClevelandBridge"

python -m mapemgen.cli extract `
  --site-folder "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge" `
  --site-id "1003" `
  --out-dir "outputs/1003_LondonRdClevelandBridge"

python -m mapemgen.cli assign-geometry `
  --input "outputs/1003_LondonRdClevelandBridge/extracted_facts.partial.json" `
  --out-dir "outputs/1003_LondonRdClevelandBridge"
```

Shortened `extracted_facts.partial.json` example:

```json
{
  "site_id": "1003",
  "source_files": [
    {
      "source_file": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge/1003_2500Config_Mar24.pdf",
      "file_type": "pdf",
      "parser": "pdf_parser",
      "status": "parsed",
      "extracted_facts": [
        {
          "fact_name": "phase_label_from_controller_config",
          "payload": {
            "value": "Phase A"
          },
          "evidence_location": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge/1003_2500Config_Mar24.pdf -> page 1 line 16",
          "confidence": 0.65
        }
      ]
    }
  ]
}
```

Shortened `geometry_assignments.partial.json` example:

```json
{
  "site_id": "1003",
  "lanes": [
    {
      "lane_ref": "lane_1",
      "intersection_ref": "intersection_1",
      "source_fact_name": "lane_geometry_candidate_from_cad"
    }
  ],
  "assigned_facts": [
    {
      "fact_name": "stop_line_from_cad",
      "target_scope": {
        "intersection_ref": "intersection_1",
        "lane_ref": "lane_1"
      },
      "assignment_method": "nearest_lane_centroid"
    }
  ],
  "semantic_assignments": [
    {
      "fact_name": "phase_label_from_controller_config",
      "target_scope": {
        "intersection_ref": "intersection_1",
        "lane_ref": null,
        "phase_ref": "phase_A"
      },
      "assignment_method": "semantic_reference_extraction"
    }
  ],
  "movement_lane_mappings": [
    {
      "movement_ref": "movement_london_road_inbound_ahead",
      "phase_refs": ["phase_A"],
      "lane_ref": "lane_1",
      "intersection_ref": "intersection_1",
      "assignment_method": "lane_label_movement_match",
      "requires_context_match": false
    }
  ]
}
```
