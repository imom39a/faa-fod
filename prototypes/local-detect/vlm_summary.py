"""PROTOTYPE - summarise vlm__*.json: recall/candidates before and after the local verifier."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
for p in sys.argv[1:]:
    d = json.loads(Path(p).read_text())
    kept = {n: {**r, "findings": [f for f in r["findings"] if f["vlm_yes"]]} for n, r in d.items()}
    for lab, x in (("before", d), ("after VLM", kept)):
        s = C.summarise(C.score_candidates(x))
        print(f"{Path(p).name} {lab}: recall {s['tp']}/{s['n_gt']} cand/clean {s['cand_per_clean']:.1f} cand/noop {s['cand_per_noop']:.1f} extra/seeded {s['fp_per_seeded']:.1f} missed {s['missed']}")
    lost = [(n, f["gt_label"], f["vlm"]) for n, r in d.items() for f in r["findings"] if f["tp"] and not f["vlm_yes"]]
    print("  TP dropped by VLM:", lost)
    vs = sorted(f["vlm_s"] for r in d.values() for f in r["findings"]); print("  median s/crop", vs[len(vs)//2])
