# GDP Group 9: Automated MAPEM File Creation

Engineering scaffold for an Imperial College Group Design Project on automated MAPEM generation from traffic signal site data.

The project investigates how far existing local authority site records can be converted into MAPEM topographic data. The planned workflow ingests CAD/PDF/GIS-derived information, maps it into a shared `SiteModel`, generates both MAPEM JSON and ASN.1-style output, and produces a validation report that explains quality, missing data, and manual intervention.

## Repository Scope

This repository is structured as one engineering project, not one folder per person.

For a fuller explanation of every folder and where team members should add work, see [`docs/repository_structure_notes.md`](docs/repository_structure_notes.md).

- `src/mapemgen/`: Core Python package. Shared code for data models, pipeline orchestration, file IO, and command line entry points should live here.
- `src/mapemgen/ingestion/`: Input extraction modules. Put CAD/DXF extraction, PDF table parsing, PDF computer vision, and GIS/georeferencing code here.
- `src/mapemgen/generators/`: MAPEM output modules. Put `mapem.json` and `mapem.asn1` generation logic here.
- `src/mapemgen/validation/`: Quality checks and validation reports. Put `validation_report.json` logic, completeness checks, consistency checks, and robustness metrics here.
- `configs/`: Project configuration templates. Site configuration, CAD layer rules, parser settings, and local processing templates belong here.
- `schemas/`: Shared data contracts. The `SiteModel` JSON schema and any future MAPEM-facing schema definitions belong here.
- `examples/`: Non-confidential sample data. Use synthetic or anonymised examples only.
- `docs/`: Project documentation. Architecture notes, project plan, quality metrics, client questions, weekly report templates, and reflection templates belong here.
- `tests/`: Smoke tests and regression tests for the shared model, parsers, generators, pipeline, and validation report.

## How To Add Work

Use the project structure above when adding new code or documents:

- CAD/DXF work goes in `src/mapemgen/ingestion/cad.py` or a focused submodule under `src/mapemgen/ingestion/`.
- PDF table extraction goes in `src/mapemgen/ingestion/pdf_tables.py` or related parser files.
- PDF image/CV work goes in `src/mapemgen/ingestion/pdf_cv.py`.
- GIS and coordinate conversion work goes in `src/mapemgen/ingestion/gis.py`.
- Shared data model changes go in `src/mapemgen/models.py` and must be reflected in `schemas/site_model.schema.json`.
- MAPEM JSON/ASN.1 output changes go in `src/mapemgen/generators/`.
- Quality metrics and validation checks go in `src/mapemgen/validation/`.
- Weekly notes, meeting notes, research notes, and reflection logs go in `docs/`.

Do not create personal top-level folders for individual contributions. If a module grows large, create a clear subfolder under the relevant package, for example `src/mapemgen/ingestion/cad/`.

## Commit And Data Rules

- Do not commit raw Leeds City Council files, including `.dwg`, `.dxf`, `.pdf`, `.docx`, or `.pptx` files.
- Do not commit generated outputs from `outputs/` unless the team explicitly agrees that a small anonymised example should be versioned.
- Add tests for new parser, generator, model, or validation behaviour where practical.
- Keep example files synthetic or anonymised.
- Update `docs/` when a design decision, data limitation, or client-facing finding changes.

## Confidentiality

The briefing material states that site data must be treated in confidence. Raw PDFs, DWGs, DXFs, Word documents, and slide decks are intentionally ignored by git. Keep original Leeds City Council data outside commits and use anonymised or synthetic samples in `examples/`.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m mapemgen.cli validate --input examples/site_model.example.json
python -m mapemgen.cli generate --input examples/site_model.example.json --out-dir outputs/demo
```

## Planned Outputs

- `mapem.json`: MAPEM-like JSON representation for inspection and schema checks.
- `mapem.asn1`: ASN.1-style MAPEM output for the project brief requirement.
- `validation_report.json`: Evidence of completeness, consistency, geometry checks, warnings, and manual intervention.
