# Data Directory

Do not commit confidential raw data here.

Recommended local-only layout:

```text
data/
  raw/
    337L/
    378L/
    397L/
    573L/
    950L/
    982L/
  processed/
    397L/
      site.dxf
      cad_geometry.partial.json
      phase_logic.partial.json
      signal_locations.partial.json
```

Use `examples/` for synthetic or anonymised data that can be committed.

