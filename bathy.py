"""Depth lines from swissBATHY3D ESRI ASCII tiles (LV95, 1 m, heights a.s.l.).
Usage: python3 -I bathy.py <dir of .asc> <grid step m> <simplify m> [out.geojson]"""
import glob, gzip, json, math, os, sys
from array import array

LEVELS = (2, 5, 10, 20, 50, 100)
src, step, tol = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
NAN = float('nan')

tiles = []
for f in sorted(glob.glob(os.path.join(src, '*.asc'))):
    with open(f) as fh:
        h = {k.lower(): float(v) for k, v in (fh.readline().split() for _ in range(6))}
    tiles.append((f, h))
X0 = min(h['xllcorner'] for _, h in tiles) // step * step
Y0 = min(h['yllcorner'] for _, h in tiles) // step * step
X1 = max(h['xllcorner'] + h['ncols'] for _, h in tiles)
Y1 = max(h['yllcorner'] + h['nrows'] for _, h in tiles)
W, H = int((X1 - X0) // step) + 1, int((Y1 - Y0) // step) + 1
grid = array('f', [NAN]) * (W * H)
top = -1e9
for f, h in tiles:
    xll, yll, nc, nr, nd = h['xllcorner'], h['yllcorner'], int(h['ncols']), int(h['nrows']), h['nodata_value']
    c0 = int((-(xll - X0)) % step)  # first column on the global step lattice
    with open(f) as fh:
        for _ in range(6): fh.readline()
        for r, line in enumerate(fh):
            y = yll + nr - 1 - r
            if (y - Y0) % step: continue
            vals = line.split()
            gy = int((y - Y0) // step)
            for c in range(c0, nc, step):
                v = float(vals[c])
                if v != nd:
                    grid[gy * W + int((xll + c - X0) // step)] = v
                    top = max(top, v)
top = float(os.environ.get("SURFACE", top))
print(f"grid {W}x{H} at {step} m, surface {top:.1f} m", file=sys.stderr)


def at(i, j):
    v = grid[j * W + i]
    return None if v != v else top - v  # depth


def lv95(e, n):
    y, x = (e - 2600000) / 1e6, (n - 1200000) / 1e6
    lng = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y ** 3
    lat = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x ** 3
    return [round(lng * 100 / 36, 6), round(lat * 100 / 36, 6)]


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = 0 if dx == dy == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def simplify(pts):
    if tol <= 0 or len(pts) < 3: return pts
    keep, stack = [False] * len(pts), [(0, len(pts) - 1)]
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
    return [p for p, f in zip(pts, keep) if f]


def contour(L):
    """Marching squares; segments keyed by the grid edge they cross, joined into lines."""
    def pt(edge):
        (i, j, d) = edge
        a, b = at(i, j), at(i + (d == 'h'), j + (d == 'v'))
        t = (L - a) / (b - a)
        return (X0 + (i + t * (d == 'h')) * step, Y0 + (j + t * (d == 'v')) * step)
    adj = {}
    for j in range(H - 1):
        for i in range(W - 1):
            q = (at(i, j), at(i + 1, j), at(i + 1, j + 1), at(i, j + 1))
            if None in q: continue
            edges = [(i, j, 'h'), (i + 1, j, 'v'), (i, j + 1, 'h'), (i, j, 'v')]  # bottom, right, top, left
            cut = [e for e, (a, b) in zip(edges, ((q[0], q[1]), (q[1], q[2]), (q[3], q[2]), (q[0], q[3]))) if (a < L) != (b < L)]
            for a, b in zip(cut[::2], cut[1::2]):  # ponytail: saddles paired arbitrarily, fine at display scale
                adj.setdefault(a, []).append(b)
                adj.setdefault(b, []).append(a)
    lines, seen = [], set()
    for s in sorted(adj, key=lambda e: len(adj[e])):  # open ends first, then loops
        if s in seen: continue
        line, cur = [s], s
        seen.add(s)
        while True:
            nxt = [n for n in adj[cur] if n not in seen]
            if not nxt: break
            cur = nxt[0]; seen.add(cur); line.append(cur)
        if len(line) > 2: lines.append([pt(e) for e in line])
    return lines


feats, stats = [], []
for L in LEVELS:
    ls = [simplify(l) for l in contour(L)]
    ls = [l for l in ls if len(l) > 2]
    feats.append({'type': 'Feature', 'properties': {'depth': L},
                  'geometry': {'type': 'MultiLineString', 'coordinates': [[lv95(*p) for p in l] for l in ls]}})
    stats.append(f'{L:4} m: {len(ls):5} lines, {sum(map(len, ls)):7} points')
blob = json.dumps({'type': 'FeatureCollection', 'features': feats}, separators=(',', ':')).encode()
print('\n'.join(stats))
print(f'TOTAL grid {step} m, tol {tol} m: {len(blob) / 1024:.0f} KB raw, {len(gzip.compress(blob, 9)) / 1024:.0f} KB gzip')
if len(sys.argv) > 4: open(sys.argv[4], 'wb').write(blob)
