"""PROTOTYPE (ticket 0012) - sweep a candidate file over score thresholds / top-K and print the table.

usage: .venv/bin/python -I evaluate.py results/cand__changedet.json [--thr 0 50 100] [--topk 5 10 20] [--key score]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402


def filt(data, thr=None, topk=None, key="score"):
    out = {}
    for name, r in data.items():
        f = sorted(r["findings"], key=lambda d: -d[key])
        if thr is not None:
            f = [d for d in f if d[key] >= thr]
        if topk:
            f = f[:topk]
        out[name] = {**r, "findings": f}
    return out


def row(label, data):
    s = C.summarise(C.score_candidates(data))
    return (f"| {label} | {s['tp']}/{s['n_gt']} ({s['recall']:.0%}) | {s['cand_per_clean']:.1f} | {s['cand_per_noop']:.1f} "
            f"| {s['fp_per_seeded']:.1f} | {s['median_latency_s']} |"), s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path"); ap.add_argument("--thr", type=float, nargs="*", default=[])
    ap.add_argument("--topk", type=int, nargs="*", default=[]); ap.add_argument("--key", default="score")
    ap.add_argument("--missed", action="store_true")
    a = ap.parse_args()
    data = json.loads(Path(a.path).read_text())
    print("| setting | recall | cand/clean | cand/noop | extra cand/seeded | median s |\n|---|---|---|---|---|---|")
    line, s = row("all", data); print(line)
    if a.missed:
        print("   missed:", s["missed"])
    for t in a.thr:
        line, s = row(f"{a.key}>={t:g}", filt(data, thr=t, key=a.key)); print(line)
        if a.missed:
            print("   missed:", s["missed"])
    for k in a.topk:
        line, s = row(f"top{k}", filt(data, topk=k, key=a.key)); print(line)
        if a.missed:
            print("   missed:", s["missed"])


if __name__ == "__main__":
    main()
