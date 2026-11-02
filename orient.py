"""Orientation layer for zoomed-out views: country borders and names, cities, big lakes, main rivers,
from Natural Earth 10m GeoJSON (public domain), as out/orient.json.gz (format in README.md).
Usage: python3 -I orient.py <dir of Natural Earth .geojson> <w,s,e,n>"""
import gzip, json, math, os, sys

src, (W, S, E, N) = sys.argv[1], [float(v) for v in sys.argv[2].split(',')]
KX, KY = 111320 * math.cos(math.radians((S + N) / 2)), 110540
TOL = 150  # metres; NE 10m is drawn at 1:10 million, finer than this adds bytes and no detail


def load(name):
    return json.load(open(os.path.join(src, f'ne_10m_{name}.geojson')))['features']


def near(line):
    return any(W <= x <= E and S <= y <= N for x, y in line)


def simplify(line):
    """Douglas-Peucker in metres; [lng, lat] in, [lat, lng] rounded to ~10 m out."""
    pts = [(x * KX, y * KY) for x, y in line]
    keep = [False] * len(line)
    keep[0] = keep[-1] = True
    stack = [(0, len(line) - 1)]
    while stack:
        i, j = stack.pop()
        (ax, ay), (bx, by) = pts[i], pts[j]
        dx, dy, best, k = bx - ax, by - ay, 0, None
        for m in range(i + 1, j):
            px, py = pts[m]
            t = 0 if dx == dy == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
            d = math.hypot(px - ax - t * dx, py - ay - t * dy)
            if d > best:
                best, k = d, m
        if k is not None and best > TOL:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [[round(y, 4), round(x, 4)] for (x, y), f in zip(line, keep) if f]


def within(p, ring):
    x, y, c = p[0], p[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def lines(g):
    return [g['coordinates']] if g['type'] == 'LineString' else g['coordinates'] if g['type'] == 'MultiLineString' else []


def polys(g):
    return [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates'] if g['type'] == 'MultiPolygon' else []


borders = [simplify(l) for f in load('admin_0_boundary_lines_land') for l in lines(f['geometry']) if near(l)]
rivers = [simplify(l) for name in ('rivers_lake_centerlines', 'rivers_europe') for f in load(name)
          for l in lines(f['geometry']) if near(l)]
lakes = [[simplify(r) for r in p] for name in ('lakes', 'lakes_europe') for f in load(name)
         for p in polys(f['geometry']) if near(p[0])]
# z: Natural Earth's own suggested zoom for the label, which matches web map zoom levels
places = []
for f in load('admin_0_countries'):
    p = f['properties']
    at = (p['LABEL_X'], p['LABEL_Y'])
    if not (W <= at[0] <= E and S <= at[1] <= N):  # France, Italy, Austria: label far away, so name the part in view
        rings = [poly[0] for poly in polys(f['geometry']) if near(poly[0])]
        grid = [(W + i / 4, S + j / 4) for i in range(int((E - W) * 4) + 1) for j in range(int((N - S) * 4) + 1)]
        inside = [g for g in grid if any(within(g, r) for r in rings)]
        if not inside: continue
        mx, my = sum(g[0] for g in inside) / len(inside), sum(g[1] for g in inside) / len(inside)
        at = min(inside, key=lambda g: (g[0] - mx) ** 2 + (g[1] - my) ** 2)
    places.append({'k': 'country', 'n': p['NAME_EN'], 'z': round(p['MIN_LABEL'], 1), 'p': [round(at[1], 4), round(at[0], 4)]})
for f in load('populated_places_simple'):
    p, (x, y) = f['properties'], f['geometry']['coordinates']
    if W <= x <= E and S <= y <= N and p['scalerank'] <= 8:
        places.append({'k': 'capital' if p['featurecla'] == 'Admin-0 capital' else 'city', 'n': p['name'],
                       'z': round(p['min_zoom'], 1), 'p': [round(y, 4), round(x, 4)]})

data = {'licence': 'Natural Earth, public domain', 'bbox': [W, S, E, N],
        'borders': borders, 'lakes': lakes, 'rivers': rivers, 'places': places}
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'orient.json.gz')
os.makedirs(os.path.dirname(out), exist_ok=True)
blob = gzip.compress(json.dumps(data, separators=(',', ':'), ensure_ascii=False).encode(), 9, mtime=0)
open(out, 'wb').write(blob)
print(f'orient: {len(borders)} borders, {len(lakes)} lakes, {len(rivers)} rivers, {len(places)} places, {len(blob) // 1024} KB')
