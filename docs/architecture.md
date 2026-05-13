# Architecture

The project uses a shared intermediate model to isolate data extraction from MAPEM generation.

```text
Raw CAD/PDF/GIS sources
        |
        v
Format-specific extraction modules
        |
        v
Partial JSON outputs
        |
        v
SiteModel merge and human-in-the-loop correction
        |
        v
MAPEM JSON + ASN.1 generation
        |
        v
Validation report and quality metrics
```

## Modules

- `ingestion.cad`: DXF layer and geometry extraction.
- `ingestion.pdf_tables`: phase, stage, movement, and conflict table extraction.
- `ingestion.pdf_cv`: signal labels, site map symbols, and stage arrow recognition.
- `ingestion.gis`: coordinate transformation and georeferencing.
- `models`: shared `SiteModel` contract.
- `generators`: MAPEM JSON and ASN.1-style output.
- `validation`: structural checks and quality reporting.
- `pipeline`: end-to-end orchestration.

