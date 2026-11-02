#!/bin/bash
# Every water and the orientation layer into out/, plus manifest.json for the release tag given.
# Usage: waters.sh <release tag>   (sources are fetched into src/ once; delete a file there to refresh it)
set -euo pipefail
S=$(cd "$(dirname "$0")" && pwd)
cd "$S"
mkdir -p work
release=$1
GF=https://download.geofabrik.de/europe
NE=https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson
BATHY=https://data.geo.admin.ch/ch.swisstopo.swissbathy3d

get() { [ -s "$2" ] || { mkdir -p "$(dirname "$2")"; curl -sSfL -o "$2" "$1"; }; }
get $GF/switzerland-latest.osm.pbf src/switzerland-latest.osm.pbf
for r in freiburg-regbez tuebingen-regbez; do get $GF/germany/baden-wuerttemberg/$r-latest.osm.pbf src/de/$r.osm.pbf; done
get $GF/germany/bayern/schwaben-latest.osm.pbf src/de/schwaben.osm.pbf
get $GF/germany/hessen-latest.osm.pbf src/de/hessen.osm.pbf
for n in admin_0_boundary_lines_land admin_0_countries populated_places_simple lakes lakes_europe rivers_lake_centerlines rivers_europe; do
  get $NE/ne_10m_$n.geojson src/ne/ne_10m_$n.geojson
done
bathy() {  # swissBATHY3D lake grid (ESRI ASCII, 1 m) into src/bathy/<lake>/
  [ -d src/bathy/$1 ] && return
  get $BATHY/swissbathy3d_$1/swissbathy3d_$1_2056_5728.esriasciigrid.zip src/bathy/$1.zip
  mkdir -p src/bathy/$1 && unzip -qjo src/bathy/$1.zip '*.asc' -d src/bathy/$1
}
for l in zuerichsee thunersee vierwaldstaettersee; do bathy $l; done

# slug | OSM name, or key=values for a river stretch | bbox w,s,e,n | swissBATHY3D lake and its surface (m a.s.l.) | sources | title
WATERS=(
  "zuerichsee|Zürichsee|8.50,47.15,9.05,47.40|zuerichsee 405.9||Lake Zurich"
  "greifensee|Greifensee|8.62,47.32,8.74,47.39|||Greifensee"
  "vierwaldstaettersee|Vierwaldstättersee|8.20,46.89,8.66,47.10|vierwaldstaettersee 433.6||Lake Lucerne"
  "thunersee|Thunersee|7.58,46.62,7.92,46.79|thunersee 557.7||Lake Thun"
  "rhein_schaffhausen|water=river,canal|8.58,47.64,8.88,47.72||src/switzerland-latest.osm.pbf src/de/freiburg-regbez.osm.pbf|Rhine: Stein am Rhein to Rheinfall"
  "donau_ulm|water=river,canal|9.90,48.36,10.12,48.43||src/de/tuebingen-regbez.osm.pbf src/de/schwaben.osm.pbf|Danube: Ulm"
  "main_frankfurt|water=river,canal|8.52,50.07,8.82,50.14||src/de/hessen.osm.pbf|Main: Frankfurt"
)
for w in "${WATERS[@]}"; do
  IFS='|' read -r slug name bbox bathy src title <<< "$w"
  set -- $bathy
  SRC=${src:-src/switzerland-latest.osm.pbf} ./lake.sh "$slug" "$name" "$bbox" ${1:+src/bathy/$1} ${2:-} > "work/$slug.log" 2>&1 || { tail "work/$slug.log"; exit 1; }
  tail -1 "work/$slug.log"
done
python3 -I orient.py src/ne 4.5,45.0,12.0,51.0

printf '%s\n' "${WATERS[@]}" | python3 -I -c '
import json, os, sys
release, waters = sys.argv[1], {}
for line in sys.stdin.read().splitlines():
    slug, name, bbox, bathy, src, title = line.split("|")
    w, s, e, n = (float(v) for v in bbox.split(","))
    waters[slug] = {"title": title, "bbox": [w, s, e, n], "depth": bool(bathy),
                    "bytes": os.path.getsize(f"out/{slug}.json.gz")}
json.dump({"release": release, "format": 1,
           "base": f"https://github.com/kenix/osm-water/releases/download/{release}/",
           "licence": "ODbL-1.0", "attribution": "© OpenStreetMap contributors",
           "orient": {"file": "orient.json.gz", "bytes": os.path.getsize("out/orient.json.gz"), "licence": "public domain (Natural Earth)"},
           "waters": waters}, open("manifest.json", "w"), indent=1, ensure_ascii=False)
print("manifest:", len(waters), "waters")
' "$release"
