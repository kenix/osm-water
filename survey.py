"""The waters rowing clubs are on, found from OSM: every sport=rowing object, the natural=water polygon
within 500 m of it, then one file per lake and one per stretch of river around a group of clubs.
Usage: python3 -I survey.py <hand waters.txt> <out waters.txt> <cc>:<clubs>:<water>:<rivers> ... (osmium geojsonseq
files: sport=rowing, natural=water polygons, waterway=river,canal lines for the stretches' names; ids are osmium's
type_id, a<n> for an area as lake.sh exports it too)
A river stretch's selector also names, by id, the polygons its clubs sit on that a named river runs
through but that lack water=river. Writes the generated lines in the WATERS format of waters.sh (slug|selector|bbox||src|title|core) and
prints what it found. The hand-made waters win: a club on one of them gets nothing generated."""
import json, math, re, sys, unicodedata

NEAR = 500           # metres from a club to its water
POND = 50_000        # m²: a lake smaller than this is no rowing water
LINK = 15_000        # m: river clubs closer than this share a stretch
SPAN = 50_000        # m: a stretch, or a lake cut into stretches, at most this across
MARGIN = 10_000      # m of river around a stretch's clubs
CORE = 2_000         # m around the clubs where this stretch wins over a neighbour's
LAKE_MAX = 60_000    # m: a lake wider than this is cut into stretches like a river
RIVER = {'river', 'canal', 'oxbow', 'harbour'}  # a river's harbour basin is its water (Düsseldorf)
NOT_WATER = {'stream', 'ditch', 'drain', 'wastewater', 'fish_pass', 'reflecting_pool', 'lock', 'moat', 'pond'}
CELL = 0.01


def records(path):
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.lstrip('\x1e').strip()
            if line:
                yield json.loads(line)


def rings_of(g):
    if not g:
        return []
    return [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates'] if g['type'] == 'MultiPolygon' else []


def centre(g):
    t, c = g['type'], g['coordinates']
    if t == 'Point':
        return c
    pts = c if t == 'LineString' else c[0] if t in ('Polygon', 'MultiLineString') else c[0][0]
    return [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]


def k(lat):
    return 111_320 * math.cos(math.radians(lat)), 110_540


def dist_m(a, b):  # [lng, lat]
    kx, ky = k((a[1] + b[1]) / 2)
    return math.hypot((a[0] - b[0]) * kx, (a[1] - b[1]) * ky)


def seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = 0 if dx == dy == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def inside(p, ring):
    x, y, c = p[0], p[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def to_m(ring, lat):
    kx, ky = k(lat)
    return [(x * kx, y * ky) for x, y in ring]


def poly_dist(pt, polys):
    """Metres from pt ([lng, lat]) to the water: 0 on it."""
    kx, ky = k(pt[1])
    q = (pt[0] * kx, pt[1] * ky)
    best = math.inf
    for poly in polys:
        rings = [to_m(r, pt[1]) for r in poly]
        if inside(q, rings[0]) and not any(inside(q, h) for h in rings[1:]):
            return 0
        for r in rings:
            for a, b in zip(r, r[1:]):
                best = min(best, seg(q, a, b))
    return best


def area_m2(polys):
    total = 0
    for poly in polys:
        lat = poly[0][0][1]
        for i, r in enumerate(to_m(r, lat) for r in poly):
            a = abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:]))) / 2
            total += a if i == 0 else -a
    return total


def slugify(s):
    s = s.lower()
    for a, b in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss')):
        s = s.replace(a, b)
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '_', s).strip('_') or 'water'


def box(points, margin):
    """[w, s, e, n] around [lng, lat] points, margin in metres."""
    lat = sum(p[1] for p in points) / len(points)
    kx, ky = k(lat)
    w, e = min(p[0] for p in points), max(p[0] for p in points)
    s, n = min(p[1] for p in points), max(p[1] for p in points)
    return [round(w - margin / kx, 3), round(s - margin / ky, 3), round(e + margin / kx, 3), round(n + margin / ky, 3)]


def span_m(points):
    w, s, e, n = box(points, 0)
    return max(dist_m([w, s], [e, s]), dist_m([w, s], [w, n]))


def clusters(points):
    """Single linkage within LINK, then halved along the longer side until no cluster spans more than SPAN."""
    left, out = list(range(len(points))), []
    while left:
        group, todo = [], [left.pop()]
        while todo:
            i = todo.pop()
            group.append(i)
            near = [j for j in left if dist_m(points[i], points[j]) < LINK]
            for j in near:
                left.remove(j)
            todo += near
        out.append(group)
    done = []
    while out:
        g = out.pop()
        ps = [points[i] for i in g]
        if len(g) < 2 or span_m(ps) <= SPAN:
            done.append(g)
            continue
        w, s, e, n = box(ps, 0)
        axis = 0 if dist_m([w, s], [e, s]) >= dist_m([w, s], [w, n]) else 1
        g.sort(key=lambda i: points[i][axis])
        out += [g[:len(g) // 2], g[len(g) // 2:]]
    return done


def main():
    hand, out_path, inputs = sys.argv[1], sys.argv[2], sys.argv[3:]
    hands = []  # (name or selector, bbox)
    for line in open(hand, encoding='utf-8'):
        parts = line.rstrip('\n').split('|')
        if len(parts) >= 3:
            hands.append((parts[1], [float(v) for v in parts[2].split(',')]))

    clubs = []  # dict: cc, name, p
    waters = {}  # osm id -> dict: name, kind, polys
    lines_ = []  # named river lines: (name, points)
    for spec in inputs:
        cc, clubs_path, water_path, river_path = spec.split(':')
        for f in records(river_path):
            g, name = f.get('geometry'), f['properties'].get('name')
            if name and g and g['type'] == 'LineString':
                lines_.append((name, g['coordinates']))
        river_names = {name for name, _ in lines_}
        for f in records(clubs_path):
            if f.get('geometry'):
                t = f['properties']
                clubs.append({'cc': cc, 'id': f.get('id'), 'name': t.get('name') or '', 'p': centre(f['geometry'])})
        cells = {}
        for i, c in enumerate(clubs):
            if c['cc'] == cc:
                cells.setdefault((math.floor(c['p'][1] / CELL), math.floor(c['p'][0] / CELL)), []).append(i)
        for f in records(water_path):
            polys = rings_of(f.get('geometry'))
            if not polys:
                continue
            t = f['properties']
            if t.get('water') in NOT_WATER:
                continue
            xs = [p[0] for poly in polys for p in poly[0]]
            ys = [p[1] for poly in polys for p in poly[0]]
            pad = 0.006
            hit = any((a, b) in cells
                      for a in range(math.floor((min(ys) - pad) / CELL), math.floor((max(ys) + pad) / CELL) + 1)
                      for b in range(math.floor((min(xs) - pad * 1.5) / CELL), math.floor((max(xs) + pad * 1.5) / CELL) + 1))
            if not hit:
                continue
            # a river's polygon without water=river still carries the river's name (River Trent)
            kind = 'river' if (t.get('water') in RIVER or t.get('waterway') == 'riverbank'
                               or t.get('name') in river_names) else 'lake'
            if kind == 'lake' and area_m2(polys) < POND:
                continue
            waters[f['id']] = {'id': f['id'], 'name': t.get('name') or '', 'kind': kind, 'polys': polys,
                               'harbour': t.get('water') == 'harbour',
                               'bbox': [min(xs), min(ys), max(xs), max(ys)], 'cc': cc}

    # every club to the largest water within NEAR, so a harbour basin or a pond by the shore does not take
    # it from the lake (a bbox test first: thousands of polygons)
    for w in waters.values():
        w['area'] = area_m2(w['polys'])
    for c in clubs:
        near = []
        for w in waters.values():
            x0, y0, x1, y1 = w['bbox']
            if x0 - 0.01 <= c['p'][0] <= x1 + 0.01 and y0 - 0.006 <= c['p'][1] <= y1 + 0.006:
                if poly_dist(c['p'], w['polys']) <= NEAR:
                    near.append(w)
        c['water'] = max(near, key=lambda w: w['area']) if near else None
        c['near'] = near
        w = c['water']
        if w and w['kind'] == 'lake' and not w['name'] and 'crossed' not in w:
            # an unnamed polygon a named river runs through is that river, mapped without water=river
            x0, y0, x1, y1 = w['bbox']
            w['crossed'] = any(poly_dist(a, w['polys']) == 0 for _, pts in lines_ for a in pts[::3]
                               if x0 <= a[0] <= x1 and y0 <= a[1] <= y1)
            if w['crossed']:
                w['kind'], w['untagged'] = 'river', True

    def by_hand(c):
        for sel, (x0, y0, x1, y1) in hands:
            if not (x0 <= c['p'][0] <= x1 and y0 <= c['p'][1] <= y1):
                continue
            # a river stretch by hand takes its river's clubs, a lake by hand those near that lake
            if c['water']['kind'] == 'river' if '=' in sel else any(w['name'] == sel for w in c['near']):
                return True
        return False

    def river_name(ps):
        best = (math.inf, 'river')
        for name, pts in lines_:
            for p in ps:
                for a in pts[::5]:
                    if abs(a[1] - p[1]) < 0.03 and abs(a[0] - p[0]) < 0.05:
                        best = min(best, (dist_m(a, p), name))
        return best[1]

    on = [c for c in clubs if c['water']]
    gen = [c for c in on if not by_hand(c)]
    lines, slugs = [], set()

    def add(cc, name, selector, bbox, title, core):
        slug, n = f'{cc}_{slugify(name)}', 2
        while slug in slugs:
            slug, n = f'{cc}_{slugify(name)}_{n}', n + 1
        slugs.add(slug)
        lines.append('|'.join([slug, selector, ','.join(map(str, bbox)), '', '', title, ','.join(map(str, core))]))

    lakes = {}
    for c in gen:
        if c['water']['kind'] == 'lake':
            lakes.setdefault(c['water']['id'], []).append(c)
    for wid, cs in sorted(lakes.items(), key=lambda kv: kv[1][0]['water']['name']):
        w = cs[0]['water']
        corners = [w['bbox'][:2], w['bbox'][2:]]
        # unnamed and no river through it (that made it a stretch): a regatta course, a dock; a club's name
        name = w['name'] or (cs[0]['name'] or 'Rowing') + ' water'
        if span_m(corners) <= LAKE_MAX:
            b = box(corners, 300)
            add(cs[0]['cc'], name, f'@id={wid}', b, name, b)
        else:
            for g in clusters([c['p'] for c in cs]):
                ps = [cs[i]['p'] for i in g]
                add(cs[g[0]]['cc'], name, f'@id={wid}', box(ps, MARGIN), name, box(ps, CORE))

    rivers = [c for c in gen if c['water']['kind'] == 'river']
    for g in clusters([c['p'] for c in rivers]):
        cs = [rivers[i] for i in g]
        if all(c['water']['harbour'] for c in cs):
            continue  # harbours alone are the sea's (Kiel); a sea club waits for the coast
        names = [c['water']['name'] for c in cs if c['water']['name']]
        ps = [c['p'] for c in cs]
        name = max(set(names), key=names.count) if names else river_name(ps)
        # ponytail: only the untagged polygons clubs sit on join; others along the stretch stay out
        extra = sorted({c['water']['id'] for c in cs if c['water'].get('untagged')})
        sel = 'water=river,canal,oxbow,harbour' + (';@id=' + ','.join(extra) if extra else '')
        add(cs[0]['cc'], name, sel, box(ps, MARGIN), name, box(ps, CORE))

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sorted(lines)) + '\n')
    per = {}
    for c in clubs:
        s = per.setdefault(c['cc'], {'sites': 0, 'on water': 0, 'hand': 0, 'none': 0})
        s['sites'] += 1
        s['on water' if c['water'] else 'none'] += 1
        s['hand'] += bool(c['water'] and by_hand(c))
    print(json.dumps(per))
    print(len(lines), 'waters:', sum('@id=' in l for l in lines), 'lakes,', sum('water=' in l for l in lines), 'river stretches')
    with open(out_path + '.none', 'w', encoding='utf-8') as f:
        for c in clubs:
            if not c['water']:
                f.write(f"{c['cc']}\t{c['p'][1]:.5f},{c['p'][0]:.5f}\t{c['id']}\t{c['name']}\n")


if __name__ == '__main__':
    main()
