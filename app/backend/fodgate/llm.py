"""Claude calls for the pipeline: Candidate decisions, tiled passes, equipment scan.

- Haiku 5.5 by default; Sonnet 5.5 only as the optional escalation (FOD_ESCALATION=sonnet); never Opus.
- Every call uses structured output (`output_config.format`) and adaptive thinking.
- Results are cached by content hash in app/var/cache/ (FOD_LLM_CACHE), so demo replays cost nothing.
- Tokens and cost are recorded per call. A billing / credit / auth error stops all further API calls.
- The API key is loaded from <repo>/.env into this process only and is never printed or logged.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from . import config
from .detect.geometry import centre_dist, clamp_box, crop_candidate, iou

log = logging.getLogger("fodgate.llm")

# $ per million tokens (input, output). Source: claude-api skill model table (cached 2026-11-03).
PRICES = {config.HAIKU: (0.10, 0.50), config.SONNET: (2.00, 10.00)}
HAIKU_LONG_PROMPT_TOKENS = 100_000        # Haiku 5.5 switches to a higher rate card above this prompt size
HAIKU_LONG_PRICES = (0.50, 2.50)

BATCH_SIZE = 30                           # Candidates per decision call (= the per-Angle Candidate cap)
CTX_W = 1280                              # downscaled context frame width
TILE_W, TILE_H = 2048, 1152               # tiled pass: native-resolution tiles (2x2 on a 4K frame)
SCAN_W = 2048                             # equipment scan: whole frame downscaled to this width

CATEGORIES = ["fasteners_hardware", "aircraft_parts", "tools", "luggage_parts", "catering_flightline",
              "cargo_packaging", "pavement_construction", "natural", "unidentified"]


class LLMError(Exception):
    """One call failed; the caller decides what that means for the Angle."""


class LLMUnavailable(LLMError):
    """No further API calls will be made in this process (no key, billing / credit error, spend cap)."""


@dataclass
class CallRecord:
    model: str
    purpose: str            # decide | escalate | safety_net | equipment_scan | workflow
    tokens_in: int
    tokens_out: int
    est_cost_usd: float     # what the call costs uncached (a cache hit spends nothing; see `cached`)
    ms: int
    cached: bool
    stop_reason: str
    started: float
    ended: float

    def public(self) -> dict:
        return {"model": self.model, "purpose": self.purpose, "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out, "est_cost_usd": round(self.est_cost_usd, 6),
                "ms": self.ms, "cached": self.cached}


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = PRICES[model]
    if model == config.HAIKU and tokens_in > HAIKU_LONG_PROMPT_TOKENS:
        pin, pout = HAIKU_LONG_PRICES
    return (tokens_in * pin + tokens_out * pout) / 1e6


def short_model(model: str) -> str:
    return "sonnet" if "sonnet" in model else "haiku"


# ---------------------------------------------------------------------- prompts and schemas
def decide_system(rules_json: str) -> str:
    return f"""You are the reasoning step of an airline FOD (Foreign Object Debris) inspection system for aircraft gates.
A proposer has marked Candidates: regions of a fixed-camera frame that changed or look unusual. Most Candidates are NOT FOD: lighting changes, shadows, stains, markings, pavement texture, reflections, noise, people, vehicles and equipment.

For each Candidate you get the CURRENT native-resolution crop (the red rectangle marks the Candidate; judge only what is inside it) and, when the Gate has one, a REFERENCE crop of the same pixels from a recent clean frame of the same fixed camera (taken at a different time, so lighting, noise and shadows may differ slightly). Use the context frame to see where the Candidate is.

Give each Candidate one verdict:
- "fod": a distinct physical object lying on the ground inside the rectangle that does not belong there (and is not in the reference, when there is one). There is no minimum size: a small, compact object that is new relative to the reference is FOD even if you cannot identify it (category "unidentified", rule FOD-R5). Loose or misplaced chocks, cones and tow bars are FOD (FOD-R8).
- "equipment": ground support equipment (tug, belt loader, cart, dolly, stairs, GPU, fuel or catering truck), or chocks and cones placed deliberately. Code decides separately whether it is staged in the wrong place.
- "observation": snow or ice, a liquid spill, or live wildlife (FOD-R7). These are reported but are not FOD.
- "not_fod": the same thing in both crops, or only pavement, texture, a stain, a brightness or shadow change, a painted marking, the aircraft, the jet bridge or people.

For "fod", choose the category from the rule set and set material to "hard" or "light" when you can tell (a bag tag is light; a can or a pen is hard), otherwise "unsure". Do not output a severity, zone or rule: code computes those from the rule set. Confidence is shown to people and never lowers severity, so report it honestly.
Always fill every field. Use category "none" unless the verdict is "fod", and observation_kind "none" unless the verdict is "observation". "reason" is one short line a ramp agent can read (why it is or is not FOD). "location_text" is a short verbal location in the scene, for example "about 1 m ahead of the left engine intake lip".

<rule_set>
{rules_json}
</rule_set>"""


DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "integer"},
                "what_is_visible": {"type": "string"},
                "verdict": {"type": "string", "enum": ["fod", "equipment", "observation", "not_fod"]},
                "category": {"type": "string", "enum": CATEGORIES + ["none"]},
                "material": {"type": "string", "enum": ["hard", "light", "unsure"]},
                "observation_kind": {"type": "string", "enum": ["snow_ice", "live_wildlife", "spill", "none"]},
                "location_text": {"type": "string"},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "reason": {"type": "string"},
            },
            "required": ["candidate_id", "what_is_visible", "verdict", "category", "material", "observation_kind",
                         "location_text", "confidence", "reason"],
            "additionalProperties": False}},
    },
    "required": ["decisions"],
    "additionalProperties": False,
}

TILED_SYSTEM = """You are an airport ramp-safety inspector reviewing fixed-camera images of a narrowbody aircraft gate (apron/stand).

Task: find FOD (Foreign Object Debris) ON THE GROUND: any loose object lying on the apron surface that does not belong there and could be ingested by an engine, cut a tyre or injure someone. Typical FOD: tools (wrenches, pliers, hammers, screwdrivers, cutters), bolts, nuts, washers, safety wire, metal strips, rocks or pavement chunks, plastic bags, wrapping, bottle or can, bag tags, luggage parts, rags, rubber pieces, hose or wire pieces.

NOT FOD (do not report): the aircraft and its parts; jet bridge; ground support equipment (tugs, belt loaders, carts, dollies, stairs, fuel trucks, GPU, hoses connected to the aircraft); people; deliberately placed safety cones and wheel chocks; painted markings, stand numbers, lines; cracks, joints, stains, oil spots, puddles, tyre marks, shadows and reflections; grass and things far off the apron (buildings, roads, other stands in the background).

Look carefully across the whole ground surface, including small, dark or partly shadowed objects. Small objects may be only 10-30 pixels across. Report each distinct suspected object once. If you see nothing, return an empty findings list. Prefer reporting a genuinely suspicious small object with confidence "low" over silently ignoring it, but do not report normal equipment or markings. Every hit is checked again in a second step, so a doubtful object should be reported rather than dropped.

Coordinates: give each finding a tight bounding box in ABSOLUTE PIXELS of the image it appears in, origin at the top-left, x to the right, y down, as x1,y1 (top-left corner) and x2,y2 (bottom-right corner)."""


def tiled_schema(n_tiles: int) -> dict:
    return {
        "type": "object",
        "properties": {"findings": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "image_index": {"type": "integer", "enum": list(range(n_tiles))},
                "x1": {"type": "integer"}, "y1": {"type": "integer"},
                "x2": {"type": "integer"}, "y2": {"type": "integer"},
                "description": {"type": "string"},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["image_index", "x1", "y1", "x2", "y2", "description", "confidence"],
            "additionalProperties": False}}},
        "required": ["findings"],
        "additionalProperties": False,
    }


EQUIPMENT_SYSTEM = """You are checking a fixed wide-angle camera image of an aircraft stand just before an aircraft arrives (pre-arrival). The stand should be empty.

List every piece of ground support equipment (GSE) and every chock or cone standing on the apron: tugs and tractors, belt loaders, baggage carts and dollies, container loaders, passenger stairs, ground power units, air-start units, fuel, catering and lavatory trucks, tow bars, wheel chocks and safety cones. Do not list the jet bridge, fixed stand equipment, buildings, aircraft, people, painted markings or anything clearly on another stand far in the background.

Give each item a tight bounding box in ABSOLUTE PIXELS of this image (origin top-left, x right, y down) as x1,y1,x2,y2. The box must reach down to where the item touches the ground. If there is none, return an empty list. Code decides afterwards whether an item is inside the equipment restraint line."""

EQUIPMENT_SCHEMA = {
    "type": "object",
    "properties": {"equipment": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "x1": {"type": "integer"}, "y1": {"type": "integer"}, "x2": {"type": "integer"}, "y2": {"type": "integer"},
            "label": {"type": "string"},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": ["x1", "y1", "x2", "y2", "label", "confidence"],
        "additionalProperties": False}}},
    "required": ["equipment"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------- image helpers
def b64jpeg(bgr: np.ndarray, quality: int = 90) -> str:
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return base64.standard_b64encode(buf.tobytes()).decode()


def image_block(bgr: np.ndarray, quality: int = 90) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64jpeg(bgr, quality)}}


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def context_image(bgr: np.ndarray, cands: list[dict]) -> np.ndarray:
    h, w = bgr.shape[:2]
    s = min(1.0, CTX_W / w)
    im = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else bgr.copy()
    for c in cands:
        x1, y1, x2, y2 = (int(v * s) for v in c["box"])
        cv2.rectangle(im, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4), (0, 0, 255), 2)
        cv2.putText(im, str(c["cid"]), (max(0, x1 - 4), max(12, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return im


def tile_origins(width: int, height: int) -> tuple[int, int, list[tuple[int, int]]]:
    """Overlapping native-resolution tiles covering the frame. 3840x2160 gives the spike's 2x2 layout."""
    tw, th = min(TILE_W, width), min(TILE_H, height)

    def starts(full: int, tile: int) -> list[int]:
        if full <= tile:
            return [0]
        n = -(-(full - tile) // (tile - 128)) + 1
        return [round(i * (full - tile) / (n - 1)) for i in range(n)]

    return tw, th, [(x, y) for y in starts(height, th) for x in starts(width, tw)]


# ---------------------------------------------------------------------- client
_spend_lock = threading.Lock()
_spend = {"usd": 0.0, "calls": 0, "stopped": None}


def process_spend() -> dict:
    """Real (uncached) spend of this process."""
    with _spend_lock:
        return dict(_spend)


def reset_process_state() -> None:
    with _spend_lock:
        _spend.update(usd=0.0, calls=0, stopped=None)


def add_spend(model: str, tokens_in: int, tokens_out: int) -> float:
    """Account a call made outside `LLM.call_json` (the assistant, the dispatch agent). Returns its cost."""
    cost = estimate_cost(model, tokens_in, tokens_out)
    with _spend_lock:
        _spend["usd"] += cost
        _spend["calls"] += 1
    return cost


def spend_allowed() -> tuple[bool, str]:
    """Whether another real API call may be made: no earlier stop, and FOD_MAX_SPEND_USD not reached.
    Every caller outside `LLM._guarded` (the assistant, the dispatch agent) checks this before each request."""
    cap = config.max_spend_usd()
    with _spend_lock:
        if not _spend["stopped"] and cap is not None and _spend["usd"] >= cap:
            _spend["stopped"] = f"spend cap ${cap:.2f} reached"
        if _spend["stopped"]:
            return False, _spend["stopped"]
    return True, "ok"


Transport = Callable[..., dict]
# transport(model=, system=, content=, schema=, effort=, max_tokens=) ->
#   {"text": str, "stop_reason": str, "tokens_in": int, "tokens_out": int}


class LLM:
    def __init__(self, transport: Transport | None = None, *, cache_dir: Path | None = None,
                 use_cache: bool | None = None, decision_model: str | None = None, escalation: str | None = None):
        self._transport = transport
        self._client = None
        self._client_lock = threading.Lock()
        self.cache_dir = cache_dir
        self.use_cache = config.llm_cache_on() if use_cache is None else use_cache
        self.decision_model = decision_model or config.decision_model()
        self.escalation = escalation or config.escalation()
        if self.decision_model not in config.ALLOWED_MODELS:
            raise ValueError(f"model {self.decision_model!r} is not allowed")

    # ------------------------------------------------------------------ availability
    def available(self) -> tuple[bool, str]:
        ok, why = spend_allowed()
        if not ok:
            return False, why
        if self._transport is not None:
            return True, "ok"
        if not config.load_api_key():
            return False, "ANTHROPIC_API_KEY is not set (expected in <repo>/.env)"
        return True, "ok"

    def anthropic_client(self):
        """The shared SDK client (also used by the assistant)."""
        with self._client_lock:
            if self._client is None:
                if not config.load_api_key():
                    raise LLMUnavailable("ANTHROPIC_API_KEY is not set (expected in <repo>/.env)")
                import anthropic
                self._client = anthropic.Anthropic(max_retries=3, timeout=120.0)
            return self._client

    # ------------------------------------------------------------------ one structured call
    def _sdk_transport(self, *, model, system, content, schema, effort, max_tokens) -> dict:
        client = self.anthropic_client()
        # Streaming + get_final_message avoids HTTP timeouts with adaptive thinking.
        with client.messages.stream(
            model=model, max_tokens=max_tokens, system=system, thinking={"type": "adaptive"},
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": content}],
        ) as stream:
            msg = stream.get_final_message()
        u = msg.usage
        tokens_in = u.input_tokens + (getattr(u, "cache_creation_input_tokens", 0) or 0) \
            + (getattr(u, "cache_read_input_tokens", 0) or 0)
        return {"text": next((b.text for b in msg.content if b.type == "text"), ""),
                "stop_reason": msg.stop_reason or "", "tokens_in": tokens_in, "tokens_out": u.output_tokens}

    def _guarded(self, **kw) -> dict:
        """Run the transport; turn billing / credit / auth failures into a process-wide stop."""
        cap = config.max_spend_usd()
        with _spend_lock:
            if _spend["stopped"]:
                raise LLMUnavailable(_spend["stopped"])
            if cap is not None and _spend["usd"] >= cap:
                _spend["stopped"] = f"spend cap ${cap:.2f} reached"
                raise LLMUnavailable(_spend["stopped"])
        if self._transport is not None:
            return self._transport(**kw)
        import anthropic
        try:
            return self._sdk_transport(**kw)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            self._stop(f"API key rejected (HTTP {e.status_code})")
            raise LLMUnavailable(_spend["stopped"]) from None
        except anthropic.RateLimitError as e:
            raise LLMError("rate limited (HTTP 429)") from e
        except anthropic.APIStatusError as e:
            msg = str(getattr(e, "message", "")).lower()
            if e.status_code == 402 or "credit" in msg or "billing" in msg:
                self._stop(f"billing / credit error (HTTP {e.status_code})")
                raise LLMUnavailable(_spend["stopped"]) from None
            raise LLMError(f"API error (HTTP {e.status_code})") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("network error calling the API") from e

    @staticmethod
    def _stop(reason: str) -> None:
        with _spend_lock:
            _spend["stopped"] = reason
        log.error("LLM calls stopped: %s", reason)

    def call_json(self, *, purpose: str, model: str, system: str, content: list[dict], schema: dict,
                  effort: str = "medium", max_tokens: int = 16000, fresh: bool = False) -> tuple[dict | None, CallRecord]:
        """One structured-output call. Returns (parsed JSON or None if the model did not finish, record).
        `fresh` skips the cache read (used when retrying a call whose answer was incomplete)."""
        if model not in config.ALLOWED_MODELS:
            raise ValueError(f"model {model!r} is not allowed")
        key = hashlib.sha256(json.dumps([model, system, schema, effort, content], sort_keys=True).encode()).hexdigest()
        cache_file = (self.cache_dir or config.cache_dir()) / f"{key}.json"
        started = time.time()
        raw, cached = None, False
        if self.use_cache and not fresh and cache_file.is_file():
            try:
                raw, cached = json.loads(cache_file.read_text()), True
            except (OSError, json.JSONDecodeError):
                raw = None
        if raw is None:
            raw = self._guarded(model=model, system=system, content=content, schema=schema, effort=effort,
                                max_tokens=max_tokens)
            cost = estimate_cost(model, raw["tokens_in"], raw["tokens_out"])
            with _spend_lock:
                _spend["usd"] += cost
                _spend["calls"] += 1
            raw["ms"] = int((time.time() - started) * 1000)
            if self.use_cache and raw.get("stop_reason") == "end_turn":
                tmp = cache_file.with_suffix(f".{threading.get_ident()}.tmp")
                tmp.write_text(json.dumps({**raw, "model": model, "purpose": purpose}))
                tmp.replace(cache_file)
        ended = time.time()
        rec = CallRecord(model=model, purpose=purpose, tokens_in=int(raw["tokens_in"]), tokens_out=int(raw["tokens_out"]),
                         est_cost_usd=estimate_cost(model, raw["tokens_in"], raw["tokens_out"]),
                         ms=int((ended - started) * 1000), cached=cached, stop_reason=raw.get("stop_reason", ""),
                         started=started, ended=ended)
        parsed = None
        if raw.get("stop_reason") == "end_turn":
            try:
                parsed = json.loads(raw["text"])
            except (json.JSONDecodeError, TypeError):
                parsed = None
        return parsed, rec

    # ------------------------------------------------------------------ decision step
    def decide(self, *, model: str, purpose: str, rules_json: str, angle: str, kind: str, light: str,
               bgr: np.ndarray, ref: np.ndarray | None, cands: list[dict],
               fresh: bool = False) -> tuple[dict[int, dict], list[CallRecord]]:
        """Decide every Candidate (dicts with `cid` and `box`). Returns ({cid: decision}, call records).
        Candidates missing from the result were not decided (the caller must not treat them as clear)."""
        h, w = bgr.shape[:2]
        decisions: dict[int, dict] = {}
        records: list[CallRecord] = []
        system = decide_system(rules_json)
        for i in range(0, len(cands), BATCH_SIZE):
            batch = cands[i:i + BATCH_SIZE]
            ctx = context_image(bgr, batch)
            content = [text_block(f"Context frame ({ctx.shape[1]}x{ctx.shape[0]}, downscaled from {w}x{h}; "
                                  "Candidates numbered in red):"), image_block(ctx, 85)]
            for c in batch:
                crop, _ = crop_candidate(bgr, c["box"])
                content += [text_block(f"Candidate {c['cid']} CURRENT (native-resolution crop):"), image_block(crop)]
                if ref is not None:
                    rcrop, _ = crop_candidate(ref, c["box"])
                    content += [text_block(f"Candidate {c['cid']} REFERENCE (same pixels, recent clean frame):"),
                                image_block(rcrop)]
                if c.get("hint"):
                    content.append(text_block(f"Candidate {c['cid']} was described by the first pass as: {c['hint']}"))
            ref_note = "" if ref is not None else " This Gate has no reference frame, so there are no REFERENCE crops."
            content.append(text_block(
                f"Angle: {angle}. Inspection kind: {kind}. Light: {light}.{ref_note} Decide every Candidate "
                f"({len(batch)} in total, ids {[c['cid'] for c in batch]}). Return one decision per Candidate."))
            parsed, rec = self.call_json(purpose=purpose, model=model, system=system, content=content,
                                         schema=DECISION_SCHEMA, fresh=fresh)
            records.append(rec)
            wanted = {c["cid"] for c in batch}
            for d in (parsed or {}).get("decisions", []):
                if d.get("candidate_id") in wanted:
                    decisions[d["candidate_id"]] = dict(d, model=model)
        return decisions, records

    # ------------------------------------------------------------------ tiled pass
    def tiled_scan(self, *, bgr: np.ndarray, angle: str, purpose: str = "safety_net") -> tuple[list[dict] | None, CallRecord]:
        """Whole-Angle FOD pass on native-resolution tiles, all tiles in one request.
        Returns ([{"box", "description", "confidence"}] in full-frame pixels, or None on failure; record)."""
        h, w = bgr.shape[:2]
        tw, th, origins = tile_origins(w, h)
        content = []
        for i, (ox, oy) in enumerate(origins):
            content += [text_block(f"image_index {i} (tile at x={ox}, y={oy}):"),
                        image_block(bgr[oy:oy + th, ox:ox + tw])]
        content.append(text_block(
            f"Angle: {angle}. The camera frame is split into {len(origins)} overlapping tiles, each {tw}x{th} px. "
            "Objects in an overlap may appear in two tiles; report them in either. Return all FOD findings; for "
            "each, set image_index to the tile it appears in and give the pixel box in THAT TILE's coordinates."))
        parsed, rec = self.call_json(purpose=purpose, model=config.HAIKU, system=TILED_SYSTEM, content=content,
                                     schema=tiled_schema(len(origins)))
        if parsed is None:
            return None, rec
        out: list[dict] = []
        for f in parsed.get("findings", []):
            i = f.get("image_index", 0)
            if not 0 <= i < len(origins):
                continue
            ox, oy = origins[i]
            box = clamp_box([ox + f["x1"], oy + f["y1"], ox + f["x2"], oy + f["y2"]], w, h)
            if any(iou(box, k["box"]) > 0.2 or centre_dist(box, k["box"]) < 40 for k in out):
                continue                                    # same object seen in two overlapping tiles
            out.append({"box": box, "description": f.get("description", ""), "confidence": f.get("confidence", "low")})
        return out, rec

    # ------------------------------------------------------------------ equipment scan (FOD-R9)
    def equipment_scan(self, *, bgr: np.ndarray) -> tuple[list[dict] | None, CallRecord]:
        """GSE, chocks and cones in a pre-arrival WIDE frame. Boxes are returned in full-frame pixels."""
        h, w = bgr.shape[:2]
        s = min(1.0, SCAN_W / w)
        im = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else bgr
        content = [image_block(im), text_block(f"Image: one {im.shape[1]}x{im.shape[0]} px wide-angle frame of the "
                                               "stand. List the equipment with pixel boxes in this image.")]
        parsed, rec = self.call_json(purpose="equipment_scan", model=config.HAIKU, system=EQUIPMENT_SYSTEM,
                                     content=content, schema=EQUIPMENT_SCHEMA)
        if parsed is None:
            return None, rec
        out = [{"box": clamp_box([e["x1"] / s, e["y1"] / s, e["x2"] / s, e["y2"] / s], w, h),
                "label": e.get("label", "equipment"), "confidence": e.get("confidence", "low")}
               for e in parsed.get("equipment", [])]
        return out, rec
