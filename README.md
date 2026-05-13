# GDP Group 9: Automated MAPEM File Creation

Engineering scaffold for an Imperial College Group Design Project on automated MAPEM generation from traffic signal site data.

The project investigates how far existing local authority site records can be converted into MAPEM topographic data. The planned workflow ingests CAD/PDF/GIS-derived information, maps it into a shared `SiteModel`, generates both MAPEM JSON and ASN.1-style output, and produces a validation report that explains quality, missing data, and manual intervention.

## Repository Scope

This repository is structured as one engineering project, not one folder per person.

- `src/mapemgen/`: Python package for ingestion, modelling, generation, validation, and pipeline orchestration.
- `configs/`: Example site configuration and CAD layer rules.
- `schemas/`: JSON schema for the shared intermediate model.
- `examples/`: Non-confidential sample input data.
- `docs/`: Project plan, architecture, quality metrics, weekly report templates, and client questions.
- `tests/`: Smoke tests for the shared model, generators, and validation report.

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

