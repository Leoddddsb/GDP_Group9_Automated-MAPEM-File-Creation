# Quality and Robustness Metrics

## MAPEM Quality

- Syntax validity: MAPEM JSON schema and ASN.1 output generation.
- Completeness: required fields populated for lanes, approaches, node lists, connections, and signal groups.
- Geometry quality: lane centreline error, stop line error, signal head location error against Ground Truth.
- Semantic quality: movement accuracy, signal group accuracy, conflict relation accuracy.
- Internal consistency: unique lane IDs, valid `connectsTo` references, valid signal group references.

## Robustness

- Site success rate across all six Leeds sites.
- Hard failure rate where the program crashes instead of reporting a useful error.
- Manual intervention rate by field and by site.
- Parser adaptation effort for a new PDF template or CAD layer style.
- Warning quality: whether the report explains missing or unreliable data.

