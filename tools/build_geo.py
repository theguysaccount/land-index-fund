"""Build data/geo/counties.json and data/geo/states.json from the Census Bureau's cartographic boundary files.

    python3 tools/build_geo.py cb_2021_us_county_20m.zip cb_2021_us_state_20m.zip

Source: https://www2.census.gov/geo/tiger/GENZ2021/shp/ (public domain). The 2021 vintage is used on purpose:
it still has Connecticut's eight counties, which is how USDA and FHFA report. Run by hand when county
boundaries change; the output is committed, so builds never need the Census site.

Output coordinates are an Albers USA composite projection (Alaska and Hawaii as insets) on a 975 x 610 canvas,
stored as integers in tenths of a unit: each ring is [x0, y0, dx1, dy1, dx2, dy2, ...].
"""
import json
import math
import os
import struct
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "geo")
K, TX, TY = 1300.0, 487.5, 305.0
SKIP_STATES = {"60", "66", "69", "72", "78"}  # territories: not in the USDA county series used here


def _conic(phi0, phi1):
    sy0 = math.sin(phi0)
    n = (sy0 + math.sin(phi1)) / 2
    c = 1 + sy0 * (2 * n - sy0)
    r0 = math.sqrt(c) / n

    def project(lam, phi):
        r = math.sqrt(max(0.0, c - 2 * n * math.sin(phi))) / n
        return r * math.sin(lam * n), r0 - r * math.cos(lam * n)
    return project


def _proj(parallels, rotate, center, scale, tx, ty):
    p = _conic(math.radians(parallels[0]), math.radians(parallels[1]))
    cx, cy = p(math.radians(center[0]), math.radians(center[1]))

    def f(lon, lat):
        lam = lon + rotate
        while lam > 180:
            lam -= 360
        while lam < -180:
            lam += 360
        x, y = p(math.radians(lam), math.radians(lat))
        return tx + scale * (x - cx), ty - scale * (y - cy)
    return f


LOWER48 = _proj((29.5, 45.5), 96, (-0.6, 38.7), K, TX, TY)
ALASKA = _proj((55, 65), 154, (-2, 58.5), 0.35 * K, TX - 0.307 * K, TY + 0.201 * K)
HAWAII = _proj((8, 18), 157, (-3, 19.9), K, TX - 0.205 * K, TY + 0.212 * K)


def project(statefp, lon, lat):
    f = ALASKA if statefp == "02" else HAWAII if statefp == "15" else LOWER48
    return f(lon, lat)


def read_shapefile(path):
    """Yield (attributes, rings) for each polygon record; rings are lists of (lon, lat)."""
    z = zipfile.ZipFile(path)
    base = [n for n in z.namelist() if n.endswith(".shp")][0][:-4]
    shp, dbf = z.read(base + ".shp"), z.read(base + ".dbf")
    nrec, hlen, rlen = struct.unpack("<IHH", dbf[4:12])
    fields, off = [], 32
    while dbf[off] != 0x0D:
        fields.append((dbf[off:off + 11].split(b"\0")[0].decode(), dbf[off + 16]))
        off += 32
    recs, pos = [], hlen
    for _ in range(nrec):
        rec, o, d = dbf[pos:pos + rlen], 1, {}
        pos += rlen
        for name, flen in fields:
            d[name] = rec[o:o + flen].decode("utf-8", "replace").strip()
            o += flen
        recs.append(d)
    pos, i = 100, 0
    while pos < len(shp):
        _, clen = struct.unpack(">II", shp[pos:pos + 8])
        pos += 8
        stype = struct.unpack("<I", shp[pos:pos + 4])[0]
        rings = []
        if stype == 5:
            nparts, npts = struct.unpack("<II", shp[pos + 36:pos + 44])
            parts = list(struct.unpack("<%dI" % nparts, shp[pos + 44:pos + 44 + 4 * nparts])) + [npts]
            base_off = pos + 44 + 4 * nparts
            pts = struct.unpack("<%dd" % (2 * npts), shp[base_off:base_off + 16 * npts])
            for a, b in zip(parts, parts[1:]):
                rings.append([(pts[2 * j], pts[2 * j + 1]) for j in range(a, b)])
        yield recs[i], rings
        pos += clen * 2
        i += 1


def quantize(statefp, ring):
    out, last = [], None
    for lon, lat in ring:
        x, y = project(statefp, lon, lat)
        q = (int(round(x * 10)), int(round(y * 10)))
        if q != last:
            out.append(q)
            last = q
    return out


def delta(points):
    flat = [points[0][0], points[0][1]]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        flat += [x1 - x0, y1 - y0]
    return flat


def ring_area(points):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))) / 2.0


def main(county_zip, state_zip):
    os.makedirs(OUT, exist_ok=True)
    counties, vertex_owner = [], {}
    for rec, rings in read_shapefile(county_zip):
        sf = rec["STATEFP"]
        if sf in SKIP_STATES:
            continue
        fips = rec["GEOID"]
        paths, biggest, centre = [], 0.0, None
        for ring in rings:
            for lon, lat in ring:
                vertex_owner.setdefault((round(lon, 6), round(lat, 6)), set()).add(fips)
            q = quantize(sf, ring)
            if len(q) < 4:
                continue
            paths.append(delta(q))
            area = ring_area(q)
            if area > biggest:
                biggest = area
                centre = [int(round(sum(p[0] for p in q[:-1]) / (len(q) - 1))),
                          int(round(sum(p[1] for p in q[:-1]) / (len(q) - 1)))]
        if not paths:
            continue
        counties.append({"f": fips, "n": rec["NAMELSAD"], "s": rec["STUSPS"], "sn": rec["STATE_NAME"],
                         "a": int(round(int(rec["ALAND"]) / 2589988.11)), "c": centre, "p": paths})
    shared = {}
    for owners in vertex_owner.values():
        if len(owners) > 1:
            for a in owners:
                for b in owners:
                    if a != b:
                        shared.setdefault((a, b), 0)
                        shared[(a, b)] += 1
    for c in counties:
        c["nb"] = sorted(b for (a, b), n in shared.items() if a == c["f"] and n >= 2)
    counties.sort(key=lambda c: c["f"])
    states = []
    for rec, rings in read_shapefile(state_zip):
        sf = rec["STATEFP"]
        if sf in SKIP_STATES:
            continue
        paths = [delta(q) for q in (quantize(sf, r) for r in rings) if len(q) >= 4]
        states.append({"f": sf, "s": rec["STUSPS"], "n": rec["NAME"], "p": paths})
    states.sort(key=lambda s: s["f"])
    meta = {"source": "US Census Bureau cartographic boundary files, 2021, 1:20,000,000 (public domain)",
            "url": "https://www2.census.gov/geo/tiger/GENZ2021/shp/", "width": 975, "height": 610, "scale": 10}
    with open(os.path.join(OUT, "counties.json"), "w") as fh:
        json.dump({"meta": meta, "counties": counties}, fh, separators=(",", ":"))
    with open(os.path.join(OUT, "states.json"), "w") as fh:
        json.dump({"meta": meta, "states": states}, fh, separators=(",", ":"))
    pts = sum(len(p) // 2 for c in counties for p in c["p"])
    print("counties %d, points %d, states %d" % (len(counties), pts, len(states)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
