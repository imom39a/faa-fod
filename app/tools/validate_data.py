"""Validate app/data against app/CONTRACT.md section 1 and spec/test-data-plan.md.

Usage: .venv/bin/python -I validate_data.py <data_dir>
Checks every scene.json (6 Angle keys, files exist, sizes match, boxes inside the image, categories
valid, severity consistent with the rules matrix, WIDE regions), the scoring-set quotas, the spike
exclusion, demo/timeline.json and the size budget. Prints a summary table; exit code 1 on any error.
"""
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ANGLES = ["NOSE", "ENG-L", "ENG-R", "CARGO", "AFT", "WIDE"]
REASONS = {"missing", "glare", "blur", "blocked", "low_light"}
SPIKE_TITLES = {  # the 6 photos behind the 22-frame spike set (prototypes/spike/data/raw/commons_meta.json)
    "Airport Brussels 1.jpg", "Pelita Air Airbus A320 PK-PWF Jakarta 2025 (01).jpg",
    "Pelita Air Airbus A320 PK-PWL Jakarta 2025 (01).jpg",
    "Spring Airlines Airbus A320 B-6708 at Shanghai Pudong June 2025.jpg", "Tansonnhat9.jpg",
    "Wingo Boeing 737-700 sitting at the gate at Cali Airport.jpg",
}
NAMED = ["fasteners_hardware", "aircraft_parts", "tools", "luggage_parts", "catering_flightline",
         "cargo_packaging", "pavement_construction", "natural"]
BUDGET_MB = 400

errors, warnings = [], []


def err(where, msg):
    errors.append(f"{where}: {msg}")


def inside(poly, x, y):
    n, c = len(poly), False
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def img_size(p):
    with Image.open(p) as im:
        return im.size, im.format


def check_scene(sdir: Path, rules):
    sid = sdir.name
    try:
        sc = json.loads((sdir / "scene.json").read_text())
    except Exception as e:  # noqa: BLE001
        err(sid, f"scene.json unreadable: {e}")
        return None
    if sc.get("scene_id") != sid:
        err(sid, "scene_id does not match its directory")
    if sc.get("kind") not in ("pre_arrival", "pre_departure"):
        err(sid, f"bad kind {sc.get('kind')!r}")
    if sc.get("light") not in ("day", "night", "wet"):
        err(sid, f"bad light {sc.get('light')!r}")
    if not isinstance(sc.get("description"), str) or not sc["description"].strip() or "\n" in sc["description"]:
        err(sid, "description must be one non-empty line")
    angles = sc.get("angles") or {}
    if sorted(angles) != sorted(ANGLES):
        err(sid, f"angles keys are {sorted(angles)}, expected all 6")
    for ang, a in angles.items():
        w = f"{sid}/{ang}"
        need = {"image", "reference", "after", "width", "height", "derived", "source", "usable", "unusable_reason", "regions", "ground_truth", "observations_truth"}
        if set(a) != need:
            err(w, f"keys differ from contract: missing {sorted(need - set(a))}, extra {sorted(set(a) - need)}")
            continue
        W, H = a["width"], a["height"]
        if not (isinstance(W, int) and isinstance(H, int) and 0 < W <= 3840 and 0 < H <= 2160):
            err(w, f"bad size {W}x{H}")
        if a["derived"] not in ("native", "crop", "mirror"):
            err(w, f"bad derived {a['derived']!r}")
        s = a["source"] or {}
        for k in ("title", "url", "author", "licence"):
            if not s.get(k):
                err(w, f"source.{k} missing")
        if s.get("title") in SPIKE_TITLES:
            a["_spike"] = True
        # usability
        if a["usable"]:
            if a["unusable_reason"] is not None:
                err(w, "usable Angle has an unusable_reason")
        else:
            if a["unusable_reason"] not in REASONS:
                err(w, f"bad unusable_reason {a['unusable_reason']!r}")
            if a["ground_truth"]:
                err(w, "unusable Angle has ground truth")
        if (a["unusable_reason"] == "missing") != (a["image"] is None):
            err(w, "image must be null exactly when unusable_reason is 'missing'")
        # files
        for key, expect in (("image", f"{ang}.jpg"), ("reference", f"ref/{ang}.jpg"), ("after", f"after/{ang}.jpg")):
            rel = a[key]
            if rel is None:
                continue
            if rel != expect:
                err(w, f"{key} is {rel!r}, expected {expect!r}")
            p = sdir / rel
            if not p.is_file():
                err(w, f"{key} file missing: {rel}")
                continue
            try:
                size, fmt = img_size(p)
            except Exception as e:  # noqa: BLE001
                err(w, f"{key} not a readable image: {e}")
                continue
            if fmt != "JPEG":
                err(w, f"{key} is {fmt}, not JPEG")
            if size != (W, H):
                err(w, f"{key} is {size[0]}x{size[1]}, scene.json says {W}x{H}")
        if W * 9 != H * 16:
            warnings.append(f"{w}: {W}x{H} is not 16:9")
        # regions
        rg = a["regions"]
        if ang == "WIDE":
            if not rg or set(rg) != {"envelope", "erl"}:
                err(w, "WIDE needs regions.envelope and regions.erl")
                rg = None
            else:
                for name, poly in rg.items():
                    if not (isinstance(poly, list) and len(poly) >= 3 and all(len(p) == 2 and 0 <= p[0] <= W and 0 <= p[1] <= H for p in poly)):
                        err(w, f"regions.{name} is not a polygon inside the image")
                        rg = None
                        break
        elif rg is not None:
            err(w, "regions must be null except on WIDE")
        # ground truth
        for i, g in enumerate(a["ground_truth"]):
            wi = f"{w}/gt[{i}]"
            if set(g) != {"bbox", "finding_type", "category", "object_class", "zone_tier", "expected_severity", "label"}:
                err(wi, f"keys differ from contract: {sorted(g)}")
                continue
            b = g["bbox"]
            if not (len(b) == 4 and all(isinstance(v, int) for v in b) and 0 <= b[0] < b[2] <= W and 0 <= b[1] < b[3] <= H):
                err(wi, f"bbox {b} not inside {W}x{H}")
                continue
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            if g["finding_type"] == "equipment_staging":
                if g["category"] is not None:
                    err(wi, "equipment_staging must have category null")
                if g["expected_severity"] != rules["rules"][[r["id"] for r in rules["rules"]].index("FOD-R9")]["severity"]:
                    err(wi, "equipment_staging severity must be REMOVE (FOD-R9)")
                if sc["kind"] != "pre_arrival":
                    err(wi, "equipment_staging only applies at pre-arrival")
                if ang != "WIDE":
                    err(wi, "equipment_staging ground truth belongs on WIDE (where the ERL polygon is)")
                elif rg and not inside(rg["erl"], cx, b[3] - (b[3] - b[1]) * 0.15):
                    err(wi, "GSE box base is not inside the erl polygon")
            elif g["finding_type"] == "fod":
                if g["category"] not in rules["categories"]:
                    err(wi, f"unknown category {g['category']!r}")
                if g["object_class"] not in rules["severity_matrix"]:
                    err(wi, f"unknown object_class {g['object_class']!r}")
                    continue
                tier = rules["angle_zone_tier"][ang]
                if ang == "WIDE" and rg:
                    tier = "general" if inside(rg["envelope"], cx, cy) else "outside_boundary"
                if g["zone_tier"] != tier:
                    err(wi, f"zone_tier {g['zone_tier']!r} but the box is in {tier!r}")
                exp = rules["severity_matrix"][g["object_class"]].get(g["zone_tier"])
                if g["expected_severity"] != exp:
                    err(wi, f"expected_severity {g['expected_severity']!r}, matrix says {exp!r}")
            else:
                err(wi, f"bad finding_type {g['finding_type']!r}")
            if not g["label"]:
                err(wi, "label missing")
        for i, o in enumerate(a["observations_truth"]):
            b = o.get("bbox") or []
            if not (len(b) == 4 and 0 <= b[0] < b[2] <= W and 0 <= b[1] < b[3] <= H and o.get("kind")):
                err(f"{w}/obs[{i}]", "bad observation")
    return sc


def classify(sc):
    gts = [g for a in sc["angles"].values() for g in a["ground_truth"]]
    if any(g["finding_type"] == "equipment_staging" for g in gts):
        return "gse_in_erl"
    if any(not a["usable"] for a in sc["angles"].values()):
        return "unusable_angle"
    return "debris" if gts else "clean"


def main():
    data = Path(sys.argv[1])
    rules = json.loads((data / "rules/fod-rules.json").read_text())
    scenes = {}
    for sdir in sorted((data / "scenes").iterdir()):
        if sdir.is_dir():
            sc = check_scene(sdir, rules)
            if sc:
                scenes[sdir.name] = sc
    # ---- scoring set
    try:
        test = json.loads((data / "testset.json").read_text())["scenes"]
    except Exception as e:  # noqa: BLE001
        err("testset.json", str(e)); test = []
    for sid in test:
        if sid not in scenes:
            err("testset.json", f"unknown scene {sid}")
    T = [scenes[s] for s in test if s in scenes]
    if len(test) != 30 or len(set(test)) != 30:
        err("quota", f"scoring set has {len(set(test))} scenes, plan says 30")
    kinds = Counter((sc["kind"], classify(sc)) for sc in T)
    plan = {("pre_arrival", "clean"): 5, ("pre_arrival", "debris"): 3, ("pre_arrival", "gse_in_erl"): 2,
            ("pre_departure", "clean"): 8, ("pre_departure", "debris"): 10, ("pre_departure", "unusable_angle"): 2}
    for k in sorted(set(plan) | set(kinds)):
        if kinds.get(k, 0) != plan.get(k, 0):
            err("quota", f"{k[0]} / {k[1]}: {kinds.get(k, 0)} scenes, plan says {plan.get(k, 0)}")
    light = Counter(sc["light"] for sc in T)
    nw = light["night"] + light["wet"]
    if T and nw / len(T) < 0.20:
        err("quota", f"night or wet: {nw}/{len(T)} is under 20%")
    items, per_scene = [], {}
    for sc in T:
        n = 0
        for ang, a in sc["angles"].items():
            for g in a["ground_truth"]:
                if g["finding_type"] == "fod":
                    b = g["bbox"]
                    items.append({"scene": sc["scene_id"], "angle": ang, "long": max(b[2] - b[0], b[3] - b[1]), "derived": a["derived"], **g})
                    n += 1
        if classify(sc) == "debris":
            per_scene[sc["scene_id"]] = n
            if not 1 <= n <= 4:
                err("quota", f"{sc['scene_id']}: {n} debris items, plan says 1 to 4")
        if classify(sc) in ("clean", "unusable_angle") and n:
            err("quota", f"{sc['scene_id']}: classified {classify(sc)} but has debris")
        for ang, a in sc["angles"].items():
            if a.get("_spike"):
                err("spike", f"{sc['scene_id']}/{ang} uses a photo from the 22-frame spike set: {a['source']['title']}")
    cats = Counter(i["category"] for i in items)
    for c in NAMED:
        if not cats.get(c):
            err("quota", f"category {c} has no debris item in the scoring set")
    crit = sum(i["zone_tier"] == "critical" for i in items)
    small = sum(i["long"] < 30 for i in items)
    if items and crit / len(items) < 0.5:
        err("quota", f"critical-zone debris {crit}/{len(items)} is under half")
    if items and small / len(items) < 0.25:
        err("quota", f"debris under 30 px: {small}/{len(items)} is under a quarter")
    controls = Counter()
    for sid in test:
        bp = data / "scenes" / sid / "build.json"
        if bp.exists():
            c = json.loads(bp.read_text()).get("control")
            if c:
                controls[c] += 1
    for c in ("noop", "clutter"):
        if not controls.get(c):
            err("quota", f"no '{c}' control scene in the scoring set")
    # ---- demo timeline
    moments = {}
    try:
        tl = json.loads((data / "demo/timeline.json").read_text())
        if tl.get("gates") != ["T1", "T2", "T4", "T5", "T8"]:
            err("timeline", f"gates are {tl.get('gates')}")
        tids = [t["turn_id"] for t in tl["turns"]]
        if len(tids) != len(set(tids)):
            err("timeline", "duplicate turn_id")
        clean_turn = False
        for t in tl["turns"]:
            w = f"timeline/{t.get('turn_id')}"
            if t.get("gate") not in tl["gates"]:
                err(w, f"unknown gate {t.get('gate')}")
            for k in ("turn_id", "gate", "flight", "aircraft_type", "events"):
                if not t.get(k):
                    err(w, f"{k} missing")
            ts = [e["t"] for e in t["events"]]
            if ts != sorted(ts):
                err(w, "events are not in time order")
            classes = []
            for e in t["events"]:
                if e["type"] not in ("stand_prep", "inspection", "block_in", "scheduled_pushback"):
                    err(w, f"unknown event type {e['type']}")
                if e["type"] != "inspection":
                    continue
                sc = scenes.get(e.get("scene_id"))
                if not sc:
                    err(w, f"unknown scene {e.get('scene_id')}")
                    continue
                if sc["kind"] != e.get("kind"):
                    err(w, f"{e['scene_id']} is {sc['kind']}, event says {e.get('kind')}")
                classes.append(classify(sc))
                for ang, a in sc["angles"].items():
                    for g in a["ground_truth"]:
                        b = g["bbox"]
                        if g["expected_severity"] == "HOLD":
                            ok_after = bool(a["after"])
                            if not ok_after:
                                err(w, f"{e['scene_id']}/{ang}: HOLD demo Finding without a clean `after` frame")
                            moments.setdefault("hold_clears_on_reinspect", e["scene_id"])
                            if ang in ("ENG-L", "ENG-R") and g["category"] == "fasteners_hardware" and max(b[2] - b[0], b[3] - b[1]) < 40:
                                moments["small_bolt_in_engine_zone"] = e["scene_id"]
                        if g["finding_type"] == "equipment_staging" and sc["kind"] == "pre_arrival":
                            moments["gse_inside_erl"] = e["scene_id"]
                        if g["zone_tier"] == "outside_boundary" and ang == "WIDE":
                            moments["outside_envelope_wide_only"] = e["scene_id"]
                    if ang in ("ENG-L", "ENG-R") and a["unusable_reason"] == "glare":
                        moments["glare_on_engine_angle"] = e["scene_id"]
            if len(classes) >= 2 and all(c == "clean" for c in classes):
                clean_turn = True
        for m in ("small_bolt_in_engine_zone", "gse_inside_erl", "glare_on_engine_angle", "hold_clears_on_reinspect", "outside_envelope_wide_only"):
            if m not in moments:
                err("timeline", f"demo moment not staged: {m}")
        if not clean_turn:
            err("timeline", "no fully clean Turn")
        dur = max(e["t"] for t in tl["turns"] for e in t["events"])
        if not 300 <= dur <= 420:
            err("timeline", f"run length {dur}s at 1x is not about 6 minutes")
        missing_gates = set(tl["gates"]) - {t["gate"] for t in tl["turns"]}
        if missing_gates:
            err("timeline", f"gates with no Turn: {sorted(missing_gates)}")
    except FileNotFoundError:
        err("timeline", "demo/timeline.json missing"); tl = {"turns": []}; dur = 0
    for f in ("ATTRIBUTION.md",):
        if not (data / f).is_file():
            err(f, "missing")
        else:
            txt = (data / f).read_text()
            for sc in scenes.values():
                for a in sc["angles"].values():
                    if a["source"].get("title") and a["source"]["title"] not in txt:
                        err(f, f"source not listed: {a['source']['title']}")
    size_mb = sum(p.stat().st_size for p in data.rglob("*") if p.is_file()) / 1e6
    if size_mb > BUDGET_MB:
        err("size", f"app/data is {size_mb:.0f} MB, budget is about {BUDGET_MB} MB")
    # ---- summary
    def table(title, rows):
        print(f"\n{title}")
        wd = max(len(str(r[0])) for r in rows) + 2
        for r in rows:
            print("  " + str(r[0]).ljust(wd) + "  ".join(str(v) for v in r[1:]))

    ang_all = [a for sc in T for a in sc["angles"].values()]
    table("Scoring set (testset.json)", [
        ("Inspections", len(T), f"({len(scenes)} scenes on disk, {len(scenes) - len(T)} demo-only)"),
        *[(f"{k[0]} / {k[1]}", kinds[k], f"(plan {plan.get(k, 0)})") for k in sorted(set(plan) | set(kinds))],
        ("light", ", ".join(f"{k} {v}" for k, v in sorted(light.items())), f"(night or wet {nw}/{len(T)} = {100 * nw / max(1, len(T)):.0f}%)"),
        ("Angle images", sum(a["image"] is not None for a in ang_all), f"of {len(ang_all)} Angles"),
        ("derived", ", ".join(f"{k} {v}" for k, v in sorted(Counter(a["derived"] for a in ang_all).items()))),
        ("full 3840x2160", sum(a["width"] == 3840 for a in ang_all), f"smallest {min((a['width'], a['height']) for a in ang_all) if ang_all else '-'}"),
        ("unusable Angles", ", ".join(f"{k} {v}" for k, v in Counter(a["unusable_reason"] for a in ang_all if not a["usable"]).items()) or 0),
        ("no reference", sum(a["reference"] is None for a in ang_all)),
        ("controls", ", ".join(f"{k} {v}" for k, v in sorted(controls.items())) or 0),
    ])
    if items:
        table("Debris items in the scoring set", [
            ("items", len(items), f"in {len(per_scene)} Inspections ({min(per_scene.values())} to {max(per_scene.values())} each)"),
            *[(c, cats.get(c, 0)) for c in NAMED + ["unidentified"] if c in NAMED or cats.get(c)],
            ("zone tier", ", ".join(f"{k} {v}" for k, v in sorted(Counter(i["zone_tier"] for i in items).items())), f"(critical {100 * crit / len(items):.0f}%)"),
            ("object class", ", ".join(f"{k} {v}" for k, v in sorted(Counter(i["object_class"] for i in items).items()))),
            ("severity", ", ".join(f"{k} {v}" for k, v in sorted(Counter(i["expected_severity"] for i in items).items()))),
            ("under 30 px", small, f"({100 * small / len(items):.0f}%; long edge min {min(i['long'] for i in items)}, max {max(i['long'] for i in items)} px)"),
            ("on derived Angles", ", ".join(f"{k} {v}" for k, v in sorted(Counter(i["derived"] for i in items).items()))),
        ])
    table("Demo timeline", [
        ("turns", len(tl["turns"]), f"run length {dur}s at 1x"),
        *[(k, v) for k, v in sorted(moments.items())],
    ])
    table("Totals", [("app/data size", f"{size_mb:.0f} MB", f"(budget ~{BUDGET_MB} MB)"), ("warnings", len(warnings)), ("errors", len(errors))])
    for wmsg in warnings:
        print("WARN ", wmsg)
    for e in errors:
        print("ERROR", e)
    print("\nRESULT:", "FAIL" if errors else "PASS")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
