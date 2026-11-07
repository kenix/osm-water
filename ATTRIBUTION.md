# OSM water — sources and licences

These files are data, not program code. They are published separately from
any application binary and are downloaded by the app when needed.

## OpenStreetMap (every water file)

Contains information from **OpenStreetMap**, © OpenStreetMap contributors,
made available under the **Open Database License (ODbL) 1.0**.

- Source: https://www.openstreetmap.org, via the Geofabrik extracts at
  https://download.geofabrik.de (the sea from their coastline ways)
- Licence: https://opendatacommons.org/licenses/odbl/1-0/
- Copyright and attribution: https://www.openstreetmap.org/copyright
- Modifications: cut to one lake, river stretch or strip of sea; outlines simplified to
  1 m; reduced to the categories in `README.md`; labels placed at a
  feature's centre.

**Share-alike:** the water files are a derived database and are themselves
licensed under the ODbL 1.0. `waters.sh` in this repository reproduces them
from the public extracts.

## swisstopo (depth lines in Swiss lakes)

Depth lines derived from **swissBATHY3D**, © swisstopo, free geodata (OGD)
under the swisstopo terms of use: https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices

- Source: https://www.swisstopo.admin.ch/en/height-model-swissbathy3d
- Modifications: resampled to 5 m, contoured at 2, 5, 10, 20, 50 and 100 m
  below the lake surface, simplified to 1 m.

## Natural Earth (orientation layer)

`orient.json.gz` is made with **Natural Earth** data, public domain:
https://www.naturalearthdata.com (vector release v5.1.2). Cut to the region in
its `bbox` and simplified to 150 m.

## Credit in an app

The notice travels inside every file, in its `licence` field. An app that
shows the water credits "© OpenStreetMap contributors" and, where depth lines
show, "© swisstopo".
