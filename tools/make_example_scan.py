"""Draw a fake "scanned" ground floor plan for the fictional example house, so the overlay check
has something to run on. Real projects use the architect's sheet instead.

  .venv/bin/python tools/make_example_scan.py examples/simple-house
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from scanlib import Scan  # noqa: E402

house = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/simple-house")
plan = json.loads((house / "plan.json").read_text())
sc = Scan(house)
W = int(sc.px_x0 * 2 + 1200 * sc.kx)
H = int(sc.py0 + 300)
im = np.full((H, W), 250, np.uint8)
INK, EPS, FONT = 20, 150, cv2.FONT_HERSHEY_SIMPLEX


def P(x, y):
    px, py = sc.to_px(x, y)
    return int(round(px)), int(round(py))


ext_eps = 20
for w in plan["walls"]:
    cv2.rectangle(im, P(w["x0"], w["y0"]), P(w["x1"], w["y1"]), INK, -1)
    if w["type"] == "ext":       # insulation layer drawn lighter on the outside face
        x0, y0, x1, y1 = w["x0"], w["y0"], w["x1"], w["y1"]
        if y0 == 0: cv2.rectangle(im, P(x0, 0), P(x1, ext_eps), EPS, -1)
        if y1 == 900: cv2.rectangle(im, P(x0, 900 - ext_eps), P(x1, 900), EPS, -1)
        if x0 == 0: cv2.rectangle(im, P(0, y0), P(ext_eps, y1), EPS, -1)
        if x1 == 1200: cv2.rectangle(im, P(1200 - ext_eps, y0), P(1200, y1), EPS, -1)
for o in plan["openings"]:
    p0, p1 = P(o["x0"], o["y0"]), P(o["x1"], o["y1"])
    cv2.rectangle(im, p0, p1, 250, -1)
    cv2.rectangle(im, p0, p1, INK, 1)
    along_x = (o["x1"] - o["x0"]) >= (o["y1"] - o["y0"])
    if o["kind"] == "window":
        if along_x:
            ym = (o["y0"] + o["y1"]) / 2
            cv2.line(im, P(o["x0"], ym - 4), P(o["x1"], ym - 4), INK, 1)
            cv2.line(im, P(o["x0"], ym + 4), P(o["x1"], ym + 4), INK, 1)
        else:
            xm = (o["x0"] + o["x1"]) / 2
            cv2.line(im, P(xm - 4, o["y0"]), P(xm - 4, o["y1"]), INK, 1)
            cv2.line(im, P(xm + 4, o["y0"]), P(xm + 4, o["y1"]), INK, 1)
    label = f'{o["w"]}/{o["h"]}' if o.get("h") else f'{o["w"]}'
    tx, ty = P((o["x0"] + o["x1"]) / 2, (o["y0"] + o["y1"]) / 2)
    cv2.putText(im, label, (tx - 22, ty - 12 if along_x else ty), FONT, 0.38, INK, 1, cv2.LINE_AA)

for r in plan["rooms"]:
    x0, y0, x1, y1 = r["rects"][0]
    cx, cy = P((x0 + x1) / 2, (y0 + y1) / 2)
    for k, t in enumerate((r["id"], r["name"], f'{r["table_m2"]:.2f} m2')):
        cv2.putText(im, t, (cx - 45, cy - 14 + 18 * k), FONT, 0.45, INK, 1, cv2.LINE_AA)


def chain_x(y_cm, marks):
    py = P(0, y_cm)[1]
    cv2.line(im, (P(marks[0], 0)[0], py), (P(marks[-1], 0)[0], py), INK, 1)
    for m in marks:
        px = P(m, 0)[0]
        cv2.line(im, (px - 5, py + 5), (px + 5, py - 5), INK, 1)
    for a, b in zip(marks, marks[1:]):
        cv2.putText(im, f"{b - a:g}", (P((a + b) / 2, 0)[0] - 12, py - 6), FONT, 0.4, INK, 1, cv2.LINE_AA)


def chain_y(x_cm, marks):
    px = P(x_cm, 0)[0]
    cv2.line(im, (px, P(0, marks[0])[1]), (px, P(0, marks[-1])[1]), INK, 1)
    for m in marks:
        py = P(0, m)[1]
        cv2.line(im, (px - 5, py + 5), (px + 5, py - 5), INK, 1)
    for a, b in zip(marks, marks[1:]):
        cv2.putText(im, f"{b - a:g}", (px - 48, P(0, (a + b) / 2)[1] + 4), FONT, 0.4, INK, 1, cv2.LINE_AA)


chain_x(-150, [0, 1200])
chain_x(-110, [0, 44, 700, 724, 844, 856, 1156, 1200])
chain_x(-70, [0, 150, 550, 734, 834, 930, 1080, 1200])
chain_y(-150, [0, 900])
chain_y(-90, [0, 44, 250, 650, 856, 900])
chain_y(1290, [0, 44, 400, 412, 600, 612, 856, 900])
cv2.putText(im, "P-1 GROUND FLOOR 1:100  (fictional example house)", (40, 60), FONT, 0.9, INK, 2, cv2.LINE_AA)
nx, ny = W - 120, 120
cv2.arrowedLine(im, (nx, ny + 50), (nx, ny - 30), INK, 2, tipLength=0.3)
cv2.putText(im, "N", (nx - 9, ny + 80), FONT, 0.8, INK, 2, cv2.LINE_AA)

# a little scanner noise and blur
rng = np.random.default_rng(7)
im = cv2.GaussianBlur(im, (3, 3), 0)
im = np.clip(im.astype(np.int16) + rng.normal(0, 6, im.shape).astype(np.int16), 0, 255).astype(np.uint8)
out = house / plan["meta"]["scan"]
out.parent.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(out), im, [cv2.IMWRITE_JPEG_QUALITY, 85])
print("wrote", out, im.shape)
