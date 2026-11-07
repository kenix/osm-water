# OSM water

A map of the water a rower needs, one file per lake or river stretch: the
outline, shore landmarks (towns, rowing clubs, ferry stops, islands),
everything on the water that matters in a boat (reeds, shallows, no-entry and
speed zones, piers, harbours, weirs, locks, bridges, buoys and lights) and,
inside Switzerland, depth lines. Plus one small orientation layer (borders,
countries, cities, big lakes, main rivers) for zoomed-out views. Crewbook reads
them; nothing in here is specific to it.

Published as GitHub Release assets, one release per build. **The data is not
in this repository**: a release asset can be replaced, while binaries in the
history are in every clone for ever.

| File | What it is |
|---|---|
| `waters.sh` | Fetches the sources and builds every file of a release into `out/`, then writes `manifest.json` |
| `survey.py` | Every other water: the lake or river each `sport=rowing` object in OSM is on, one file per lake and per stretch of river around a group of clubs, into `generated.txt` |
| `lake.sh` | One water: OSM extract (`osmium-tool`), then the Python steps below |
| `clip.py` | A river stretch: its `natural=water` polygons clipped to the bbox |
| `measure.py` | The details on and around the water, by category |
| `bathy.py` | Depth lines from swissBATHY3D |
| `build.py` | One water's file |
| `orient.py` | The orientation layer from Natural Earth |
| `preview.html` | Both maps side by side, the swisstopo map and these files (serve this directory, open it) |
| `manifest.json` | The current release and every file in it |
| `ATTRIBUTION.md` | Sources and licences |

Building needs `osmium-tool`, Python 3 (standard library only), `curl` and
`unzip`: `./waters.sh water-YYYY-MM-DD`, then upload `out/*` to that release.
The countries are `COUNTRIES` in `waters.sh` (Geofabrik extracts, 7 GB for
CH, DE, AT, GB and IE; a run takes about an hour). The waters by hand are
`WATERS` there (a depth grid, a better title, a box cut by hand); every other
club gets its water from `survey.py`. Clubs on the sea (coastline, not
`natural=water`) get none yet; `generated.txt.none` lists them. `ONLY=<slug>`
builds one water, `KEEP=1` skips those already in `out/`, `JOBS` sets how
many build at once (6).

## Using it

`manifest.json` names the release, the download `base` and every water with
its `bbox` (`[w, s, e, n]`) and, where boxes overlap, its `core`: the part
around its own clubs where it wins over a neighbour (the smallest core holding
a point first, then the smallest box). Release assets send no CORS headers, so a browser
reads them through a server of its own (Crewbook: slipway's `/v1/water`).

Every file is gzip of UTF-8 JSON. Coordinates are `[lat, lng]`.

### `<slug>.json.gz`

```json
{"name": "Zürichsee", "licence": "© OpenStreetMap contributors, ODbL 1.0; depth © swisstopo (swissBATHY3D), OGD",
 "lake": [[[[47.36, 8.54], …]]],
 "marks": [{"k": "rowing", "n": "Seeclub Wädenswil", "r": 2, "p": [47.22196, 8.68689]}],
 "detail": {"type": "FeatureCollection", "features": [{"properties": {"c": "reed", "name": "…"}, "geometry": …}]},
 "depth": {"type": "FeatureCollection", "features": [{"properties": {"depth": 10}, "geometry": …}]}}
```

- `name` is the OSM lake name, or `water` for a river stretch (its many
  adjacent polygons are drawn without outlines, which would show as seams).
- `lake` holds polygons, each a list of rings; fill them even-odd.
- `marks` are labels: `k` kind (`city`, `town`, `village`, `island`, `islet`,
  `peninsula`, `cape`, `bay`, `beach`, `ferry`, `rowing`), `n` name, `r` rank
  (1 shows from zoom 11, 2 from zoom 13).
- `detail` is GeoJSON (`[lng, lat]`, as GeoJSON wants). `c` is the category:
  `reed`, `shoal`, `no entry`, `speed zone` (with `maxspeed`), `bathing`,
  `protected area`, `pier/breakwater`, `harbour/slipway/mooring`, `river`,
  `weir`, `lock`, `rapids`, `bridge`, `river km` (with `distance`),
  `ferry route`, `ferry stop`, and points only `seamark light|buoy|beacon|other`.
  Other properties when OSM has them: `name`, `description`, `seamark:type`.
- `depth` lines in metres below the surface (2, 5, 10, 20, 50, 100), GeoJSON.

A reader skips fields and categories it does not know.

### `orient.json.gz`

```json
{"licence": "Natural Earth, public domain", "bbox": [4.5, 45.0, 12.0, 51.0],
 "borders": [[[47.5, 7.6], …]], "lakes": [[[[46.4, 6.2], …]]], "rivers": [[[47.6, 8.6], …]],
 "places": [{"k": "country", "n": "Switzerland", "z": 4, "p": [46.72, 7.46]}]}
```

`borders` and `rivers` are lines, `lakes` polygons with rings. `places` are
`country`, `capital` or `city`; `z` is Natural Earth's suggested zoom for the
label.
