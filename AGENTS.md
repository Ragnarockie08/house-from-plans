# Instructions for coding agents

You are building a measured 3D model of a real house from its permit drawings. Read
`README.md` first (inputs, pipeline, lessons). This file is the rules and the data format.

## Rules
1. **Every dimension lives in `<house>/plan.json` with a `src`** naming the sheet and the
   dimension chain or label it came from. `blender/build_model.py` only reads that file.
   Never type a house number into a script.
2. **Never invent a dimension.** A value that is not on the drawings or stated by the owner is a
   question for the owner. Scaling off a sketch is a last resort: say so in `src` and mark it ±5 cm.
3. **Numbers come from dimension chains and labels, not from pixels.** The scan only places walls.
4. **Stop at the two gates** (README, pipeline) and wait for the owner.
5. **Never overwrite an output.** Every build gets a new `<house>/out/<version>/` (v1, v2, ...).
6. **Report check results as printed**, with the failing lines. Do not adjust plan.json just to
   make a check pass; a failing room is a transcription error or a drawing inconsistency, and
   either way the owner hears about it.
7. Keep `<house>/BUILD_LOG.md`: per version what changed, check results, findings, open questions.
8. Commit after each step with a short message. Sources (`<house>/sources/`) are never committed.
9. Code, file names and docs in English.
10. Privacy: the owner's drawings, address, plot number, names and the catalog design name never
    go anywhere public. Strip GPS metadata from photos.

## Folder of one house
```
house/
  plan.json        dimensions (this file is the model)
  shots.json       review cameras
  sources/         drawings: scans or PDFs rendered to images (not committed)
  out/<version>/   model_<variant>.blend, geometry_reference_<variant>.json, stills_<variant>/
  BUILD_LOG.md
```
Start a new house by copying `examples/simple-house/plan.json` and `shots.json`, then replace
every entry. PDF sheets to images: `pdftoppm -r 300 -png sheet.pdf sources/sheet`.

## plan.json reference
Units: cm. Frame: x east (drawing right), y north (drawing up), z = 0 at finished ground floor
(±0.00). Origin at the outer south-west corner of the walls. Rectangles are `x0 < x1`, `y0 < y1`.

| Key | Content |
|---|---|
| `meta.scan`, `meta.calibration` | path of the ground floor scan in the house folder; `px_x0`, `px_y0` = pixel of plan (0, 0); `px_per_cm_x`, `px_per_cm_y` (from `tools/calibrate.py`) |
| `meta.plaster_cm` | finish thickness per face subtracted before comparing room areas (find it on 3 to 4 rooms first) |
| `meta.area_tolerance` | optional, default 0.01 (1 %) |
| `meta.envelope_exclude` | optional rects left out of the envelope check (wall fins, frames) |
| `wall_types` | `ext`, `lb`, `part` with `thickness` and `layers` |
| `walls[]` | `id`, `type`, `x0 y0 x1 y1`. Walls run straight through their openings; the build cuts the openings out |
| `openings[]` | `id`, `kind` (`window`/`door`), `exterior`, rect across the full wall thickness, `w`, `h`, `sill`. Sloped tops: `"shape": "to_roof", "below_roof": cm` (glazing up to the roof slope) or `"shape": "line", "top_line": [[along, z], [along, z]]` |
| `rooms[]` | `id`, `name`, `table_m2` (from the room table), `rects` (structural interior). Optional `group` (rooms the table splits without a wall are checked as a sum), `minus` (shaft ids) |
| `totals` | `usable_m2`, `footprint_m2`, `envelope_cm` [x, y] from the building data |
| `expected` | numbers printed on the drawings for the model check: `ridge_z`, `height_above_ground`, `pitch_deg`, optional `stack_top_z` |
| `levels` | `ground_outside`, `floor`, `ceiling`, `wall_plate` (each `{"z": cm, "src": ...}`) |
| `inner_rects` | room side of the exterior walls, as rects (L-shaped house = 2 rects); the slabs fill these |
| `slab` | ceiling slab `z0`, `z1` |
| `voids[]`, `slab_holes[]` | rects where the ceiling slab is missing (rooms open to the roof, stair holes) |
| `attic_walls[]` | rects of walls standing on the slab up to the roof (e.g. along a void edge) |
| `rails[]` | optional railings: `a`, `b` (cm), `h`, optional `z` |
| `shafts[]` | vent or chimney shafts, floor to slab top |
| `roof` | `pitch_deg`, `thickness` (perpendicular), `wings[]`, `stacks[]` |
| `roof.wings[]` | rect of one roof body including overhangs, `ridge_axis` `x` or `y`, and `ridge_z` or `eave_z` (height at the rect's eave edges). Overlapping wings: the higher surface wins, so valleys and cross gables need no extra data |
| `variants.<name>` | owner changes on top of the permit: `<list>_remove`, `<list>_change`, `<list>_add` for any list above, `replace` for top-level keys (see `tools/plan.py`) |

## Commands
```sh
make setup
make check   HOUSE=house [VARIANT=B]
make overlay HOUSE=house
make build   HOUSE=house V=v1 [VARIANT=B]
make render  HOUSE=house V=v2 [FAST=1]
.venv/bin/python tools/overlay.py house out.jpg x0 y0 x1 y1 3     # zoomed region with a 10 cm grid
.venv/bin/python tools/roof.py house                               # roof facets per slope
```
Set `BLENDER=` if Blender is not at the macOS default path.
