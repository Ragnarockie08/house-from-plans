"""Roof geometry from plan["roof"] (pure Python, cm).

Each wing is a rectangle with a ridge along x or y and two slopes at the wing's pitch. Its eave
line is the long edge of the rectangle (overhangs included), at "eave_z"; or give "ridge_z" and
the eave height follows. Where wings overlap the roof surface is the higher one, so valleys and
cross gables come out by themselves.

Every slope is a plane z = a*x + b*y + c over a half of its wing. roof_facets() splits the slopes
into convex pieces where each plane is the top one, so the mesh is exactly planar per facet.
"""
import math


class Roof:
    def __init__(self, roof):
        self.r = roof
        self.thickness = roof["thickness"]
        self.planes = []          # (wing id, a, b, c, convex domain polygon, pitch)
        self.wings = []
        for w in roof["wings"]:
            pitch = w.get("pitch_deg", roof["pitch_deg"])
            t = math.tan(math.radians(pitch))
            x0, y0, x1, y1 = w["x0"], w["y0"], w["x1"], w["y1"]
            half = ((y1 - y0) if w["ridge_axis"] == "x" else (x1 - x0)) / 2
            eave = w["eave_z"] if "eave_z" in w else w["ridge_z"] - half * t
            self.wings.append(dict(w, eave=eave, tan=t, pitch=pitch,
                                   v_thick=self.thickness / math.cos(math.radians(pitch))))
            if w["ridge_axis"] == "x":
                ym = (y0 + y1) / 2
                self.planes.append((w["id"], 0, t, eave - y0 * t, rect(x0, y0, x1, ym), pitch))
                self.planes.append((w["id"], 0, -t, eave + y1 * t, rect(x0, ym, x1, y1), pitch))
            elif w["ridge_axis"] == "y":
                xm = (x0 + x1) / 2
                self.planes.append((w["id"], t, 0, eave - x0 * t, rect(x0, y0, xm, y1), pitch))
                self.planes.append((w["id"], -t, 0, eave + x1 * t, rect(xm, y0, x1, y1), pitch))
            else:
                raise SystemExit(f"roof wing {w['id']}: ridge_axis must be 'x' or 'y'")
        pitches = {w["pitch"] for w in self.wings}
        if len(pitches) > 1:
            raise SystemExit("roof wings with different pitches are not supported (vertical thickness differs)")
        self.v_thick = self.wings[0]["v_thick"]

    def top(self, x, y):
        """Roof surface height at (x, y), None outside every wing."""
        zs = [a * x + b * y + c for _, a, b, c, dom, _ in self.planes if inside(dom, x, y)]
        return max(zs) if zs else None

    def under(self, x, y):
        z = self.top(x, y)
        return None if z is None else z - self.v_thick

    def facets(self):
        """[(plane, [convex polygon, ...])]: where each slope plane is the top surface."""
        out = []
        for i, pi in enumerate(self.planes):
            pieces = [pi[4]]
            for j, pj in enumerate(self.planes):
                if i == j:
                    continue
                da, db, dc = pj[1] - pi[1], pj[2] - pi[2], pj[3] - pi[3]
                if abs(da) < 1e-9 and abs(db) < 1e-9:
                    if abs(dc) < 1e-6:
                        if j > i:
                            continue   # same plane: the earlier one keeps the overlap
                    elif dc < 0:
                        continue       # j is lower everywhere
                    cutter = [rect_halfplanes(pj[4])]
                else:
                    # j is higher where da*x + db*y + dc > 0
                    cutter = [rect_halfplanes(pj[4]) + [(da, db, dc)]]
                pieces = [q for p in pieces for c in cutter for q in subtract(p, c)]
            pieces = [p for p in pieces if area(p) > 1.0]
            if pieces:
                out.append((pi, pieces))
        return out


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def inside(poly, x, y, eps=1e-6):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return min(xs) - eps <= x <= max(xs) + eps and min(ys) - eps <= y <= max(ys) + eps


def rect_halfplanes(poly):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    # a*x + b*y + c >= 0 inside
    return [(1, 0, -x0), (-1, 0, x1), (0, 1, -y0), (0, -1, y1)]


def clip(poly, a, b, c):
    """Keep the part of a convex polygon where a*x + b*y + c >= 0."""
    out = []
    n = len(poly)
    for k in range(n):
        p, q = poly[k], poly[(k + 1) % n]
        fp, fq = a * p[0] + b * p[1] + c, a * q[0] + b * q[1] + c
        if fp >= 0:
            out.append(p)
        if (fp >= 0) != (fq >= 0):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out if len(out) >= 3 else []


def subtract(poly, halfplanes):
    """Convex polygon minus a convex region (intersection of half-planes) -> convex pieces."""
    pieces = []
    rest = poly
    for a, b, c in halfplanes:
        outside = clip(rest, -a, -b, -c)
        if outside and area(outside) > 1e-6:
            pieces.append(outside)
        rest = clip(rest, a, b, c)
        if not rest:
            break
    return pieces


def area(poly):
    s = 0.0
    for k in range(len(poly)):
        x0, y0 = poly[k]; x1, y1 = poly[(k + 1) % len(poly)]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2


def ccw(poly):
    s = sum(poly[k][0] * poly[(k + 1) % len(poly)][1] - poly[(k + 1) % len(poly)][0] * poly[k][1]
            for k in range(len(poly)))
    return poly if s > 0 else list(reversed(poly))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from plan import load_plan
    house = sys.argv[1] if len(sys.argv) > 1 else "examples/simple-house"
    R = Roof(load_plan(house, sys.argv[2] if len(sys.argv) > 2 else "A")["roof"])
    for pl, pieces in R.facets():
        print(f"{pl[0]:<14} a={pl[1]:+.3f} b={pl[2]:+.3f}  {len(pieces)} piece(s), {sum(map(area, pieces)) / 1e4:7.2f} m2 plan")
