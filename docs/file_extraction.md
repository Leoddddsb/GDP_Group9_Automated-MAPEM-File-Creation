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
| MOVA | File path, executable configuration, and file size | `mova_tools_manual_export_required`; file-size metadata | `.mova` is a proprietary binary dataset; full control facts must come from files exported by MOVA Tools |
| Unsupported extension | File path and extension | File-level `status: "unsupported"` with no extracted facts | The file remains visible for manual review without guessing its contents |

Every retained fact includes an `evidence_location` chain. For example, a CAD
fact extracted from a DWG inside a ZIP keeps the ZIP path, archive-member path,
and modelspace entity location.

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

### PDF OCR and Computer-vision Implementation Plan

Many local authorities may only provide a PDF as the final fallback. For those
sites, one-shot extraction from a scanned drawing is not realistic. The planned
approach is feature extraction plus spatial filtering:

1. Prefer CAD first when available. DWG/DXF geometry is treated as the strongest
   source for lanes, stop lines, road markings, and signal-head positions.
2. Use GIS/OSM/Ordnance Survey geometry as a coarse spatial filter. Road names,
   junction bounds, and approximate centre points narrow the candidate area and
   reduce unrelated clusters or secondary drawing information.
3. Convert PDF pages with embedded images to rendered images. `needs_future_recognition`
   means the page lacks extractable text; `pdf_image_page_candidate` means the
   page contains image objects and should go through OCR/CV.
4. Run OCR on cropped title blocks, notes, labels, phase/stage tables, and road
   labels. These outputs become text candidates with lower confidence than
   native PDF text unless they are corroborated by CAD/GIS.
5. Run computer vision and vector-geometry heuristics on drawing regions to
   produce low-confidence candidates for road markings, lane lines, arrows,
   stop lines, crossings, and signal-head symbols. Detected features stay as
   candidate facts until matched against CAD/GIS context.
6. Assign initial Step 2 confidence conservatively. CAD-confirmed geometry,
   OCR corroboration, and GIS spatial filtering are not applied in Step 2; they
   are Step 3 / evidence-fusion responsibilities.
7. For vector PDFs, read drawing objects directly from `pdfplumber` page
   structures. Lines, curves, and rectangles are retained as vector candidates
   before they are matched against CAD/GIS context.

This keeps PDF fallback useful without pretending that scanned drawings can
directly produce final MAPEM fields. The Step 2 output records the image page,
OCR text candidates, and raw CV line candidates; later matching/fusion must
decide whether they support MAPEM fields.

#### Current Image-recognition Process

The implementation is in `src/mapemgen/ingestion/pdf_cv.py`. It is a rule-based
fallback for PDF drawings, not a trained object-detection model.

Goal:

- keep useful drawing evidence when CAD is unavailable
- separate directly observed geometry from guessed road semantics
- mark every guessed semantic feature as requiring later CAD/GIS context match

Path A: vector PDF objects

1. Read `page.lines`, `page.curves`, and `page.rects` from `pdfplumber`.
2. Emit raw vector facts:
   `pdf_vector_page_candidate`, `pdf_vector_line_candidate`,
   `pdf_vector_curve_candidate`, and `pdf_vector_rect_candidate`.
3. Preserve PDF coordinates such as `x0`, `top`, `x1`, `bottom`, `width`,
   `height`, and `linewidth`.
4. Apply simple geometry rules to create low-confidence semantic candidates:
   lane lines, stop lines, crossings, arrows, road markings, and signal-head
   symbols.
5. Do not promote obvious page borders, full-page lines, full-page rectangles,
   or generic decorative curves to semantic road candidates. These objects stay
   available as raw vector facts only.

Path B: raster image pages

1. Render the page to pixels with `pymupdf` / `fitz`.
2. Run OCR with `pytesseract` and emit non-empty text as
   `pdf_ocr_text_candidate`.
3. Scan OCR text for control keywords such as `phase`, `stage`, `detector`,
   `timing`, and `control`.
4. Run OpenCV line detection on the rendered pixels:
   grayscale -> Otsu threshold -> morphology close -> Canny edges ->
   probabilistic Hough lines.
5. Emit raw pixel line facts as `pdf_cv_line_candidate`.
6. Derive low-confidence semantic candidates from those lines, such as
   `road_marking_candidate_from_pdf_cv`, `lane_line_candidate_from_pdf_cv`, and
   `stop_line_candidate_from_pdf_cv`.

Output rule:

- vector geometry is stronger than pixel CV because it comes from the PDF
  drawing structure
- OCR text is weaker than native PDF text because it comes from rendered pixels
- CV line detection only proves that a line-like shape was found; it does not
  prove the line is a road marking
- semantic drawing candidates always include `requires_context_match: true`
- when in doubt, keep raw geometry and suppress the guessed semantic candidate

### DXF and DWG Parser

Implement `src/mapemgen/ingestion/cad.py`.

Use `ezdxf` for DXF parsing. Emit:

- layer names
- entity counts
- coordinate bounds
- line and polyline geometry candidates
- text labels
- block references
- lane, stop line, crossing and signal-head candidates based on configurable
  layer-name and text-label rules

For DWG input, call ODA File Converter through `ezdxf.addons.odafc`, create a
temporary DXF, and run the same DXF parser. ODA File Converter is a required
runtime dependency when a site inventory contains `.dwg`. If it is not
installed, extraction stops with a clear error.

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
application. Full extraction must use MOVA Tools as an external conversion
boundary, in the same way that DWG extraction uses ODA File Converter:

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

The external tool is required because the repository samples are opaque binary
files, the binary schema is not published, and guessing byte offsets would
produce unreliable MAPEM evidence. TRL describes MOVA Tools as the official
program for creating, editing, and converting MOVA dataset files.

The Python integration must read a `MOVA_TOOLS_PATH` environment variable that
points to the installed MOVA Tools executable. The exact automated export
command must be confirmed against the installed MOVA Tools version before it is
enabled. If that version provides only a graphical export workflow, export the
files manually and place them in the site folder for the Python parsers.

## Dependency Policy

Add the libraries required by the implemented parsers to `pyproject.toml`.

Python packages are ordinary project dependencies. ODA File Converter and MOVA
Tools are external applications and must be documented in the README.

Dependency failures are handled as follows:

| Situation | Behaviour |
| --- | --- |
| Required Python package missing | Stop with an actionable error |
| `.dwg` encountered without ODA File Converter | Stop with an actionable error |
| `.mova` encountered without MOVA Tools | Stop full MOVA extraction with an actionable error |
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
modules and do not need additional parser packages. Full MOVA extraction
additionally requires the external MOVA Tools application described below.

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

Training a local PDF object detector uses another optional dependency group:

```powershell
python -m pip install -e ".[train]"
```

This installs `ultralytics` plus the PDF image-recognition packages. The
training command does not download or create human annotations. It uses the
current PDF vector/CV semantic candidates as weak pseudo-labels and trains a
local YOLO detector from those generated labels. Missing training packages stop
the command with a clear error.

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

## Usage

### 1. Optional: create a Step 1 site inventory

Run Step 1 for the site folder. Replace every value in angle brackets:

| Placeholder | What to enter |
| --- | --- |
| `<project-root>` | Absolute path of the repository root on the local machine |
| `<site-folder>` | Path of the folder containing all files for one traffic-signal site |
| `<site-id>` | Site identifier, for example `1003`, `1062`, or `397L` |
| `<site-name>` | Human-readable site name |
| `<dataset>` | Data source or local authority, for example `DCIS/Bathnes` or `Leeds` |

Template:

```powershell
cd "<project-root>"
.\mapem313\Scripts\Activate.ps1
$env:PYTHONPATH='src'
python -m mapemgen.cli inventory `
  --site-folder "<site-folder>" `
  --site-id "<site-id>" `
  --site-name "<site-name>" `
  --dataset "<dataset>"
```

Example:

```powershell
cd C:\Users\leovo\Desktop\GDP
.\mapem313\Scripts\Activate.ps1
$env:PYTHONPATH='src'
python -m mapemgen.cli inventory `
  --site-folder "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge" `
  --site-id "1003" `
  --site-name "London Rd Cleveland Bridge" `
  --dataset "DCIS/Bathnes"
```

The default output is:

```text
outputs/1003_LondonRdClevelandBridge/site_inventory.partial.json
```

Use `--out-dir <folder>` to choose another inventory output directory.

The Step 1 inventory is a separate output. Step 2 does not read it.

### 2. Extract MAPEM-relevant facts from the complete site folder

Pass the site folder directly to Step 2. Replace every value in angle brackets:

| Placeholder | What to enter |
| --- | --- |
| `<site-folder>` | Path of the folder containing all files for one site; nested folders are scanned recursively |
| `<site-id>` | Site identifier written into `extracted_facts.partial.json` |
| `<output-folder>` | Folder where `extracted_facts.partial.json` should be written |

Template:

```powershell
python -m mapemgen.cli extract `
  --site-folder "<site-folder>" `
  --site-id "<site-id>" `
  --out-dir "<output-folder>"
```

Example:

```powershell
python -m mapemgen.cli extract `
  --site-folder "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge" `
  --site-id "1003" `
  --out-dir "outputs/1003_LondonRdClevelandBridge"
```

The output is:

```text
outputs/1003_LondonRdClevelandBridge/extracted_facts.partial.json
```

A shortened output example:

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
    },
    {
      "source_file": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge/T1003 Cleveland Place - Standard.zip",
      "file_type": "zip",
      "parser": "zip_inventory_parser",
      "status": "parsed",
      "extracted_facts": [
        {
          "fact_name": "lane_geometry_candidate_from_cad",
          "payload": {
            "value": [[0.0, 0.0], [10.0, 5.0]]
          },
          "evidence_location": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge/T1003 Cleveland Place - Standard.zip -> archive member 1003_Cleveland Place_2023Version_Overlay.dwg -> modelspace entity 1 layer LANE_MAIN",
          "confidence": 0.70
        }
      ]
    }
  ]
}
```

The real file contains all scanned source files and all extracted facts. The
example above is intentionally shortened.

### 3. Optional: train a local PDF drawing detector

Use this when the current site folder contains PDF drawings and you want to
bootstrap an object detector from the low-confidence PDF drawing candidates.
Replace every value in angle brackets:

| Placeholder | What to enter |
| --- | --- |
| `<site-folder>` | Path of the folder containing all files for one site |
| `<training-output-folder>` | Empty or new folder where the generated YOLO dataset, manifest, and training runs should be written |

Template:

```powershell
python -m mapemgen.cli train-pdf-detector `
  --site-folder "<site-folder>" `
  --out-dir "<training-output-folder>"
```

Example:

```powershell
python -m mapemgen.cli train-pdf-detector `
  --site-folder "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge" `
  --out-dir "outputs/1003_LondonRdClevelandBridge_pdf_training"
```

To only generate and inspect the weak-label YOLO dataset without training:

```powershell
python -m mapemgen.cli train-pdf-detector `
  --site-folder "<site-folder>" `
  --out-dir "<training-output-folder>" `
  --dataset-only
```

Main outputs:

```text
<training-output-folder>/pdf_training_manifest.json
<training-output-folder>/weak_pdf_yolo_dataset/data.yaml
<training-output-folder>/weak_pdf_yolo_dataset/images/train/*.png
<training-output-folder>/weak_pdf_yolo_dataset/labels/train/*.txt
<training-output-folder>/training_runs/weak_pdf_yolo/
```

The dataset output directory must be empty or new. The command refuses to
overwrite an existing non-empty generated dataset directory.

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
geometry assignment
        |
        v
geometry_assignments.partial.json
```

## Geometry Assignment

Geometry assignment is the step after parsing and before MAPEM field matching.
It does not choose MAPEM fields, build `SiteModel`, or decide final lane
connectivity. Its only job is to add spatial scope to geometry evidence so that
multi-lane sites do not merge all geometry into one undifferentiated fact pool.

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
| `lanes[]` | Stable `lane_ref` values created from lane-like geometry facts |
| `assigned_facts[]` | Geometry facts with `target_scope.intersection_ref` and, when possible, `target_scope.lane_ref` |
| `geometry_summary` | Centroid, bounds, coordinate space, and PDF page reference when applicable |

Example:

```json
{
  "fact_id": "fact_00123",
  "fact_name": "stop_line_from_cad",
  "target_scope": {
    "intersection_ref": "intersection_1",
    "lane_ref": "lane_3"
  },
  "assignment_method": "nearest_lane_centroid",
  "distance_to_lane": 1.7
}
```

Rules:

- CAD and GIS geometry can be assigned by nearest geometry centroid.
- PDF page-space geometry is assigned only to lanes on the same PDF page and
  source file. It is not mixed with CAD modelspace or GIS coordinates.
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
