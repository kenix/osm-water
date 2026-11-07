#!/bin/bash
# One lake or river stretch from OSM (and swissBATHY3D when given) into out/<slug>.json.gz.
# Usage: lake.sh <slug> <OSM lake name | key=v1,v2 for a river stretch> <bbox w,s,e,n> [<bathy dir> <lake level m>]
# SRC: space-separated source extracts (default the Swiss one); a border river needs both sides.
set -euo pipefail
S=$(cd "$(dirname "$0")" && pwd)
slug=$1 name=$2 bbox=$3 bathy=${4:-} level=${5:-}
W=$S/work/$slug
mkdir -p "$W"
parts=()
for src in ${SRC:-$S/src/switzerland-latest.osm.pbf}; do
  part=$W/part${#parts[@]}.pbf
  parts+=("$part")
  osmium extract -s smart -b "$bbox" "$src" -o "$part" -O
done
osmium merge "${parts[@]}" -o "$W/area.pbf" -O
# a river's own polygons become the water area, so keep them out of the details
river=; [[ $name == *=* ]] && river=1
x() { osmium tags-filter "$W/area.pbf" "${@:2}" -o "$W/$1.pbf" -O && osmium export "$W/$1.pbf" -u type_id -o "$W/$1.geojson" -O; }
x lake nwr/natural=water
if [ -n "$river" ]; then
  # one lake by id keeps its name (TITLE), so it is drawn with a shore; a stretch is 'water'
  label=water; [[ $name == @id=* && $name != *\;* && -n ${TITLE:-} ]] && label=$TITLE
  python3 -I "$S/clip.py" "$W/lake.geojson" "$name" "$bbox" "$W/river.geojson" "$label"
  mv "$W/river.geojson" "$W/lake.geojson"
  name=$label
fi
x marks n/place=town,city,village,island,islet w/place=island,islet r/place=island \
  nwr/natural=cape,peninsula,bay,beach nwr/amenity=ferry_terminal nwr/sport
x details nwr/man_made=pier,breakwater,groyne nwr/leisure=slipway,marina,bathing_place,swimming_area,nature_reserve \
  nwr/harbour nwr/mooring nwr/seamark:type nwr/route=ferry nwr/amenity=ferry_terminal \
  nwr/natural=shoal,reef,wetland${river:-,water} nwr/wetland nwr/boundary=protected_area nwr/waterway nwr/depth \
  nwr/man_made=bridge nwr/lock nwr/water=lock
python3 -I "$S/measure.py" "$W/lake.geojson" "$W/details.geojson" "$name" 1 "$W/water.geojson" | tail -1
depth=
if [ -n "$bathy" ]; then
  SURFACE=$level python3 -I "$S/bathy.py" "$bathy" 5 1 "$W/depth.geojson" | tail -1
  depth=$W/depth.geojson
fi
python3 -I "$S/build.py" "$slug" "$name" "$W/lake.geojson" "$W/marks.geojson" "$W/water.geojson" $depth
