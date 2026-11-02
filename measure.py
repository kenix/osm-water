"""Size of every water-related OSM feature on and around one lake, at a given
accuracy. Usage: python3 -I measure.py <lake.geojson> <details.geojson> <lake name> <tol_m> [out.geojson]"""
import collections, gzip, json, math, sys

CELL, NEAR = 50.0, 4  # grid metres; a feature counts if a vertex is within NEAR cells of the shore, or on the lake


def xy(p): return (p[0] * KX, p[1] * KY)


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = 0 if dx == dy == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def simplify(line, tol):
    if tol <= 0 or len(line) < 3: return line
    pts, keep, stack = [xy(p) for p in line], [False] * len(line), [(0, len(line) - 1)]
    keep[0] = keep[-1] = True
    while stack:
        i, j = stack.pop()
        best, k = 0, None
        for m in range(i + 1, j):
            d = seg_dist(pts[m], pts[i], pts[j])
            if d > best: best, k = d, m
        if k is not None and best > tol:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [p for p, f in zip(line, keep) if f]


def lines(g):
    t, c = g['type'], g['coordinates']
    return [[c]] if t == 'Point' else [c] if t == 'LineString' else c if t in ('Polygon', 'MultiLineString') else [r for p in c for r in p]


def remap(g, f):
    t, c = g['type'], g['coordinates']
    if t == 'Point': return g
    if t == 'LineString': return {'type': t, 'coordinates': f(c)}
    if t in ('Polygon', 'MultiLineString'): return {'type': t, 'coordinates': [f(r) for r in c]}
    return {'type': t, 'coordinates': [[f(r) for r in p] for p in c]}


def rnd(line): return [[round(x, 6), round(y, 6)] for x, y in line]


def inside(q, ring):
    c = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > q[1]) != (y2 > q[1]) and q[0] < (x2 - x1) * (q[1] - y1) / (y2 - y1) + x1: c = not c
    return c


lake_fc, det_fc, LAKES, tol = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), {sys.argv[3]}, float(sys.argv[4])
lake = [f for f in lake_fc['features'] if f['properties'].get('name') in LAKES]
LAT = sum(p[1] for l in lines(lake[0]['geometry']) for p in l) / sum(len(l) for l in lines(lake[0]['geometry']))
KX, KY = 111320 * math.cos(math.radians(LAT)), 110540
polys = [[[xy(p) for p in r] for r in f['geometry']['coordinates']] for f in lake if f['geometry']['type'] == 'Polygon']
polys +=[[[xy(p) for p in r] for r in poly] for f in lake if f['geometry']['type'] == 'MultiPolygon' for poly in f['geometry']['coordinates']]

near = set()
for poly in polys:
    for r in poly:
        for a, b in zip(r, r[1:]):
            n = max(1, int(math.dist(a, b) / CELL))
            for i in range(n + 1):
                cx, cy = int((a[0] + (b[0] - a[0]) * i / n) // CELL), int((a[1] + (b[1] - a[1]) * i / n) // CELL)
                near.update((cx + dx, cy + dy) for dx in range(-NEAR, NEAR + 1) for dy in range(-NEAR, NEAR + 1))


def on_lake(q):
    return any(inside(q, poly[0]) and not any(inside(q, h) for h in poly[1:]) for poly in polys)


def relevant(g):
    pts = [xy(p) for l in lines(g) for p in l]
    if any((int(q[0] // CELL), int(q[1] // CELL)) in near for q in pts): return True
    return on_lake(pts[0])


def category(t):
    if t.get('route') == 'ferry': return 'ferry route'
    # restrictions before nature: a reserve tagged no_entry is a no-go zone first
    if t.get('seamark:type') == 'restricted_area' or 'maxspeed' in t:  # maxspeed: the 300 m "Uferzone"
        return 'no entry' if t.get('seamark:restricted_area:restriction') == 'no_entry' else 'speed zone'
    if t.get('man_made') in ('pier', 'breakwater', 'groyne'): return 'pier/breakwater'
    if t.get('man_made') == 'bridge': return 'bridge'
    if t.get('waterway') in ('weir', 'dam', 'waterfall'): return 'weir'
    if t.get('waterway') == 'lock_gate' or t.get('lock') == 'yes' or t.get('water') == 'lock': return 'lock'
    if t.get('waterway') in ('rapids', 'whitewater') or 'whitewater' in t: return 'rapids'
    if t.get('waterway') == 'milestone': return 'river km'
    if t.get('leisure') in ('slipway', 'marina') or 'harbour' in t or 'mooring' in t: return 'harbour/slipway/mooring'
    if t.get('amenity') == 'ferry_terminal': return 'ferry stop'
    if t.get('leisure') in ('bathing_place', 'swimming_area') or t.get('sport') == 'swimming': return 'bathing'
    if t.get('natural') in ('shoal', 'reef') or t.get('seamark:sea_area:category') == 'shoal': return 'shoal'
    if t.get('natural') == 'wetland': return 'reed' if t.get('wetland') in (None, 'reedbed', 'swamp', 'marsh') else 'other'
    if t.get('boundary') == 'protected_area' or t.get('leisure') == 'nature_reserve': return 'protected area'
    if 'seamark:type' in t:
        s = t['seamark:type']
        if s == 'distance_mark': return 'river km'
        if s == 'lock_basin': return 'lock'
        if s in ('cable_submarine', 'pipeline_submarine', 'cable_overhead', 'crane', 'building', 'landmark'): return 'other'
        return 'seamark ' + ('light' if 'light' in s else 'buoy' if 'buoy' in s else 'beacon' if 'beacon' in s else 'other')
    if t.get('waterway') in ('river', 'canal'): return 'river'
    if t.get('waterway'): return 'stream/ditch'
    if 'depth' in t: return 'depth'
    if t.get('natural') == 'water' and t.get('water') in ('harbour', 'river', 'canal', 'lock'): return 'other water'
    return 'other'


stats, out = collections.defaultdict(lambda: [0, 0]), []
lake_g = [remap(f['geometry'], lambda l: rnd(simplify(l, tol))) for f in lake]
out += [{'type': 'Feature', 'properties': {'c': 'lake'}, 'geometry': g} for g in lake_g]
def off_lake(line):
    """The runs of a line outside the lake: OSM draws rivers on through it as flow lines."""
    runs, cur = [], []
    for a, b in zip(line, line[1:]):
        if on_lake(xy(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))):
            if len(cur) > 1: runs.append(cur)
            cur = []
        else:
            cur = cur or [a]
            cur.append(b)
    return runs + [cur] if len(cur) > 1 else runs


# ponytail: mappers tag the corners of a restricted area as buoys; the zone outline already shows them
corners = {tuple(p) for f in det_fc['features'] if f['geometry'] and f['properties'].get('seamark:type') == 'restricted_area'
           for l in lines(f['geometry']) for p in l}
for f in det_fc['features']:
    g, t = f['geometry'], f['properties']
    if not g or t.get('name') in LAKES or not relevant(g): continue
    c = category(t)
    if g['type'] == 'LineString' and g['coordinates'][0] == g['coordinates'][-1] and c != 'ferry route':
        continue  # osmium exports a closed way as a line and an area too; keep the area
    if g['type'] == 'Point' and 'buoy' in t.get('seamark:type', '') and tuple(g['coordinates']) in corners: continue
    if c.startswith('seamark') and g['type'] != 'Point': continue  # fairway, berth, bridge areas: drawn as marks they are slabs
    if c == 'river' and g['type'] == 'LineString':
        runs = off_lake(g['coordinates'])
        if not runs: continue
        g = {'type': 'MultiLineString', 'coordinates': runs}
    if 'seamark:distance_mark:distance' in t: t['distance'] = t['seamark:distance_mark:distance']
    if 'seamark:notice:category' in t: t['description'] = t['seamark:notice:category'].replace('_', ' ')
    keep = {k: t[k] for k in ('name', 'depth', 'seamark:type', 'seamark:restricted_area:restriction', 'access', 'boat', 'maxspeed', 'description', 'distance') if k in t}
    out.append({'type': 'Feature', 'properties': {'c': c, **keep}, 'geometry': remap(g, lambda l: rnd(simplify(l, tol)))})
for f in out:
    b = len(json.dumps(f, separators=(',', ':'), ensure_ascii=False).encode())
    stats[f['properties']['c']][0] += 1
    stats[f['properties']['c']][1] += b
blob = json.dumps({'type': 'FeatureCollection', 'features': out}, separators=(',', ':'), ensure_ascii=False).encode()
for c, (n, b) in sorted(stats.items(), key=lambda kv: -kv[1][1]):
    print(f'{c:26} {n:5}  {b / 1024:8.1f} KB')
print(f'TOTAL tol={tol} m: {len(out)} features, {len(blob) / 1024:.0f} KB raw, {len(gzip.compress(blob, 9)) / 1024:.0f} KB gzip')
if len(sys.argv) > 5: open(sys.argv[5], 'wb').write(blob)
