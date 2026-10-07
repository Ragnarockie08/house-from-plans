"""Load a house's plan.json and apply a variant (pure Python, used by the checks and by Blender).

A variant lives in plan["variants"][name] and edits the base plan list by list:
  <list>_remove: [id, ...]         drop entries by id
  <list>_change: {id: {key: v}}    update fields of an entry ("src" is kept as a note)
  <list>_add:    [entry, ...]      append entries
  replace:       {key: value}      replace a top-level key outright (levels, totals, ...)
<list> is any top-level list of objects with an "id": walls, openings, rooms, shafts, voids,
slab_holes, attic_walls, rails. A changed or added room without "table_m2" is reported, not checked.
"""
import copy
import json
from pathlib import Path


def load_plan(house, variant="A"):
    p = json.loads((Path(house) / "plan.json").read_text())
    return apply_variant(p, variant)


def apply_variant(p, variant):
    if variant == "A":
        return p
    vs = p.get("variants", {})
    if variant not in vs:
        raise SystemExit(f"plan.json has no variant {variant!r} (known: A, {', '.join(vs) or 'none'})")
    p = copy.deepcopy(p)
    v = vs[variant]
    for key, value in v.get("replace", {}).items():
        p[key] = value
    lists = {k[: -len(s)] for k in v for s in ("_remove", "_change", "_add") if k.endswith(s)}
    for name in sorted(lists):
        items = p.get(name, [])
        items = [e for e in items if e["id"] not in v.get(name + "_remove", [])]
        for e in items:
            ch = v.get(name + "_change", {}).get(e["id"])
            if ch:
                e.update({k: x for k, x in ch.items() if k != "src"})
                e["changed_in"] = variant
                if name == "rooms" and "table_m2" not in ch:
                    e.pop("table_m2", None)
        known = {e["id"] for e in items}
        for e in v.get(name + "_add", []):
            if e["id"] in known:
                raise SystemExit(f"variant {variant}: {name} id {e['id']!r} added twice")
            items.append(dict(e, changed_in=variant))
        p[name] = items
    p["variant"] = variant
    return p
