"""PROTOTYPE - build results/examples.jpg: CURRENT | REFERENCE crop pairs for a few telling Candidates."""
import json, sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

H = {k: json.loads((C.RESULTS / f"hybrid__{k}.json").read_text())["results"] for k in ("cand__change_20", "cand__union_20_0.6")}
PICK = [("cand__change_20", "brussels__fod1.jpg", (1181, 1915)), ("cand__change_20", "pelita_pwf__fod1.jpg", (2640, 1839)),
        ("cand__union_20_0.6", "wingo__fod2.jpg", (291, 1440)), ("cand__change_20", "pelita_pwf__noop.jpg", (3200, 1302)),
        ("cand__change_20", "wingo__fod2.jpg", (3554, 1380)), ("cand__change_20", "spring__fod2.jpg", (1992, 1592))]
rows = []
for run, name, (x, y) in PICK:
    c = min(H[run][name]["candidates"], key=lambda c: abs(c["box"][0] - x) + abs(c["box"][1] - y))
    d = c["decision"]; h = d.get("haiku")
    cur, _ = C.crop_candidate(C.load(name), c["box"]); ref, _ = C.crop_candidate(C.make_reference(C.GT[name]["frame"]), c["box"])
    pair = cv2.cvtColor(np.hstack([cur, np.full((320, 6, 3), 255, np.uint8), ref]), cv2.COLOR_RGB2BGR)
    lab = C.label_candidates(name, [c])[0]["gt_label"] or "not seeded"
    verdict = f"{'FOD' if d['is_fod'] else 'not FOD'} ({d['confidence']}, {d['model'][7:13]})" + (f" <- haiku {'FOD' if h['is_fod'] else 'not'} {h['confidence']}" if h else "")
    panel = np.full((380, pair.shape[1], 3), 255, np.uint8); panel[60:] = pair
    cv2.putText(panel, f"{name} [{c.get('src', c['origin'])}]  truth: {lab}", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)
    cv2.putText(panel, verdict, (6, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 160), 1)
    rows.append(panel)
grid = np.vstack([np.hstack(rows[i:i + 2]) for i in range(0, len(rows), 2)])
cv2.imwrite(str(C.RESULTS / "examples.jpg"), grid, [cv2.IMWRITE_JPEG_QUALITY, 88])
print("wrote", C.RESULTS / "examples.jpg")
