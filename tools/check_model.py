"""Check the built model (out/<version>/geometry_reference_<variant>.json) against plan.json
"expected" (numbers written on the drawings: ridge, height above ground, pitch) and "totals".

Run after blender/build_model.py:  .venv/bin/python tools/check_model.py <house> <version> [variant]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from plan import load_plan  # noqa: E402

house, version = sys.argv[1], sys.argv[2]
variant = sys.argv[3] if len(sys.argv) > 3 else "A"
plan = load_plan(house, variant)
g = json.loads((Path(house) / "out" / version / f"geometry_reference_{variant}.json").read_text())
e, t = plan.get("expected", {}), plan.get("totals", {})
TOL = 0.01   # 1 cm
checks = []
if "ridge_z" in e:
    checks.append(("ridge", g["ridge_z_m"], e["ridge_z"] / 100))
if "height_above_ground" in e:
    checks.append(("height above ground", g["max_height_above_ground_m"], e["height_above_ground"] / 100))
if "stack_top_z" in e:
    checks.append(("stack top", g["stack_top_m"], e["stack_top_z"] / 100))
if "envelope_cm" in t:
    checks.append(("walls x size", g["envelope_m"]["x"], t["envelope_cm"][0] / 100))
    checks.append(("walls y size", g["envelope_m"]["y"], t["envelope_cm"][1] / 100))
fails = 0
for label, got, want in checks:
    ok = abs(got - want) <= TOL
    fails += not ok
    print(f'{"ok  " if ok else "FAIL"} {label:<22} {got:8.3f} m   drawing {want:8.3f} m')
if "pitch_deg" in e:
    ok = bool(g["roof_pitches_deg"]) and all(abs(p - e["pitch_deg"]) < 0.01 for p in g["roof_pitches_deg"])
    fails += not ok
    print(f'{"ok  " if ok else "FAIL"} {"roof pitch":<22} {g["roof_pitches_deg"]}   drawing {e["pitch_deg"]}')
if not checks:
    print('plan.json has no "expected" block; nothing to compare')
print("\nall checks pass" if not fails else f"\n{fails} check(s) failed")
sys.exit(1 if fails else 0)
