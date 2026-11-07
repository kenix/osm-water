"""Sea strips for the clubs on the coast: the clubs survey.py found no water for (generated.txt.none) that lie
within 2 km of the sea, grouped like river clubs, each group's sea 20 km along the coast and 5 km out.
Usage: python3 -I sea.py <water-polygons-split-4326.zip> <generated.txt>
The sea comes from osmdata.openstreetmap.de's water polygons (the OSM coastline turned into polygons, ODbL).
Appends one line per strip to generated.txt (selector 'sea', which lake.sh reads from work/sea/<slug>.geojson)
and writes those files. A strip is the box 20 km around its clubs, then each side pulled in to 5 km beyond the
farthest land in that direction, so open sea ends 5 km out while a coast keeps its 20 km both ways."""
import json, os, struct, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from survey import CORE, box, clusters, k, poly_dist, slugify  # noqa: E402

COAST = 2_000    # m: a club farther from the sea than this is not a sea club (ACHTER Köln, in a park)
ALONG = 20_000   # m of coast each way
OUT = 5_000      # m out to sea


def pieces(path, boxes):
    """The water polygons whose bbox meets one of boxes, as [outer, holes...] rings of [lng, lat]."""
    def meets(x0, y0, x1, y1):
        return any(x0 <= b[2] and x1 >= b[0] and y0 <= b[3] and y1 >= b[1] for b in boxes)
    with zipfile.ZipFile(path) as z, z.open(next(n for n in z.namelist() if n.endswith('.shp'))) as f:
        f.read(100)
        while head := f.read(8):
            rec = f.read(struct.unpack('>2i', head)[1] * 2)
            kind, *bb = struct.unpack('<i4d', rec[:36])
            if kind != 5 or not meets(*bb):
                continue
            nparts, npts = struct.unpack('<2i', rec[36:44])
            starts = struct.unpack(f'<{nparts}i', rec[44:44 + 4 * nparts]) + (npts,)
            xy = struct.unpack(f'<{2 * npts}d', rec[44 + 4 * nparts:44 + 4 * nparts + 16 * npts])
            rings = [[[xy[2 * i], xy[2 * i + 1]] for i in range(a, b)] for a, b in zip(starts, starts[1:])]
            # a shapefile's outer rings run clockwise, holes counter-clockwise; each outer takes the holes after it
            polys = []
            for r in rings:
                cw = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:])) < 0
                if cw or not polys:
                    polys.append([r])
                else:
                    polys[-1].append(r)
            yield from polys


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
    sea inside full: the coast. Vertices on full's edges or on a whole degree (where the polygons are split)
    are cut lines, not coast."""
    def cut(p):
        return any(abs(p[0] - v) < 1e-9 for v in (full[0], full[2], round(p[0]))) or \
            any(abs(p[1] - v) < 1e-9 for v in (full[1], full[3], round(p[1])))
    land = [p for poly in polys for r in poly for p in r if not cut(p)]
    w, s, e, n = clubs_box
    if land:
        w, s = min(w, min(p[0] for p in land)), min(s, min(p[1] for p in land))
        e, n = max(e, max(p[0] for p in land)), max(n, max(p[1] for p in land))
    kx, ky = k((s + n) / 2)
    return [max(full[0], w - OUT / kx), max(full[1], s - OUT / ky), min(full[2], e + OUT / kx), min(full[3], n + OUT / ky)]


def main():
    zpath, gen_path = sys.argv[1], sys.argv[2]
    clubs = []
    for line in open(gen_path + '.none', encoding='utf-8'):
        cc, latlng, oid, name = line.rstrip('\n').split('\t')
        lat, lng = map(float, latlng.split(','))
        clubs.append({'cc': cc, 'p': [lng, lat], 'name': name})
    near = [box([c['p']], ALONG + OUT) for c in clubs]
    sea = list(pieces(zpath, near))
    # a bbox test first: every piece is up to a degree across, with thousands of points
    bbs = [(min(p[0] for p in poly[0]), min(p[1] for p in poly[0]), max(p[0] for p in poly[0]), max(p[1] for p in poly[0]))
           for poly in sea]
    on = []
    for c in clubs:
        b = box([c['p']], COAST)
        polys = [poly for poly, bb in zip(sea, bbs) if bb[0] <= b[2] and bb[2] >= b[0] and bb[1] <= b[3] and bb[3] >= b[1]]
        if polys and poly_dist(c['p'], polys) <= COAST:
            on.append(c)
    slugs = {line.split('|')[0] for line in open(gen_path, encoding='utf-8') if line.strip()}
    lines = []
    os.makedirs('work/sea', exist_ok=True)
    for g in clusters([c['p'] for c in on]):
        cs = [on[i] for i in g]
        ps = [c['p'] for c in cs]
        full = box(ps, ALONG)
        polys = clip_polys(sea, full)
        b = [round(v, 3) for v in strip(polys, box(ps, 0), full)]
        polys = clip_polys(polys, b)
        if not polys:
            continue
        title = 'Sea near ' + (cs[0]['name'] or 'rowing club')
        slug, i = f"{cs[0]['cc']}_sea_{slugify(cs[0]['name'])}", 2
        while slug in slugs:
            slug, i = f"{cs[0]['cc']}_sea_{slugify(cs[0]['name'])}_{i}", i + 1
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
    print('ok')
elif __name__ == '__main__':
    main()
