"""PROTOTYPE (ticket 0012) - combine proposer outputs (no new inference; latency = sum of the parts).

usage: .venv/bin/python -I combos.py    -> prints table rows, writes results/cand__<combo>.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
from evaluate import row  # noqa: E402
from run_spike import centre, iou  # noqa: E402

R = C.RESULTS
CD = json.loads((R / f"cand__changedet{C.SUFFIX}.json").read_text())
DN = json.loads((R / f"cand__dino{C.SUFFIX}.json").read_text())
OW = json.loads((R / "cand__owl.json").read_text()) if (R / "cand__owl.json").exists() else None


def inside(pt, box, pad=0):
    return box[0] - pad <= pt[0] <= box[2] + pad and box[1] - pad <= pt[1] <= box[3] + pad


def overlaps(a, b, pad=14):
    return inside(centre(a), b, pad) or inside(centre(b), a, pad) or iou(a, b) > 0


def union(cd_thr, dn_thr):
    out = {}
    for n in CD:
        a = [dict(f, src="change", score=f["score"]) for f in CD[n]["findings"] if f["score"] >= cd_thr]
        b = [dict(f, src="dino") for f in DN[n]["findings"] if f["score"] >= dn_thr]
        # change-detection boxes are tighter; drop DINO boxes that overlap a kept change box
        b = [f for f in b if not any(overlaps(f["box"], g["box"]) for g in a)]
        out[n] = {"findings": C.merge_near(a) + [dict(f, score=f["score"] * 1000) for f in b],
                  "latency_s": round(CD[n]["latency_s"] + DN[n]["latency_s"], 3)}
    return out


def intersect(cd_thr, dn_thr):
    out = {}
    for n in CD:
        dn = [f for f in DN[n]["findings"] if f["score"] >= dn_thr]
        a = [f for f in CD[n]["findings"] if f["score"] >= cd_thr and any(overlaps(f["box"], g["box"]) for g in dn)]
        out[n] = {"findings": a, "latency_s": round(CD[n]["latency_s"] + DN[n]["latency_s"], 3)}
    return out


def owl_gated(owl_thr, cd_thr):
    out = {}
    for n in CD:
        cd = [f for f in CD[n]["findings"] if f["score"] >= cd_thr]
        a = [f for f in OW[n]["findings"] if f["score"] >= owl_thr and any(overlaps(f["box"], g["box"]) for g in cd)]
        out[n] = {"findings": C.nms_boxes(a, 0.2, 40), "latency_s": round(CD[n]["latency_s"] + OW[n]["latency_s"], 3)}
    return out


def change_only(cd_thr):
    return {n: {"findings": C.merge_near([dict(f, src="change") for f in CD[n]["findings"] if f["score"] >= cd_thr]),
                "latency_s": CD[n]["latency_s"]} for n in CD}


def main():
    print("| combo | recall | cand/clean | cand/noop | extra cand/seeded | median s |\n|---|---|---|---|---|---|")
    for cd in (20, 50, 200):
        d = change_only(cd); line, s = row(f"change>={cd} (merged)", d); print(line, s["missed"])
        C.save(f"cand__change_{cd}{C.SUFFIX}.json", d)
    for cd, dn in [(20, 0.5), (20, 0.55), (20, 0.6), (50, 0.55), (100, 0.55), (200, 0.55), (200, 0.6)]:
        d = union(cd, dn); line, s = row(f"change>={cd} OR dino>={dn}", d); print(line, s["missed"])
        C.save(f"cand__union_{cd}_{dn}{C.SUFFIX}.json", d)
    for cd, dn in [(0, 0.3), (0, 0.4), (20, 0.3), (20, 0.4), (50, 0.4)]:
        d = intersect(cd, dn); line, s = row(f"change>={cd} AND dino>={dn}", d); print(line, s["missed"])
        C.save(f"cand__and_{cd}_{dn}{C.SUFFIX}.json", d)
    if OW:
        for ot, cd in [(0.02, 0), (0.05, 0), (0.05, 20), (0.1, 0)]:
            d = owl_gated(ot, cd); line, s = row(f"owl>={ot} AND change>={cd}", d); print(line, s["missed"])


if __name__ == "__main__":
    main()
