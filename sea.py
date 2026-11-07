"""Sea strips for the clubs on the coast: the clubs survey.py found no water for (generated.txt.none) that lie
within 2 km of the sea, grouped like river clubs, each group's sea 20 km along the coast and 5 km out.
Usage: python3 -I sea.py <generated.txt> <coastline.geojsonseq>...
The sea comes from the OSM coastline (natural=coastline ways, ODbL, out of the Geofabrik extracts), closed
into polygons per strip here: osmdata.openstreetmap.de's ready polygons were unreachable in 2026-11.
Appends one line per strip to generated.txt (selector 'sea', which lake.sh reads from work/sea/<slug>.geojson)
and writes those files. A strip is the box 20 km around its clubs, then each side pulled in to 5 km beyond the
farthest land in that direction, so open sea ends 5 km out while a coast keeps its 20 km both ways."""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from survey import CORE, box, clusters, k, seg, slugify  # noqa: E402

COAST = 2_000    # m: a club farther from the sea than this is not a sea club (ACHTER Köln, in a park)
ALONG = 20_000   # m of coast each way
OUT = 5_000      # m out to sea


def coast(paths):
    """The natural=coastline ways in osmium's geojsonseq exports, as ([lng, lat] points, bbox)."""
    ways = []
    for path in paths:
        for line in open(path, encoding='utf-8'):
            if not line.strip():
                continue
            pts = json.loads(line.lstrip('\x1e'))['geometry']['coordinates']
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            ways.append((pts, (min(xs), min(ys), max(xs), max(ys))))
    return ways


def chain(ways):
    """Ways joined end to start into the longest lines they make."""
    starts = {tuple(w[0]): i for i, w in enumerate(ways)}
    ends = {tuple(w[-1]): i for i, w in enumerate(ways)}
    done, out = set(), []
    for i, w in enumerate(ways):
        if i in done:
            continue
        done.add(i)
        line = list(w)
        while (j := starts.get(tuple(line[-1]))) is not None and j not in done:
            done.add(j)
            line += ways[j][1:]
        while (j := ends.get(tuple(line[0]))) is not None and j not in done:
            done.add(j)
            line = ways[j][:-1] + line
        out.append(line)
    return out


def cut_line(line, bb):
    """The parts of line inside bb (Liang-Barsky per segment)."""
    w, s, e, n = bb
    parts, cur = [], None
    for a, b in zip(line, line[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t0, t1 = 0.0, 1.0
        for p, q in ((-dx, a[0] - w), (dx, e - a[0]), (-dy, a[1] - s), (dy, n - a[1])):
            if p == 0:
                if q < 0:
                    t0, t1 = 1, 0
            elif p < 0:
                t0 = max(t0, q / p)
            else:
                t1 = min(t1, q / p)
        if t0 > t1:
            if cur:
                parts.append(cur)
            cur = None
            continue
        p0 = [a[0] + t0 * dx, a[1] + t0 * dy] if t0 > 0 else a
        p1 = [a[0] + t1 * dx, a[1] + t1 * dy] if t1 < 1 else b
        if cur is None:
            cur = [p0]
        cur.append(p1)
        if t1 < 1:
            parts.append(cur)
            cur = None
    if cur:
        parts.append(cur)
    return parts


def area2(r):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:]))


def ring_inside(p, r):
    c = False
    for (x1, y1), (x2, y2) in zip(r, r[1:]):
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def sea_in(ways, bb):
    """The sea inside bb as [outer, holes...] rings (outer clockwise), closed along bb's edges: OSM draws
    the coastline with the land on its left, so the sea is on the right. None when a coastline ends inside
    bb (the extract stops there: a neighbour's coast is missing)."""
    w, s, e, n = bb
    lines = chain([pts for pts, (x0, y0, x1, y1) in ways if x0 <= e and x1 >= w and y0 <= n and y1 >= s])
    eps = 1e-9

    def pos(p):  # clockwise along bb from its north-west corner
        if abs(p[1] - n) < eps: return p[0] - w
        if abs(p[0] - e) < eps: return (e - w) + (n - p[1])
        if abs(p[1] - s) < eps: return (e - w) + (n - s) + (e - p[0])
        if abs(p[0] - w) < eps: return 2 * (e - w) + (n - s) + (p[1] - s)
        return None
    corners = [(0, [w, n]), (e - w, [e, n]), ((e - w) + (n - s), [e, s]), (2 * (e - w) + (n - s), [w, s])]
    perim = 2 * ((e - w) + (n - s))
    parts, rings = [], []
    for line in lines:
        closed = line[0] == line[-1]
        out = next((i for i, p in enumerate(line) if not (w < p[0] < e and s < p[1] < n)), None)
        if closed and out:  # an island across bb's edge: start it outside, so each part runs edge to edge
            line = line[out:-1] + line[:out + 1]
        for part in cut_line(line, bb):
            if closed and part[0] == line[0] and part[-1] == line[-1] and len(part) == len(line):
                rings.append(part)
            elif pos(part[0]) is None or pos(part[-1]) is None:
                return None
            else:
                parts.append(part)
    outers, holes = [], []
    left = list(range(len(parts)))
    while left:
        i, ring = left[0], []
        while True:
            left.remove(i)
            ring += parts[i]
            at = pos(parts[i][-1])
            # the next part starting clockwise from here, and the corners passed on the way
            def ahead(x): return (x - at) % perim
            nxt = min(range(len(parts)), key=lambda j: ahead(pos(parts[j][0])))
            to = ahead(pos(parts[nxt][0]))
            ring += [c for d, c in sorted(corners, key=lambda c: ahead(c[0])) if 0 < ahead(d) < to]
            if nxt not in left:
                break
            i = nxt
        ring.append(ring[0])
        outers.append([ring])
    for r in rings:
        (outers.append([r]) if area2(r) < 0 else holes.append(r))
    if not parts and holes and not any(area2(r) < 0 for r in rings):
        outers.append([[[w, n], [e, n], [e, s], [w, s], [w, n]]])  # only islands: all sea around them
    for h in holes:
        for o in outers:
            if ring_inside(h[0], o[0]):
                o.append(h)
                break
    return outers


def clip(ring, bbox):
    """Sutherland-Hodgman against bbox (as clip.py); [] when nothing is left."""
    ring = ring[:-1]
    for i, v, sign in ((0, bbox[0], 1), (0, bbox[2], -1), (1, bbox[1], 1), (1, bbox[3], -1)):
        def inside(p): return (p[i] - v) * sign >= 0
        def cross(a, b):
            t = (v - a[i]) / (b[i] - a[i])
            p = [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]
            p[i] = v
            return p
        out = []
        for a, b in zip(ring[-1:] + ring[:-1], ring):
            if inside(b):
                if not inside(a): out.append(cross(a, b))
                out.append(b)
            elif inside(a):
                out.append(cross(a, b))
        ring = out
        if not ring: return []
    return ring + ring[:1]


def clip_polys(polys, bbox):
    out = []
    for poly in polys:
        rings = [clip(r, bbox) for r in poly]
        if rings[0]:
            out.append([r for r in rings if r])
    return out


def strip(polys, clubs_box, full):
    """full, each side pulled in to OUT beyond the farthest land (or club) that way. Land is any vertex of the
    sea inside full: the coast. Vertices on full's edges are cut lines, not coast."""
    def cut(p):
        return any(abs(p[0] - v) < 1e-9 for v in (full[0], full[2])) or any(abs(p[1] - v) < 1e-9 for v in (full[1], full[3]))
    land = [p for poly in polys for r in poly for p in r if not cut(p)]
    w, s, e, n = clubs_box
    if land:
        w, s = min(w, min(p[0] for p in land)), min(s, min(p[1] for p in land))
        e, n = max(e, max(p[0] for p in land)), max(n, max(p[1] for p in land))
    kx, ky = k((s + n) / 2)
    return [max(full[0], w - OUT / kx), max(full[1], s - OUT / ky), min(full[2], e + OUT / kx), min(full[3], n + OUT / ky)]


def near_coast(p, ways):
    """A coastline within COAST metres of p."""
    w, s, e, n = box([p], COAST)
    kx, ky = k(p[1])
    q = (p[0] * kx, p[1] * ky)
    return any(seg(q, (a[0] * kx, a[1] * ky), (b[0] * kx, b[1] * ky)) <= COAST
               for pts, (x0, y0, x1, y1) in ways if x0 <= e and x1 >= w and y0 <= n and y1 >= s
               for a, b in zip(pts, pts[1:]))


def main():
    gen_path, paths = sys.argv[1], sys.argv[2:]
    clubs = []
    for line in open(gen_path + '.none', encoding='utf-8'):
        cc, latlng, oid, name = line.rstrip('\n').split('\t')
        lat, lng = map(float, latlng.split(','))
        clubs.append({'cc': cc, 'p': [lng, lat], 'name': name})
    ways = coast(paths)
    on = [c for c in clubs if near_coast(c['p'], ways)]
    slugs = {line.split('|')[0] for line in open(gen_path, encoding='utf-8') if line.strip()}
    lines = []
    os.makedirs('work/sea', exist_ok=True)
    for g in clusters([c['p'] for c in on]):
        cs = [on[i] for i in g]
        ps = [c['p'] for c in cs]
        full = box(ps, ALONG)
        polys = sea_in(ways, full)
        if polys is None:
            print(f"sea: skipped {cs[0]['name']}: a coastline ends inside its box (the extract stops there)")
            continue
        b = [round(v, 3) for v in strip(polys, box(ps, 0), full)]
        polys = clip_polys(polys, b)
        if not polys:
            continue
        name = next((c['name'] for c in cs if c['name']), '')
        title = 'Sea near ' + (name or 'rowing club')
        slug, i = f"{cs[0]['cc']}_sea_{slugify(name)}", 2
        while slug in slugs:
            slug, i = f"{cs[0]['cc']}_sea_{slugify(name)}_{i}", i + 1
        slugs.add(slug)
        json.dump({'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {'name': 'water'}, 'geometry': {'type': 'Polygon', 'coordinates': poly}}
            for poly in polys]}, open(f'work/sea/{slug}.geojson', 'w'))
        lines.append('|'.join([slug, 'sea', ','.join(map(str, b)), '', '', title, ','.join(map(str, box(ps, CORE)))]))
    with open(gen_path, 'a', encoding='utf-8') as f:
        f.write(''.join(line + '\n' for line in sorted(lines)))
    print(f'sea: {len(on)} of {len(clubs)} clubs without water on the coast, {len(lines)} strips')


if __name__ == '__main__' and sys.argv[1:] == ['test']:
    # east-west coast at lat 0.5 with the sea north, clubs on it: the north side ends OUT beyond the coast
    full = [10.1, 54.3, 10.5, 54.7]
    sea_ = [[[[10.1, 54.5], [10.11, 54.5], [10.3, 54.501], [10.49, 54.5], [10.5, 54.5], [10.5, 54.7], [10.1, 54.7], [10.1, 54.5]]]]
    b = strip(sea_, [10.3, 54.5, 10.3, 54.5], full)
    assert b[0] == full[0] and b[2] == full[2], b  # along the coast: all 20 km kept
    assert abs((b[3] - 54.501) * 110_540 - OUT) < 1, b  # out to sea: 5 km
    r = clip([[0, 0], [2, 0], [2, 2], [0, 0]], [0, 0, 1, 1])
    assert sorted(map(tuple, r[:-1])) == [(0, 0), (1, 0), (1, 1)] and r[0] == r[-1], r
    # the same coast as a way, drawn east to west (land on its left, south): the sea is the north half
    bb = [10.1, 54.3, 10.5, 54.7]
    way = [[10.6, 54.5], [10.3, 54.501], [10.0, 54.5]]
    island = [[10.2, 54.6], [10.21, 54.6], [10.21, 54.61], [10.2, 54.6]]  # counter-clockwise: land inside
    def wb(pts): return (pts, (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)))
    polys = sea_in([wb(way[:2]), wb(way[1:]), wb(island)], bb)  # two ways, chained
    assert len(polys) == 1 and len(polys[0]) == 2 and area2(polys[0][0]) < 0, polys
    assert abs(-area2(polys[0][0]) / 2 - 0.4 * 0.2) < 1e-3, polys
    # drawn west to east the land is north: the sea is the south half
    polys = sea_in([wb(way[::-1])], bb)
    assert len(polys) == 1 and max(p[1] for p in polys[0][0]) < 54.502, polys
    # a headland running out of the box splits the sea in two, west and east of it
    cape = [[10.6, 54.5], [10.4, 54.5], [10.4, 54.8], [10.3, 54.8], [10.3, 54.5], [10.0, 54.5]]
    polys = sea_in([wb(cape)], bb)
    assert len(polys) == 2 and abs(sum(-area2(p[0]) / 2 for p in polys) - (0.08 - 0.1 * 0.2)) < 1e-9, polys
    # an island across the box's east edge, its ring starting inside: the sea keeps the part outside it
    isle = [[10.45, 54.6], [10.45, 54.58], [10.55, 54.58], [10.55, 54.62], [10.45, 54.62], [10.45, 54.6]]
    polys = sea_in([wb(way), wb(isle)], bb)
    assert len(polys) == 1 and abs(-area2(polys[0][0]) / 2 - (0.08 - 0.05 * 0.04)) < 1e-3, polys
    # a coast ending inside the box (the extract stops): no sea
    assert sea_in([wb(way[:2])], bb) is None
    print('ok')
elif __name__ == '__main__':
    main()
