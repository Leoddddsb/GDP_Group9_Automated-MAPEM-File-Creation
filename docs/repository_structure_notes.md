# GitHub Repository Structure Notes

This repository is organised by project function, not by individual team member. Everyone should add work to the relevant module so the project stays easy to integrate and review.

## Top-Level Files

- `README.md`  
  Main project introduction. It explains the project goal, repository structure, quick start commands, and contribution rules.

- `pyproject.toml`  
  Python project configuration. Use this for package metadata and dependency groups.

- `.gitignore`  
  Prevents confidential raw data, generated outputs, Python caches, and local environment files from being committed.

## Source Code

- `src/mapemgen/`  
  Main Python package for the MAPEM generation prototype.

- `src/mapemgen/models.py`  
  Shared data model definitions, including `SiteModel`, `Lane`, and `SignalGroup`. Parser modules should eventually output data compatible with these models.

- `src/mapemgen/cli.py`  
  Command line interface. This is where user-facing commands such as `validate` and `generate` are exposed.

- `src/mapemgen/pipeline.py`  
  Connects validation and generation into one workflow.

- `src/mapemgen/io.py`  
  Shared file input/output helpers.

## Input Extraction Modules

- `src/mapemgen/ingestion/`  
  Code for extracting structured information from source data.

- `src/mapemgen/ingestion/cad.py`  
  CAD/DXF geometry extraction: lanes, stop lines, kerbs, signal poles, and CAD layer interpretation.

- `src/mapemgen/ingestion/pdf_tables.py`  
  PDF table extraction: phase tables, stage/phase relations, conflicting phase matrices, and intergreen tables.

- `src/mapemgen/ingestion/pdf_cv.py`  
  PDF image and computer vision extraction: site-map labels, stage arrows, signal head symbols, and diagram features.

- `src/mapemgen/ingestion/gis.py`  
  GIS and georeferencing: coordinate conversion, BNG/WGS84 transformation, and map alignment.

## MAPEM Output Modules

- `src/mapemgen/generators/`  
  Code that turns the shared `SiteModel` into output files.

- `src/mapemgen/generators/json_mapem.py`  
  Generates `mapem.json`, which is useful for inspection, debugging, and schema-style validation.

- `src/mapemgen/generators/asn1_mapem.py`  
  Generates `mapem.asn1`, which addresses the project brief requirement for ASN.1-style MAPEM output.

## Validation And Quality

- `src/mapemgen/validation/`  
  Validation and quality reporting code.

- `src/mapemgen/validation/report.py`  
  Generates `validation_report.json`. This should contain completeness checks, internal consistency checks, warnings, and quality metrics.

## Configuration

- `configs/`  
  Configuration templates for local project runs.

- `configs/sites.example.yaml`  
  Template for site-level configuration such as site ID, input file paths, coordinate system, and output directory.

- `configs/layer_rules.example.yaml`  
  Template for CAD layer interpretation rules.

## Schemas And Examples

- `schemas/site_model.schema.json`  
  JSON schema for the shared `SiteModel`. If `models.py` changes, this schema should be updated too.

- `examples/site_model.example.json`  
  Synthetic non-confidential example data used for tests and smoke runs.

## Documentation

- `docs/architecture.md`  
  High-level system architecture and data flow.

- `docs/project_plan.md`  
  Six-week project plan.

- `docs/quality_metrics.md`  
  MAPEM quality and robustness metrics.

- `docs/client_questions/first_meeting_questions.md`  
  Questions to raise with the client or supervisor.

- `docs/reflection/REFLECTION_TEMPLATE.md`  
  Template for recording what worked, what failed, and what data would improve automation.

- `docs/weekly_reports/W1_TEMPLATE.md`  
  Weekly report template.

## Data And Outputs

- `data/README.md`  
  Explains how local raw and processed data should be arranged. Do not commit confidential source files.

- `outputs/`  
  Local generated output directory. This is ignored by git and should contain generated `mapem.json`, `mapem.asn1`, and `validation_report.json` files during local runs.

## Tests

- `tests/`  
  Smoke tests and regression tests.

- `tests/test_generation.py`  
  Tests MAPEM JSON and ASN.1 generation.

- `tests/test_validation.py`  
  Tests validation on the synthetic example `SiteModel`.

## Contribution Rule

Do not add personal top-level folders. Put code, notes, examples, and tests into the matching project area above. If a module becomes large, create a focused subfolder under the relevant package, such as `src/mapemgen/ingestion/cad/`.

