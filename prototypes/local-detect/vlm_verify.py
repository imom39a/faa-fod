"""PROTOTYPE (ticket 0012) - optional local verifier: Qwen3-VL-4B-Instruct-4bit (mlx-vlm) on Candidate crops.

Weights reused READ-ONLY from drone-lab/.models-vision. Each Candidate crop (320 px, red box marks the
Candidate) gets a yes/no question; 'no' drops the Candidate before any API call.

usage: .venv/bin/python -I vlm_verify.py results/cand__union_20_0.6.json   -> results/vlm__<same>.json
"""
import json
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

MODEL = C.DRONE_LAB / ".models-vision/mlx-community-Qwen3-VL-4B-Instruct-4bit"
PROMPT = ("This is a close-up crop from a fixed airport apron camera. Look inside the red rectangle. "
          "Is there a loose foreign object lying on the ground there (for example a tool, bolt, nut, can, "
          "plastic, bag tag, rock, wire or other debris)? Answer 'no' if the rectangle only contains pavement, "
          "markings, stains, shadows, the aircraft, vehicles, equipment, people or nothing in particular. "
          "Answer with one word: yes or no.")


def main():
    import mlx.core as mx
    from mlx_vlm import generate, load
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config
    mx.set_memory_limit(6 * 1024**3)
    model, processor = load(str(MODEL), trust_remote_code=False)
    config = load_config(str(MODEL))
    fmt = apply_chat_template(processor, config, PROMPT, num_images=1, enable_thinking=False)
    src = Path(sys.argv[1])
    data = json.loads(src.read_text())
    out, lat = {}, []
    tmp = C.RESULTS / "_crop.png"
    for name, r in data.items():
        img = C.load(name)
        rows = []
        for f in C.label_candidates(name, r["findings"]):
            rgb, _ = C.crop_candidate(img, f["box"])
            Image.fromarray(rgb).save(tmp)
            t0 = time.perf_counter()
            res = generate(model, processor, fmt, [str(tmp)], max_tokens=4, temperature=0, verbose=False)
            dt = time.perf_counter() - t0; lat.append(dt)
            ans = res.text.strip().lower()
            rows.append({**f, "vlm": ans, "vlm_yes": ans.startswith("yes"), "vlm_s": round(dt, 3)})
        out[name] = {**r, "findings": rows}
        print(name, sum(x["vlm_yes"] for x in rows), "/", len(rows), "yes; tp kept",
              sum(x["vlm_yes"] and x["tp"] for x in rows), "/", sum(x["tp"] for x in rows), flush=True)
    tmp.unlink(missing_ok=True)
    lat.sort()
    print("median s/crop", lat[len(lat) // 2], "n", len(lat))
    C.save("vlm__" + src.name, out)


if __name__ == "__main__":
    main()
