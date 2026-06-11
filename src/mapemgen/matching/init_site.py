"""
init_site.py
============
Scaffold a new per-site config for the matching engine. Generates
`site_config_<id>.yaml` with the right structure and TBD placeholders, so adding
a site is fill-in-the-blanks rather than copy-paste-and-hope.

    python init_site.py 5040 --name "Whitecross" --authority "Leeds City Council"
    python init_site.py 1234 --authority "Bath & NE Somerset" --out ./configs/

Required human input after generation (marked TBD in the file):
  region_code, crs_source, dummy_phases, and any manual/priority overrides.
"""
import argparse
import os
import sys
from datetime import date

TEMPLATE = """\
# =============================================================================
# Site Configuration — {site_id}{name_suffix}
# =============================================================================
# Per-site config consumed by matching_engine.py alongside matching_rules.yaml.
# One file per site. Anything omitted falls back to matching_rules.yaml `config:`.
# Items marked TBD MUST be confirmed before a production run.
# =============================================================================

# 0. Site metadata (informational; not used by engine logic)
site:
  id:          "{site_id}"
  name:        "{name}"
  authority:   "{authority}"
  description: "TBD: junction type / road names"
  source_files:
    pdf:       "TBD"
    dwg:       "TBD"
  prepared_by: "TBD"
  prepared_on: "{today}"

# =============================================================================
# 1. REQUIRED project-level config (overrides matching_rules.yaml `config:`)
# =============================================================================
station_id: 100                  # sender ITS-S id; project-chosen integer
region_code: 50000               # TBD: 50 (UK) + 3-digit authority code
default_lane_width_m: 3.5        # UK urban standard; override if this site differs
crs_source: EPSG:27700           # TBD: confirm the DWG/DXF is BNG, not local coords

# =============================================================================
# 2. REQUIRED site-specific domain knowledge (cannot be auto-extracted)
# =============================================================================
# Dummy phases: letters with Type="D" in the PDF USE OF PHASES table. These are
# controller placeholders, NOT real signal groups — they MUST be excluded from
# signalGroup mapping. List them here.
dummy_phases: []                 # TBD: e.g. [U, V, W, X, Y, Z]

# Conflict-area hint (optional): helps refPoint extraction pick the right polygon.
conflict_area:
  layer_name_hint: "TBD"
  type: "polygon"

# =============================================================================
# 3. OPTIONAL manual overrides (fill ONLY if auto-extraction is wrong)
# =============================================================================
# Each manual.* entry becomes a highest-priority fact, beating all auto sources.
manual:
  # refpoint:
  #   lat:  53.8007550
  #   long: -1.5490770
  #   note: "Hand-picked centre."
  # intersection_id: {site_id_int}
  # lanetype_overrides:
  #   - laneID: 12
  #     value: crosswalkLane
  #     reason: "Verified — Toucan crossing."

# =============================================================================
# 4. OPTIONAL priority overrides (when this site's data quality differs)
# =============================================================================
# Adjust priority for specific (target, fact_name) pairs. Labels: P1<P2<P3<F.
# Leave empty for most sites.
priority_overrides: []
  # - target: mapData.intersections[].refPoint.lat
  #   fact_name: junction_centre_from_open_street_map
  #   priority: P1     # this site's OSM is better than its CAD geometry

# =============================================================================
# 5. OPTIONAL parser hints (passed to Week-2 parsers)
# =============================================================================
parser_hints:
  pdf:
    site_id_page: 1
    use_of_phases_page: null       # TBD
    stage_table_page: null         # TBD
  cad:
    lane_centerline_layer: ""      # TBD; blank = auto-detect
    stop_line_layer: ""            # TBD
  gis:
    osm_bbox_wgs84:
      min_lat: null                # TBD
      max_lat: null
      min_long: null
      max_long: null

# =============================================================================
# 6. OPTIONAL sanity-check expectations (cross-checked into validation_report)
# =============================================================================
expected:
  num_intersections: 1
  num_lanes_min: null              # TBD
  num_lanes_max: null
  num_signal_groups_min: null
  num_signal_groups_max: null
# =============================================================================
# END
# =============================================================================
"""


def main(argv=None):
    p = argparse.ArgumentParser(description="Scaffold a new site_config_<id>.yaml")
    p.add_argument("site_id", help="site identifier, e.g. 5040 or 337L")
    p.add_argument("--name", default="TBD", help="site name")
    p.add_argument("--authority", default="TBD", help="road authority")
    p.add_argument("--out", default=".", help="output directory")
    p.add_argument("--force", action="store_true", help="overwrite if exists")
    args = p.parse_args(argv)

    # integer hint for the commented intersection_id override
    digits = "".join(c for c in str(args.site_id) if c.isdigit())
    site_id_int = digits or "0"

    content = TEMPLATE.format(
        site_id=args.site_id,
        name_suffix=f" ({args.name})" if args.name != "TBD" else "",
        name=args.name,
        authority=args.authority,
        today=date.today().isoformat(),
        site_id_int=site_id_int,
    )

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"site_config_{args.site_id}.yaml")
    if os.path.exists(path) and not args.force:
        print(f"[skip] {path} already exists (use --force to overwrite)",
              file=sys.stderr)
        return 1
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[ok] wrote {path}")
    print("     Next: fill the TBD fields — region_code, crs_source, "
          "dummy_phases are required before a production run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
