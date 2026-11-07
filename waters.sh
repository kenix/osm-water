#!/bin/bash
# Every water and the orientation layer into out/, plus manifest.json for the release tag given.
# Usage: waters.sh <release tag>   (sources are fetched into src/ once; delete a file there to refresh it)
set -euo pipefail
S=$(cd "$(dirname "$0")" && pwd)
cd "$S"
mkdir -p work
release=$1
GF_ROOT=https://download.geofabrik.de
NE=https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson
BATHY=https://data.geo.admin.ch/ch.swisstopo.swissbathy3d

get() { [ -s "$2" ] || { mkdir -p "$(dirname "$2")"; curl -sSfL -o "$2" "$1"; }; }
# Countries: Geofabrik path and the prefix of their generated waters. Each is cut down once to what
# lake.sh and survey.py read (FILTER is a superset of lake.sh's), and all into src/all.pbf so a border
# water has both banks.
COUNTRIES=(
  "europe/switzerland ch" "europe/germany de" "europe/austria at"
  "europe/great-britain gb" "europe/ireland-and-northern-ireland ie"
)
FILTER="nwr/natural=water,cape,peninsula,bay,beach,shoal,reef,wetland n/place=town,city,village,island,islet
  w/place=island,islet r/place=island nwr/amenity=ferry_terminal nwr/sport
  nwr/man_made=pier,breakwater,groyne,bridge nwr/leisure=slipway,marina,bathing_place,swimming_area,nature_reserve
  nwr/harbour nwr/mooring nwr/seamark:type nwr/route=ferry nwr/wetland nwr/boundary=protected_area nwr/waterway
  nwr/depth nwr/lock nwr/water=lock"
mkdir -p src/filtered work/survey work/coast
parts=() survey=() coast=()
for c in "${COUNTRIES[@]}"; do
  set -- $c
  get $GF_ROOT/$1-latest.osm.pbf src/$(basename $1)-latest.osm.pbf
  f=src/filtered/$2.pbf
  [ $f -nt src/$(basename $1)-latest.osm.pbf ] || osmium tags-filter src/$(basename $1)-latest.osm.pbf $FILTER -o $f -O
  parts+=($f)
  osmium tags-filter $f nwr/sport -o work/survey/$2-clubs.pbf -O
  osmium export work/survey/$2-clubs.pbf -u type_id -f geojsonseq -o work/survey/$2-clubs.geojsonseq -O
  osmium tags-filter $f nwr/natural=water -o work/survey/$2-water.pbf -O
  osmium export work/survey/$2-water.pbf -u type_id -f geojsonseq --geometry-types=polygon -o work/survey/$2-water.geojsonseq -O
  osmium tags-filter $f w/waterway=river,canal -o work/survey/$2-rivers.pbf -O
  osmium export work/survey/$2-rivers.pbf -f geojsonseq --geometry-types=linestring -o work/survey/$2-rivers.geojsonseq -O
  c=work/coast/$2
  [ $c.geojsonseq -nt src/$(basename $1)-latest.osm.pbf ] || { osmium tags-filter src/$(basename $1)-latest.osm.pbf w/natural=coastline -o $c.pbf -O
    osmium export $c.pbf -f geojsonseq --geometry-types=linestring -o $c.geojsonseq -O; }
  coast+=($c.geojsonseq)
  survey+=($2:work/survey/$2-clubs.geojsonseq:work/survey/$2-water.geojsonseq:work/survey/$2-rivers.geojsonseq)
done
# extracts taken on different days hold the same object at two versions; time-filter keeps today's
[ src/all.pbf -nt ${parts[0]} ] || { osmium merge "${parts[@]}" -o work/merged.pbf -O
  osmium time-filter work/merged.pbf -o src/all.pbf -O; }
for n in admin_0_boundary_lines_land admin_0_countries populated_places_simple lakes lakes_europe rivers_lake_centerlines rivers_europe; do
  get $NE/ne_10m_$n.geojson src/ne/ne_10m_$n.geojson
done
bathy() {  # swissBATHY3D lake grid (ESRI ASCII, 1 m) into src/bathy/<lake>/
  [ -d src/bathy/$1 ] && return
  get $BATHY/swissbathy3d_$1/swissbathy3d_$1_2056_5728.esriasciigrid.zip src/bathy/$1.zip
  mkdir -p src/bathy/$1 && unzip -qjo src/bathy/$1.zip '*.asc' -d src/bathy/$1
}
for l in zuerichsee thunersee vierwaldstaettersee; do bathy $l; done

# slug | OSM name, or key=values for a river stretch (@id=w1,r2 for one lake among others) | bbox w,s,e,n
# | swissBATHY3D lake and its surface (m a.s.l.) | (unused) | title | core w,s,e,n (where it wins over an
# overlapping box; the bbox when empty). By hand; survey.py writes generated.txt for every other club.
WATERS=(
  "zuerichsee|Zürichsee|8.50,47.15,9.05,47.40|zuerichsee 405.9||Lake Zurich|"
  "greifensee|Greifensee|8.62,47.32,8.74,47.39|||Greifensee|"
  "vierwaldstaettersee|Vierwaldstättersee|8.20,46.89,8.66,47.10|vierwaldstaettersee 433.6||Lake Lucerne|"
  "thunersee|Thunersee|7.58,46.62,7.92,46.79|thunersee 557.7||Lake Thun|"
  "rhein_schaffhausen|water=river,canal|8.58,47.64,8.88,47.72|||Rhine: Stein am Rhein to Rheinfall|"
  "donau_ulm|water=river,canal|9.90,48.36,10.12,48.43|||Danube: Ulm|"
  "main_frankfurt|water=river,canal|8.52,50.07,8.82,50.14|||Main: Frankfurt|"
)
printf '%s\n' "${WATERS[@]}" > work/hand.txt
python3 -I survey.py work/hand.txt generated.txt "${survey[@]}"
# the sea for the clubs on the coast, closed from the extracts' coastline ways
python3 -I sea.py generated.txt "${coast[@]}"
while IFS= read -r line; do WATERS+=("$line"); done < generated.txt
one() {
  IFS='|' read -r slug name bbox bathy src title core <<< "$1"
  set -- $bathy
  [ -n "${ONLY:-}" ] && [[ $slug != $ONLY ]] && return
  [ -s out/$slug.json.gz ] && [ -n "${KEEP:-}" ] && return
  SRC=src/all.pbf TITLE="$title" ./lake.sh "$slug" "$name" "$bbox" ${1:+src/bathy/$1} ${2:-} > "work/$slug.log" 2>&1 || { echo "FAILED $slug"; tail -3 "work/$slug.log"; return; }
  tail -1 "work/$slug.log"
}
export -f one
printf '%s\0' "${WATERS[@]}" | xargs -0 -n 1 -P ${JOBS:-6} bash -c 'one "$1"' _
python3 -I orient.py src/ne -11.0,45.0,17.5,61.0

printf '%s\n' "${WATERS[@]}" | python3 -I -c '
import json, os, sys
release, waters = sys.argv[1], {}
for line in sys.stdin.read().splitlines():
    slug, name, bbox, bathy, src, title, core = line.split("|")
    if not os.path.exists(f"out/{slug}.json.gz"):
        continue  # failed above, said so there
    waters[slug] = {"title": title, "bbox": [float(v) for v in bbox.split(",")], "depth": bool(bathy),
                    "bytes": os.path.getsize(f"out/{slug}.json.gz")}
    if core:
        waters[slug]["core"] = [float(v) for v in core.split(",")]
json.dump({"release": release, "format": 1,
           "base": f"https://github.com/kenix/osm-water/releases/download/{release}/",
           "licence": "ODbL-1.0", "attribution": "© OpenStreetMap contributors",
           "orient": {"file": "orient.json.gz", "bytes": os.path.getsize("out/orient.json.gz"), "licence": "public domain (Natural Earth)"},
           "waters": waters}, open("manifest.json", "w"), indent=1, ensure_ascii=False)
print("manifest:", len(waters), "waters")
' "$release"
