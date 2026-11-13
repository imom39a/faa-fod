"""PROTOTYPE - what did Sonnet escalation change? Haiku-only counterfactual from the stored Haiku decisions."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import run_spike as S  # noqa: E402
for p in sys.argv[1:]:
    d = json.loads(Path(p).read_text())["results"]
    flips, preds, cost = [], {}, 0.0
    for n, r in d.items():
        fs = []
        for c in r["candidates"]:
            dec = c["decision"]; h = dec.get("haiku") or dec
            lab = C.label_candidates(n, [c])[0]["tp"]
            if dec.get("haiku") and dec["is_fod"] != h["is_fod"]:
                flips.append((n, "haiku", h["is_fod"], h["confidence"], "-> sonnet", dec["is_fod"], dec["confidence"], "real" if lab else "not seeded"))
            if h["is_fod"]:
                fs.append({"box": c["box"], "description": h["what_is_visible"], "confidence": h["confidence"]})
        preds[n] = {"findings": fs, "latency_s": 0}
        cost += sum(x["cost"] for x in r["calls"] if x.get("kind") != "escalate")
    a = S.aggregate(S.score(C.IMAGES, {"results": preds}))
    print(Path(p).stem, f"HAIKU-ONLY recall {a['tp']}/{a['objects']} FA/control {a['fa_per_control_image']:.2f} FA/all {a['fa_per_image']:.2f} cost/frame {cost/len(d):.4f}")
    for f in flips:
        print("   flip:", f)
