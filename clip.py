"""River water area for one stretch: the natural=water polygons matching a selector, clipped to a bbox.
Usage: python3 -I clip.py <water.geojson> <key=v1,v2[;key=v1,...]> <w,s,e,n> <out.geojson>
A polygon matching any of the ;-separated selectors is taken. The key @id selects by OSM id (w123, r456:
osmium export -u type_id), for one lake among others or a river's polygon that lacks water=river.
Every output feature is named 'water', so measure.py and build.py take it as the lake."""
import json, sys

src, bbox = json.load(open(sys.argv[1])), [float(v) for v in sys.argv[3].split(',')]
sels = [(k, set(v.split(','))) for k, v in (s.split('=') for s in sys.argv[2].split(';'))]


def clip(ring):
    """Sutherland-Hodgman against the bbox; a concave ring may gain zero-width edges along the border, which fill hides."""
    w, s, e, n = bbox
    for i, v, sign in ((0, w, 1), (0, e, -1), (1, s, 1), (1, n, -1)):  # axis, edge value, which side is inside
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


out = []
for f in src['features']:
    g = f['geometry']
    if not g or not any((f.get('id') if k == '@id' else f['properties'].get(k)) in vs for k, vs in sels): continue
    for poly in [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates'] if g['type'] == 'MultiPolygon' else []:
        rings = [clip(r[:-1]) for r in poly]
        if rings[0]:
            out.append({'type': 'Feature', 'properties': {'name': 'water'},
                        'geometry': {'type': 'Polygon', 'coordinates': [r for r in rings if r]}})
json.dump({'type': 'FeatureCollection', 'features': out}, open(sys.argv[4], 'w'))
print('water polygons:', len(out))

if __name__ == '__main__' and len(sys.argv) > 5:  # self-check: python3 -I clip.py x x=y 0,0,1,1 /dev/null test
    bbox = [0, 0, 1, 1]
    r = clip([[-1, 0.5], [2, 0.5], [2, 0.6], [-1, 0.6]])
    assert sorted(map(tuple, r[:-1])) == [(0, 0.5), (0, 0.6), (1, 0.5), (1, 0.6)] and r[0] == r[-1], r
    assert clip([[2, 2], [3, 2], [3, 3]]) == []
    print('ok')
