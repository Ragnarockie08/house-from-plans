"""Scan calibration from two overall dimension chains.

Find, on the scan, the pixel positions of both ends of one long horizontal chain and one long
vertical chain (open the image and read the tick marks, or let the agent find them), then:

  .venv/bin/python tools/calibrate.py --x PX_LEFT PX_RIGHT CM --y PY_BOTTOM PY_TOP CM \
      --origin PX PY

--origin is the pixel of plan point (0, 0), usually the outer SW corner. Prints the
"calibration" block for plan.json meta. Check it with tools/overlay.py afterwards.
"""
import argparse
import json

ap = argparse.ArgumentParser()
ap.add_argument("--x", nargs=3, type=float, required=True, metavar=("PX_LEFT", "PX_RIGHT", "CM"))
ap.add_argument("--y", nargs=3, type=float, required=True, metavar=("PY_BOTTOM", "PY_TOP", "CM"))
ap.add_argument("--origin", nargs=2, type=float, required=True, metavar=("PX", "PY"))
a = ap.parse_args()
kx = abs(a.x[1] - a.x[0]) / a.x[2]
ky = abs(a.y[0] - a.y[1]) / a.y[2]
print(json.dumps({"px_x0": a.origin[0], "px_y0": a.origin[1], "px_per_cm_x": round(kx, 4),
                  "px_per_cm_y": round(ky, 4),
                  "src": f"chains {a.x[2]:g} (x) and {a.y[2]:g} (y)"}, indent=1))
if abs(kx - ky) / kx > 0.01:
    print(f"note: x and y scales differ by {100 * abs(kx - ky) / kx:.1f} %; the scan is stretched")
