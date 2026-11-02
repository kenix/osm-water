"""One water's outline, shore landmarks, water details and depth as out/<slug>.json.gz (format in README.md).
Usage: python3 -I build.py <slug> <lake name> <lake.geojson> <marks.geojson> <detail.geojson> [depth.geojson]"""
import gzip, json, math, os, re, sys



def xy(p):
    return (p[0] * KX, p[1] * KY)


def seg_dist(p, a, b):
    ax, ay, bx, by = *a, *b
    dx, dy = bx - ax, by - ay
    t = 0 if dx == dy == 0 else max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def simplify(ring, tol):
    """Douglas-Peucker on a ring of [lng, lat], tolerance in metres."""
    pts = [xy(p) for p in ring]
    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    stack = [(0, len(ring) - 1)]
    while stack:
        i, j = stack.pop()
        best, k = 0, None
        for m in range(i + 1, j):
            d = seg_dist(pts[m], pts[i], pts[j])
            if d > best:
                best, k = d, m
        if k is not None and best > tol:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [[round(c, 6) for c in p] for p, f in zip(ring, keep) if f]


def inside(p, ring):
    x, y, c = p[0], p[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def centre(geom):
    t, c = geom['type'], geom['coordinates']
    if t == 'Point':
        return c
    ring = c[0] if t == 'Polygon' else c[0][0] if t == 'MultiPolygon' else c
    return [sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)]


slug, name, lake_fc, marks_fc = sys.argv[1], sys.argv[2], json.load(open(sys.argv[3])), json.load(open(sys.argv[4]))
LAKES = {name}  # one name only: the Zürichsee multipolygon already holds the Obersee, and overlaps cancel under even-odd fill

polys = []
for f in lake_fc['features']:
    if f['properties'].get('name') not in LAKES:
        continue
    g = f['geometry']
    polys += [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates'] if g['type'] == 'MultiPolygon' else []
raw = sum(len(r) for poly in polys for r in poly)
LAT0 = sum(p[1] for poly in polys for p in poly[0]) / sum(len(poly[0]) for poly in polys)
KX, KY = 111320 * math.cos(math.radians(LAT0)), 110540  # metres per degree
polys = [[simplify(r, 1.0) for r in poly] for poly in polys]
rings = [[xy(p) for p in r] for poly in polys for r in poly]
print(f'lake: {len(polys)} polygons, {raw} -> {sum(len(r) for r in rings)} points')


def shore_m(p):
    q = xy(p)
    return min(seg_dist(q, a, b) for r in rings for a, b in zip(r, r[1:]))


def on_water(p):
    q = xy(p)
    return any(inside(q, [xy(c) for c in poly[0]]) and not any(inside(q, [xy(c) for c in h]) for h in poly[1:]) for poly in polys)


# kind: (max metres from shore, rank) — rank 1 shows zoomed out, 2 zoomed in
RULES = {'city': (1500, 1), 'town': (1500, 1), 'village': (700, 2), 'island': (100, 1), 'islet': (100, 1),
         'peninsula': (300, 1), 'cape': (300, 1), 'bay': (300, 2), 'beach': (200, 2),
         'ferry': (200, 2), 'rowing': (300, 2)}
marks = []
for f in marks_fc['features']:
    t, name = f['properties'], f['properties'].get('name')
    if not name or f['geometry'] is None:
        continue
    kind = (t.get('place') or t.get('natural') or ('ferry' if t.get('amenity') == 'ferry_terminal' else None)
            or ('rowing' if t.get('sport') == 'rowing' else None))
    if kind not in RULES:
        continue
    p = centre(f['geometry'])
    d = 0 if kind in ('island', 'islet', 'bay') and on_water(p) else shore_m(p)
    if d > RULES[kind][0]:
        continue
    if kind == 'ferry':
        name = re.sub(r'\s*\((See|ZSG)\)$', '', name)
    marks.append({'k': kind, 'n': name, 'r': RULES[kind][1], 'p': [round(p[1], 6), round(p[0], 6)]})

# a ferry stop or village named like a town, island or peninsula near it repeats that label
named = [m for m in marks if m['k'] not in ('ferry', 'rowing')]
def dup(m):
    return any(o is not m and o['k'] != m['k'] and (o['n'] in m['n'] or m['n'] in o['n'])
               and math.dist(xy(o['p'][::-1]), xy(m['p'][::-1])) < 2500
               for o in named)
marks = [m for m in marks if m['k'] not in ('ferry', 'village') or not dup(m)]
marks = list({(m['k'], m['n']): m for m in marks}.values())
counts = {}
for m in marks:
    counts[m['k']] = counts.get(m['k'], 0) + 1
print('marks:', len(marks), counts)

lake = [[[[c[1], c[0]] for c in r] for r in poly] for poly in polys]
LICENCE = '© OpenStreetMap contributors, ODbL 1.0' + ('; depth © swisstopo (swissBATHY3D), OGD' if len(sys.argv) > 6 else '')
data = {'name': sys.argv[2], 'licence': LICENCE, 'lake': lake, 'marks': marks}
for key, path in (('detail', sys.argv[5]), ('depth', sys.argv[6] if len(sys.argv) > 6 else None)):
    fc = json.load(open(path)) if path else {'type': 'FeatureCollection', 'features': []}
    fc['features'] = [f for f in fc['features'] if f['properties'].get('c') not in ('lake', 'stream/ditch', 'other')]
    data[key] = fc
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', f'{slug}.json.gz')
os.makedirs(os.path.dirname(out), exist_ok=True)
blob = gzip.compress(json.dumps(data, separators=(',', ':'), ensure_ascii=False).encode(), 9, mtime=0)
open(out, 'wb').write(blob)
print('wrote', out, len(blob) // 1024, 'KB')
