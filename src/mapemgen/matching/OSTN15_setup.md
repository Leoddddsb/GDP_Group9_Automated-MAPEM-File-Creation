# OSTN15 Grid — Setup & Verification

> Required for accurate BNG→WGS84 coordinate conversion (`refPoint`, lane node
> geometry). Without the OSTN15 grid, pyproj silently falls back to a generic
> ~metre-accuracy transform instead of the sub-metre OSTN15 transformation.

---

## Why this matters

`transforms.py` converts British National Grid (EPSG:27700) eastings/northings to
WGS84 lat/lon via:

```python
Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
```

pyproj picks the *best available* operation. The best one for the UK is **OSTN15**
(a NTv2 grid shift, ~0.1 m accuracy). If its grid file isn't installed, pyproj
**silently** uses a 7-parameter Helmert transform instead — roughly **2–7 m** off.
The function is named `bng_to_wgs84_OSTN15`, but the name alone does not install
the grid.

The engine detects this and emits a `warnings` entry (`ostn15_grid_missing`,
severity high) on every run until the grid is present — so the degradation is
never silent. Coordinates are still produced; only their accuracy is affected.

Grid file: **`uk_os_OSTN15_NTv2_OSGBtoETRS.tif`**

---

## Install — option A: pyproj sync (online, easiest)

On a machine with internet access to `cdn.proj.org`:

```bash
# just the OSTN15 grid
pyproj sync --file uk_os_OSTN15_NTv2_OSGBtoETRS.tif

# or all UK grids
pyproj sync --bbox -8,49,2,61
```

This downloads into pyproj's user data dir automatically; no code change needed.

## Install — option B: offline (air-gapped / restricted network)

1. On any online machine, download the grid from the PROJ CDN:
   `https://cdn.proj.org/uk_os_OSTN15_NTv2_OSGBtoETRS.tif`
2. Copy the `.tif` into the PROJ data directory on the target machine. Find it with:
   ```bash
   python -c "import pyproj; print(pyproj.datadir.get_data_dir())"
   ```
   Place the file directly in that directory.
3. (Alternative) put the file anywhere and point PROJ at it:
   ```bash
   export PROJ_DATA=/path/to/grids        # Linux/macOS
   # or set PROJ_DATA as a system env var on Windows
   ```

## Install — option C: conda

```bash
conda install -c conda-forge proj-data    # ships the full PROJ grid set
```

---

## Verify it worked

```bash
python -c "
from pyproj.transformer import TransformerGroup
g = TransformerGroup('EPSG:27700','EPSG:4326')
print('OSTN15 available:', len(g.unavailable_operations) == 0)
print('best op:', g.transformers[0].description)
"
```

Expected after install: `OSTN15 available: True` and the best op naming OSTN15 /
OSGB36, with **no** "missing Grid" warning.

Then a matching run should no longer list `ostn15_grid_missing` in its `warnings`.

Quick numeric sanity check (a Leeds point):

```bash
python -c "
from pyproj import Transformer
import warnings; warnings.simplefilter('error')
t = Transformer.from_crs('EPSG:27700','EPSG:4326', always_xy=True)
print(t.transform(429157, 434672))   # ~(-1.5587, 53.8075); no warning if grid present
"
```

If this raises a `UserWarning` about a missing grid, the grid is still not found.

---

## Notes

- No code change is required — once the grid is installed, the existing
  `bng_to_wgs84_OSTN15` automatically uses it.
- The same applies anywhere lane geometry is converted (node deltas), not just
  `refPoint`.
- Sandbox/CI environments often block `cdn.proj.org`; use option B or C there.
