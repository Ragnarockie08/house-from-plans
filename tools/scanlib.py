"""Scan <-> plan coordinates, from plan.json meta.calibration.

The scan only places walls. Numbers come from dimension chains and labels: scans are often
stretched unevenly (several cm across a sheet), so never measure a dimension off the pixels.
"""
import json
from pathlib import Path

import cv2


class Scan:
    def __init__(self, house):
        self.house = Path(house)
        meta = json.loads((self.house / "plan.json").read_text())["meta"]
        self.path = self.house / meta["scan"]
        c = meta["calibration"]
        self.px_x0, self.py0 = c["px_x0"], c["px_y0"]          # pixel of plan (0, 0)
        self.kx, self.ky = c["px_per_cm_x"], c["px_per_cm_y"]

    def load(self, gray=True):
        im = cv2.imread(str(self.path), cv2.IMREAD_GRAYSCALE if gray else cv2.IMREAD_COLOR)
        if im is None:
            raise SystemExit(f"cannot read the scan {self.path}")
        return im

    def to_cm(self, px, py):
        return (px - self.px_x0) / self.kx, (self.py0 - py) / self.ky

    def to_px(self, x, y):
        return self.px_x0 + x * self.kx, self.py0 - y * self.ky
