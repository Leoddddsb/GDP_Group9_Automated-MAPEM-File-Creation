# Step 1 File Inventory Notes

This document explains the current local implementation of Step 1 `file_inventory`. The goal of Step 1 is to take one site folder as input and generate `site_inventory.partial.json`, recording which source files exist, their formats, basic readability status, filename hints, and the recommended parser for each file.

Step 1 is only a folder-level file inventory. It does not extract MAPEM facts, parse CAD geometry, read PDF/DOCX table content, or output later semantic fields such as `junction_type`, `controller_type`, `stream_count`, `site_level_hints`, or `manual_questions`.

## 1. Created and Modified Files

### 1.1 Core Implementation File

Location:

```text
src/mapemgen/ingestion/inventory.py
```

Purpose:

- Implements the main Step 1 file inventory logic.
- Provides `build_site_inventory(site_folder, site_id, site_name="", dataset="") -> dict`.
- Recursively scans all files under the input site folder.
- Creates one `source_files` entry for each discovered file.
- Summarises total file count, file type counts, readable file count, and unreadable file count.
- Recommends a first-version parser based on file extension.
- Generates `filename_hints` from filename keywords.
- For ZIP files, checks only the ZIP member list. It does not extract the ZIP and does not parse DWG content.

Main functions:

```text
build_site_inventory(...)
```

External entry point. It receives a site folder path and site metadata, then returns a Python dict that can be written directly as JSON.

```text
_iter_files(folder)
```

Recursively scans the folder and returns all regular files. The current implementation uses `Path.rglob("*")`.

```text
_build_source_file(path)
```

Creates one inventory entry for a single file, including:

- `file_path`
- `file_type`
- `file_size_bytes`
- `filename_hints`
- `readable_status`
- `parser_to_use`
- `notes`

```text
_file_type(path)
```

Reads the file extension and normalises it to lowercase. For example, `.8TX` becomes `8tx`.

```text
_filename_hints(path)
```

Generates filename hints from filename keywords:

| Filename keyword | Generated hint |
| --- | --- |
| `Spec`, `2500Config`, `Configuration` | `possible configuration file` |
| `Drawing`, `AsBuilt`, `DetailedDesign` | `possible drawing / layout file` |
| `UTCForm` | `possible UTC form` |
| `SCOOTDets` | `possible SCOOT detector data` |
| `RAMData` | `possible RAM / override data` |
| `MOVA` | `possible MOVA/control logic data` |

If a ZIP file's member list contains a `.dwg` file, the function also adds:

```text
possible CAD package
```

This means the ZIP may be a CAD drawing package. The current implementation only checks the file names inside the ZIP. It does not extract the ZIP and does not parse DWG content.

```text
_readability(path, file_type)
```

Checks basic readability. Current statuses:

| Status | Meaning |
| --- | --- |
| `text_readable` | Text-like files can be opened, such as `.txt` and `.8tx` |
| `archive_readable` | ZIP file can be opened and its directory table can be read |
| `available_not_directly_readable` | File exists, but Step 1 does not parse its content, such as `.pdf`, `.docx`, `.dwg`, `.dxf`, `.mova` |
| `available_unknown_format` | File exists, but the extension has no known parser |
| `unreadable` | File cannot be opened, or the ZIP is damaged/unreadable |

```text
_zip_readability(path)
```

Checks whether a ZIP file can be opened and whether its member list can be read.

```text
_zip_contains_extension(path, ".dwg")
```

Checks whether a standard ZIP file contains a member whose name ends in `.dwg`. It does not recursively open nested ZIP files and does not validate whether the DWG content itself is valid.

### 1.2 CLI Modified File

Location:

```text
src/mapemgen/cli.py
```

Specific additions:

- Added this import:

```python
from mapemgen.ingestion.inventory import build_site_inventory
```

- Added the `inventory` subcommand in `build_parser()`.
- Added five CLI arguments:
  - `--site-folder`
  - `--out-dir`
  - `--site-id`
  - `--site-name`
  - `--dataset`
- Added an `if args.command == "inventory"` branch in `main()`.
- The branch calls `build_site_inventory(...)` to generate the inventory dict.
- It writes `site_inventory.partial.json` using the existing `write_json(...)` helper.
- It returns exit code `0` after successful completion.

New command:

```bash
mapemgen inventory --site-folder <path> --out-dir <path> --site-id <id> --site-name <name> --dataset <dataset>
```

Arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `--site-folder` | Yes | Site folder to scan |
| `--out-dir` | No | Custom output folder for inventory JSON |
| `--site-id` | Yes | Site ID, such as `1003` or `397L` |
| `--site-name` | No | Site name. If omitted, the folder name is used |
| `--dataset` | No | Data source or local authority, such as `DCIS/Bathnes` or `Leeds` |

CLI flow:

1. Parse command-line arguments.
2. If the command is `inventory`, call `build_site_inventory(...)`.
3. Write the result as JSON with `write_json(...)`.
4. If `--out-dir` is omitted, write to:

```text
outputs/<input_site_folder_name>/site_inventory.partial.json
```

5. If `--out-dir` is provided, write to:

```text
<out-dir>/site_inventory.partial.json
```

The existing `validate` and `generate` commands are unchanged.

### 1.3 Test File

Location:

```text
tests/test_inventory.py
```

Purpose:

- Verifies the core Step 1 file inventory behaviour.
- Uses synthetic files only, so it does not depend on confidential raw data.
- Writes temporary test files under `outputs/`, which is already ignored by Git.

Current test coverage:

1. `build_site_inventory(...)` can scan `.txt`, `.8TX`, `.zip`, `.mova`, `.bin`, and `.docx`.
2. File type counts are correct.
3. `.8TX` is normalised to `8tx`.
4. `source_files` are sorted by path for stable output.
5. Parser routing is correct.
6. Readability status is correct.
7. `RAMData`, `MOVA`, `UTCForm`, `Spec`, and `Drawing` generate the expected hints.
8. A ZIP containing a `.dwg` member generates `possible CAD package`.
9. Output does not contain Step 2 semantic fields:
   - `junction_type`
   - `controller_type`
   - `stream_count`
   - `site_level_hints`
   - `manual_questions`
10. CLI writes `site_inventory.partial.json`.
11. If `--out-dir` is omitted, CLI writes to `outputs/<input_site_folder_name>/site_inventory.partial.json`.

## 2. First-Version Parser Routing Rules

The first-version parser routing rules are hardcoded in:

```text
src/mapemgen/ingestion/inventory.py
```

Current mapping:

| File type | Recommended parser |
| --- | --- |
| `pdf` | `pdf_parser` |
| `docx` | `docx_parser` |
| `dwg` | `cad_parser_after_conversion` |
| `dxf` | `cad_parser` |
| `zip` | `zip_inventory_parser` |
| `txt` | `ram_text_parser` |
| `8tx` | `ram_text_parser` |
| `mova` | `mova_availability_recorder` |
| `geojson` | `gis_parser` |
| `json` | `gis_parser` |
| `osm` | `gis_parser` |
| `gpkg` | `gis_parser` |
| `shp` | `gis_parser` |
| unknown extension | `manual_review` |

If the rules become more complex later, they can be moved into configuration files under `configs/`.

## 3. Overall Flow

The Step 1 flow is:

```text
site_folder_path
        |
        v
recursively scan all files
        |
        v
read each file's extension, size, and filename keywords
        |
        v
check basic readability
        |
        v
recommend parser by extension
        |
        v
calculate total_files / file_type_counts / readable_files / unreadable_files
        |
        v
write site_inventory.partial.json
```

Step 1 does not:

- parse PDF tables
- parse DOCX content
- convert DWG/DXF
- extract lanes, stop lines, or signal heads
- infer phases, stages, or streams
- generate MAPEM field evidence

## 4. Usage

### 4.1 Command Line Usage

From the project root, use this template. Replace values inside angle brackets with the values for the site being processed:

```powershell
$env:PYTHONPATH='src'; python -m mapemgen.cli inventory `
  --site-folder <site_folder_to_scan> `
  --site-id <site_id> `
  --site-name "<site_name_optional>" `
  --dataset "<dataset_or_local_authority_optional>"
```

`--out-dir` is optional. If omitted, the program uses the input site folder name as the output folder name.

For example, if the input folder is:

```text
local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge
```

The default output path is:

```text
outputs/1003_LondonRdClevelandBridge/site_inventory.partial.json
```

The output filename is fixed as `site_inventory.partial.json`.

Example:

```powershell
$env:PYTHONPATH='src'; python -m mapemgen.cli inventory `
  --site-folder local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge `
  --site-id 1003 `
  --site-name "London Rd Cleveland Bridge" `
  --dataset "DCIS/Bathnes"
```

If the environment has installed `mapemgen` as a command-line tool, this template can also be used:

```bash
mapemgen inventory \
  --site-folder <site_folder_path> \
  --site-id <site_id> \
  --site-name "<site_name_optional>" \
  --dataset "<dataset_optional>"
```

To specify a custom output folder, add:

```powershell
--out-dir <custom_inventory_output_folder>
```

Minimum required arguments:

```powershell
$env:PYTHONPATH='src'; python -m mapemgen.cli inventory `
  --site-folder <site_folder_to_scan> `
  --site-id <site_id>
```

If `--site-name` is omitted, the program uses the site folder name as `site_name`. If `--dataset` is omitted, `local_authority_or_dataset` is an empty string. If `--out-dir` is omitted, the program writes to `outputs/<input_site_folder_name>/site_inventory.partial.json`.

### 4.2 Direct Python Usage

The inventory builder can also be called directly from Python:

```python
from mapemgen.ingestion.inventory import build_site_inventory

inventory = build_site_inventory(
    "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge",
    site_id="1003",
    site_name="London Rd Cleveland Bridge",
    dataset="DCIS/Bathnes",
)
```

This function only returns a Python dict. It does not write a file. To write the result as JSON, use the project's existing `write_json(...)` helper:

```python
from mapemgen.io import write_json

write_json("outputs/1003_LondonRdClevelandBridge/site_inventory.partial.json", inventory)
```

## 5. Example Output

Example:

```json
{
  "site_id": "1003",
  "site_name": "London Rd Cleveland Bridge",
  "local_authority_or_dataset": "DCIS/Bathnes",
  "input_folder_path": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge",
  "inventory_summary": {
    "total_files": 3,
    "file_type_counts": {
      "8tx": 1,
      "txt": 1,
      "zip": 1
    },
    "readable_files": 3,
    "unreadable_files": 0
  },
  "source_files": [
    {
      "file_path": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge/1003_RAMData_Jan26.8tx",
      "file_type": "8tx",
      "file_size_bytes": 12345,
      "filename_hints": ["possible RAM / override data"],
      "readable_status": "text_readable",
      "parser_to_use": "ram_text_parser",
      "notes": ""
    },
    {
      "file_path": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge/T1003 Cleveland Place - Standard.zip",
      "file_type": "zip",
      "file_size_bytes": 67890,
      "filename_hints": ["possible CAD package"],
      "readable_status": "archive_readable",
      "parser_to_use": "zip_inventory_parser",
      "notes": ""
    }
  ]
}
```
