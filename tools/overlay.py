"""Draw <house>/plan.json over the scanned floor plan: walls red, openings and shafts blue.

Usage:
  .venv/bin/python tools/overlay.py <house> OUT.jpg                     whole building
  .venv/bin/python tools/overlay.py <house> OUT.jpg x0 y0 x1 y1 [zoom]  region in cm, 10 cm grid
"""
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent))
from scanlib import Scan  # noqa: E402

RED, BLUE, GRID = (0, 0, 230), (220, 90, 0), (0, 160, 0)


def draw(house, region=None, zoom=1.0):
    sc = Scan(house)
    plan = json.loads((Path(house) / "plan.json").read_text())
    im = cv2.cvtColor(sc.load(), cv2.COLOR_GRAY2BGR)
    ov = im.copy()

    def r(e):
        p0, p1 = sc.to_px(e["x0"], e["y0"]), sc.to_px(e["x1"], e["y1"])
        return tuple(map(int, p0)), tuple(map(int, p1))

    for w in plan["walls"]:
        cv2.rectangle(ov, *r(w), RED, -1)
    for s in plan["openings"] + plan.get("shafts", []):
        cv2.rectangle(ov, *r(s), BLUE, -1)
    im = cv2.addWeighted(im, 0.55, ov, 0.45, 0)
    for w in plan["walls"]:
        cv2.rectangle(im, *r(w), RED, 1)
    if region is None:
        xs = [w[k] for w in plan["walls"] for k in ("x0", "x1")]
        ys = [w[k] for w in plan["walls"] for k in ("y0", "y1")]
        x0, y0, x1, y1 = min(xs) - 60, min(ys) - 60, max(xs) + 60, max(ys) + 60
    else:
        x0, y0, x1, y1 = region
    (px0, py1), (px1, py0) = sc.to_px(x0, y0), sc.to_px(x1, y1)
    H, W = im.shape[:2]
    crop = im[max(0, int(py0)):min(H, int(py1)), max(0, int(px0)):min(W, int(px1))]
    crop = cv2.resize(crop, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_CUBIC)
    if region is not None:
        for xc in range(int(x0 // 10) * 10, int(x1) + 1, 10):
            X = int((sc.to_px(xc, 0)[0] - max(0, int(px0))) * zoom)
            cv2.line(crop, (X, 0), (X, 14 if xc % 50 == 0 else 6), GRID, 1)
            if xc % 50 == 0:
                cv2.putText(crop, str(xc), (X + 2, 26), 0, 0.4, GRID, 1)
        for yc in range(int(y0 // 10) * 10, int(y1) + 1, 10):
            Y = int((sc.to_px(0, yc)[1] - max(0, int(py0))) * zoom)
            cv2.line(crop, (0, Y), (14 if yc % 50 == 0 else 6, Y), GRID, 1)
            if yc % 50 == 0:
                cv2.putText(crop, str(yc), (16, Y + 4), 0, 0.4, GRID, 1)
    return crop


if __name__ == "__main__":
    house, out = sys.argv[1], sys.argv[2]
    region = tuple(float(v) for v in sys.argv[3:7]) if len(sys.argv) >= 7 else None
    zoom = float(sys.argv[7]) if len(sys.argv) >= 8 else (2.0 if region else 1.0)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(out, draw(house, region, zoom))
    print("wrote", out)
