"""Check <house>/plan.json against the drawings' own numbers: room areas from the room table,
total usable area, footprint, envelope, plus wall overlaps and openings outside walls.

Run: .venv/bin/python tools/check_plan.py <house> [variant]   (exit code 1 if any check fails)
"""
import sys
from pathlib import Path

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).parent))
from plan import load_plan  # noqa: E402

house = sys.argv[1] if len(sys.argv) > 1 else "house"
variant = sys.argv[2] if len(sys.argv) > 2 else "A"
plan = load_plan(house, variant)
tol = plan["meta"].get("area_tolerance", 0.01)      # 1 % per room and on totals
plaster = plan["meta"].get("plaster_cm", 0)
shafts = {s["id"]: box(s["x0"], s["y0"], s["x1"], s["y1"]) for s in plan.get("shafts", [])}
fails = []
print(f"house {house}, variant {variant}")


def line(ok, label, got, want, unit):
    if not ok:
        fails.append(label)
    print(f'{"ok  " if ok else "FAIL"} {label:<30} {got:9.2f} {unit}   table {want:9.2f} {unit}   {100 * (got - want) / want:+6.2f} %')


print(f"Rooms (structural interior minus {plaster} cm plaster per face)")
total, groups = 0.0, {}
for r in plan["rooms"]:
    poly = unary_union([box(*rc) for rc in r["rects"]])
    for s in r.get("minus", []):
        poly = poly.difference(shafts[s])
    m2 = poly.buffer(-plaster, join_style="mitre").area / 1e4 if plaster else poly.area / 1e4
    total += m2
    label = f'{r["id"]} {r["name"]}'
    if "group" in r:            # rooms the table splits without a wall: checked as a sum
        g = groups.setdefault(r["group"], [0.0, 0.0]); g[0] += m2; g[1] += r.get("table_m2", 0)
        print(f"info {label:<30} {m2:9.2f} m2   (checked as group {r['group']})")
    elif "table_m2" not in r:
        print(f"info {label:<30} {m2:9.2f} m2   ({'changed in variant ' + variant if r.get('changed_in') else 'no table value'})")
    else:
        line(abs(m2 - r["table_m2"]) <= tol * r["table_m2"], label, m2, r["table_m2"], "m2")
for name, (got, want) in groups.items():
    line(abs(got - want) <= tol * want, f"group {name}", got, want, "m2")

t = plan.get("totals", {})
changed = any(r.get("changed_in") for r in plan["rooms"])
if "usable_m2" in t and not changed:
    line(abs(total - t["usable_m2"]) <= tol * t["usable_m2"], "total usable", total, t["usable_m2"], "m2")
else:
    print(f'info {"total usable":<30} {total:9.2f} m2')

walls = unary_union([box(w["x0"], w["y0"], w["x1"], w["y1"]) for w in plan["walls"]])
inside = unary_union([box(*rc) for r in plan["rooms"] for rc in r["rects"]])
gaps = [box(o["x0"], o["y0"], o["x1"], o["y1"]) for o in plan["openings"] if o["exterior"]]
gaps += [box(c["x0"], c["y0"], c["x1"], c["y1"]) for c in plan.get("covered", [])]
shell = unary_union([walls, inside] + gaps)
shell = unary_union([Polygon(g.exterior) for g in getattr(shell, "geoms", [shell])])   # holes filled
if "footprint_m2" in t:
    line(abs(shell.area / 1e4 - t["footprint_m2"]) <= tol * t["footprint_m2"], "footprint", shell.area / 1e4, t["footprint_m2"], "m2")
if "envelope_cm" in t:
    body = shell.difference(unary_union([box(*e) for e in plan["meta"].get("envelope_exclude", [])] or [Polygon()]))
    minx, miny, maxx, maxy = body.bounds
    for label, got, want in (("envelope x", maxx - minx, t["envelope_cm"][0]), ("envelope y", maxy - miny, t["envelope_cm"][1])):
        ok = abs(got - want) <= 1
        if not ok:
            fails.append(label)
        print(f'{"ok  " if ok else "FAIL"} {label:<30} {got:9.1f} cm   table {want:9.1f} cm')

# typos in plan.json show up here
ws = plan["walls"]
for i in range(len(ws)):
    a = box(ws[i]["x0"], ws[i]["y0"], ws[i]["x1"], ws[i]["y1"])
    if a.area <= 0:
        fails.append(ws[i]["id"]); print(f'FAIL wall {ws[i]["id"]} has no area (x0 >= x1 or y0 >= y1)')
    for j in range(i + 1, len(ws)):
        b = box(ws[j]["x0"], ws[j]["y0"], ws[j]["x1"], ws[j]["y1"])
        if a.intersection(b).area > 0:
            print(f'warn overlap {ws[i]["id"]} / {ws[j]["id"]}: {a.intersection(b).area:.0f} cm2')
for o in plan["openings"]:
    ob = box(o["x0"], o["y0"], o["x1"], o["y1"])
    if not any(box(w["x0"], w["y0"], w["x1"], w["y1"]).buffer(0.5).contains(ob) for w in ws):
        print(f'warn opening {o["id"]} is not inside a single wall')
    if o.get("w") and abs(max(o["x1"] - o["x0"], o["y1"] - o["y0"]) - o["w"]) > 1:
        print(f'warn opening {o["id"]}: rect length differs from w = {o["w"]}')
for r in plan["rooms"]:
    hit = unary_union([box(*rc) for rc in r["rects"]]).intersection(walls).area
    if hit > 1:
        print(f'warn room {r["id"]} overlaps walls by {hit:.0f} cm2')

print(f"\n{len(fails)} check(s) failed: {', '.join(fails)}" if fails else "\nall checks pass")
sys.exit(1 if fails else 0)
