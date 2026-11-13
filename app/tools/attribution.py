"""Write app/data/ATTRIBUTION.md from the built scenes (scene.json + build.json) and the manifests."""
import json
from collections import defaultdict
from pathlib import Path


def write(data: Path, man: Path):
    lock = json.loads((man / "sources.lock.json").read_text())
    objects = json.loads((man / "objects.json").read_text())
    uses = defaultdict(lambda: defaultdict(list))   # source key -> (derived) -> ["pd-001 NOSE", ...]
    obj_uses = defaultdict(list)
    test = set(json.loads((data / "testset.json").read_text())["scenes"])
    for sdir in sorted((data / "scenes").iterdir()):
        if not (sdir / "scene.json").exists():
            continue
        sc = json.loads((sdir / "scene.json").read_text())
        bd = json.loads((sdir / "build.json").read_text())
        for ang, a in sc["angles"].items():
            b = bd["angles"][ang]
            uses[b["source_key"]][a["derived"]].append((sc["scene_id"], ang))
            for o in b["objects"]:
                obj_uses[o].append((sc["scene_id"], ang))

    def fmt(pairs):
        by = defaultdict(list)
        for sid, ang in pairs:
            by[sid].append(ang)
        return "; ".join(f"`{sid}` {', '.join(angs)}" for sid, angs in sorted(by.items()))

    L = ["# Image attribution (PoC test data)", "",
         "Every Angle frame under `scenes/` is cut from a real, openly licensed photograph on Wikimedia Commons. "
         "The frames are modified by this project: cropped to 16:9 and resized, some mirrored left-to-right (ENG-L stand-ins), "
         "some with debris or a GSE vehicle composited in, some with a synthetic glare, blur or low-light degradation. "
         "Reference frames (`ref/`) and after frames (`after/`) are the same crops with simulated camera and lighting drift. "
         "Frames derived from CC BY-SA photographs are shared under the same licence as their source. "
         "A licence covers copyright only: identifiable people and airline liveries carry rights it does not cover, "
         "and nothing here implies endorsement by any airline, airport or photographer.", "",
         "Built by `app/tools/build_scenes.py` from `app/tools/manifest/` (`sources.lock.json` holds the download URL and sha256 of every file). "
         "Per-scene detail (source crop box in source pixels, edits, objects) is in each scene's `build.json`. "
         f"Scenes in the scoring set (`testset.json`): {len(test)}; other scenes are demo-only.", "",
         "## Source photographs", "",
         "| Photo | Author | Licence | Original size | Used as a plain crop (derived = crop or native) | Used mirrored (derived = mirror) |", "|---|---|---|---|---|---|"]
    for k in sorted(uses, key=lambda k: lock[k]["title"]):
        r = lock[k]
        lic = f"[{r['licence']}]({r['licence_url']})" if r.get("licence_url") else r["licence"]
        plain = uses[k].get("crop", []) + uses[k].get("native", [])
        nat = uses[k].get("native", [])
        L.append(f"| [{r['title']}]({r['url']}) | {r['author']} | {lic} | {r['width']}×{r['height']} | "
                 f"{fmt(plain) or '—'}{' (native, 16:9 trim only: ' + fmt(nat) + ')' if nat else ''} | {fmt(uses[k].get('mirror', [])) or '—'} |")
    L += ["", "## Composited debris", "",
          "Debris is cut out of the sources below and pasted at known positions with a feathered mask, brightness matched to the local pavement, and a soft contact shadow. "
          "Ground-truth boxes are in each `scene.json`.", "",
          "FOD-A objects come from the example images of the FOD-A dataset, [FOD-UNOmaha/FOD-data](https://github.com/FOD-UNOmaha/FOD-data) "
          "(`Examples/manyEx.png`, `Examples/Picture*.png`), MIT License, © 2020 FOD-UNOmaha.", "",
          "| Object | Label | Category | Class | Source | Author | Licence | Used in |", "|---|---|---|---|---|---|---|---|"]
    for key, o in objects["debris"].items():
        if key not in obj_uses:
            continue
        if "commons" in o:
            r = lock[o["commons"]]
            lic = f"[{r['licence']}]({r['licence_url']})" if r.get("licence_url") else r["licence"]
            s, au = f"[{r['title']}]({r['url']}) (cut-out)", r["author"]
        else:
            s = "FOD-A `" + (o.get("foda_picture") or f"manyEx.png` row {o['foda_cell'][0] + 1}, column {o['foda_cell'][1] + 1}").rstrip("`") + ("`" if o.get("foda_picture") else "")
            au, lic = "FOD-UNOmaha", "MIT"
        L.append(f"| `{key}` | {o['label']} | {o['category']} | {o['object_class']} | {s} | {au} | {lic} | {fmt(obj_uses[key])} |")
    gse = [(k, g) for k, g in objects.get("gse", {}).items() if k in obj_uses]
    if gse:
        L += ["", "## Composited GSE", "", "A GSE vehicle cut out of one photograph (polygon mask) and pasted onto an empty stand, for the equipment-staging case (FOD-R9).", "",
              "| Cut-out | Label | Source | Author | Licence | Used in |", "|---|---|---|---|---|---|"]
        for k, g in gse:
            r = lock[g["commons"]]
            lic = f"[{r['licence']}]({r['licence_url']})" if r.get("licence_url") else r["licence"]
            L.append(f"| `{k}` | {g['label']} | [{r['title']}]({r['url']}) | {r['author']} | {lic} | {fmt(obj_uses[k])} |")
    (data / "ATTRIBUTION.md").write_text("\n".join(L) + "\n")
