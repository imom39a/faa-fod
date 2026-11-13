"""`python -m fodgate.rehearse`: play the always-on agent demo end to end over the real HTTP endpoints.

It starts the agent process (`python -m fodgate.agent`) on a spare port with a scratch database, then acts as
the chat page would for two people, Kim (Ramp Agent) and Okafor (Ramp Lead): sign in, poll the inbox, send
commands and free text, answer a proposal. It prints a Markdown section with the agent console output, each
person's chat thread as the inbox endpoint returns it, the Confirmations and the measured cost.

  uv run python -m fodgate.rehearse                 # live: uses the key in <repo>/.env, capped by FOD_MAX_SPEND_USD
  uv run python -m fodgate.rehearse --keyless       # no key at all: code-only routing, slash commands only

Standard library only. The saved Claude results in app/var/cache/ are copied in, so the Inspections cost nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import config

PINS = {"kim": "1111", "okafor": "2222"}


class Chat:
    """One signed-in person, talking to /api/agent/* the way the chat page does."""

    def __init__(self, base: str, person_id: str, pin: str):
        self.base, self.person_id, self.token = base, person_id, None
        self.token = self.call("POST", "/api/agent/join", {"person_id": person_id, "pin": pin})[1]["token"]

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {self.token}"} if self.token else {})})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def inbox(self) -> dict:
        return self.call("GET", "/api/agent/inbox?after=0")[1]

    def texts(self) -> list[str]:
        return [m["text"] for m in self.inbox()["messages"] if m["to"] == self.person_id]

    def command(self, text: str) -> tuple[int, dict]:
        return self.call("POST", "/api/agent/command", {"text": text})

    def say(self, text: str) -> tuple[int, dict]:
        return self.call("POST", "/api/agent/say", {"text": text})


def wait_for(what: str, check, timeout: float = 90.0):
    end = time.time() + timeout
    while time.time() < end:
        got = check()
        if got:
            return got
        time.sleep(0.4)
    raise TimeoutError(f"timed out waiting for: {what}")


def run(args) -> int:
    var = Path(tempfile.mkdtemp(prefix="fod-rehearsal-"))
    shutil.copytree(config.REPO_ROOT / "app" / "var" / "cache", var / "cache")
    env = dict(os.environ, FOD_VAR_DIR=str(var), FOD_TIMELINE="timeline-agent.json", FOD_AGENT="on",
               FOD_MAX_SPEND_USD=os.environ.get("FOD_MAX_SPEND_USD") or "0.50", NO_COLOR="1", COLUMNS="110",
               PYTHONUNBUFFERED="1")
    if args.keyless:
        env.pop("ANTHROPIC_API_KEY", None)
        env["FOD_ENV_FILE"] = os.devnull                     # the key in <repo>/.env is not read
    console = var / "console.txt"
    base = f"http://127.0.0.1:{args.port}"
    notes: list[str] = []
    with console.open("w") as out:
        proc = subprocess.Popen([sys.executable, "-m", "fodgate.agent", "--port", str(args.port), "--no-colour"],
                                cwd=config.BACKEND_DIR, env=env, stdout=out, stderr=subprocess.STDOUT)
    anon = Chat.__new__(Chat)
    anon.base, anon.token, anon.person_id = base, None, None
    try:
        wait_for("the server", lambda: _up(anon), 60)
        health = anon.call("GET", "/api/health")[1]
        picker = anon.call("GET", "/api/agent/roster")[1]["people"]
        kim, okafor = Chat(base, "kim", PINS["kim"]), Chat(base, "okafor", PINS["okafor"])
        started = time.time()
        anon.call("POST", "/api/demo/speed", {"speed": args.speed})
        anon.call("POST", "/api/demo/play")

        # T8: a clean pre-arrival Inspection. Code asks the Ramp Lead to sign off; no model call.
        wait_for("T8 sign-off request", lambda: any("/signoff T8" in t for t in okafor.texts()))
        idle_cost = anon.call("GET", "/api/agent/board")[1]["cost"]
        notes.append(f"Before the first Finding the agent had made {idle_cost['model_requests']} model requests "
                     f"(${idle_cost['agent_session_usd']:.4f}).")
        okafor.command("/signoff T8")

        # T5: hammer at ENG-R (HOLD) and bag tag at CARGO (REMOVE).
        hold = wait_for("HOLD alert to Okafor", lambda: next((t for t in okafor.texts() if t.startswith("HOLD at T5")), None))
        f_hold = re.search(r"\((F\d+)\)", hold).group(1)
        bag = wait_for("Kim's bag tag Task", lambda: next((t for t in kim.inbox()["tasks"] if t["severity"] == "REMOVE"), None))
        notes.append(f"The bag tag Task {bag['task_id']} was created by `{bag['created_by']}`.")

        status, body = kim.command(f"/ack {f_hold}")           # a Ramp Agent tries to acknowledge the HOLD
        notes.append(f"Kim's `/ack {f_hold}` returned HTTP {status} `{body.get('error')}`.")

        wait_for("the 30 s Escalation", lambda: any(t.startswith("Second call") for t in okafor.texts()), 120)
        okafor.command(f"/ack {f_hold}")

        if args.keyless:
            okafor.command(f"/send kim {f_hold} remove the hammer at T5 ENG-R and report back")
        else:
            okafor.say("send kim, she's closest")
        walk = wait_for("Kim's Task on the HOLD object",
                        lambda: next((t for t in kim.inbox()["tasks"] if t["severity"] == "HOLD"), None))

        if args.keyless:
            kim.command(f"/done {walk['task_id']} in the fod bin")
            kim.command(f"/done {bag['task_id']}")
        else:
            kim.say("got the hammer, its in the fod bin. bag tag picked up too")
        prop = wait_for("a proposal for Kim", lambda: (kim.inbox()["pending_proposals"] or [None])[0])
        wait_for("Okafor told about Kim's report", lambda: any("Report, not a Confirmation" in t for t in okafor.texts()))
        open_now = anon.call("GET", "/api/state")[1]
        t5 = next(g for g in open_now["gates"] if g["gate"] == "T5")
        notes.append(f"After Kim's report and before anyone confirmed, T5 still showed highest open severity "
                     f"{t5['highest_open_severity']}.")
        status, body = kim.call("POST", f"/api/agent/proposals/{prop['proposal_id']}/answer", {"accept": True})
        notes.append(f"Kim accepted {prop['proposal_id']} ({prop['question']}): HTTP {status}.")

        status, body = okafor.command(f"/removed {f_hold}")
        notes.append(f"Okafor's `/removed {f_hold}`: {' '.join(body.get('lines', [body.get('message', '')]))}")
        wait_for("T5 sign-off request", lambda: any("/signoff T5" in t for t in okafor.texts()))
        okafor.command("/signoff T5")

        # T8 again: the clean pre-departure Inspection of the second Turn event.
        wait_for("T8 pre-departure sign-off request",
                 lambda: sum("/signoff T8" in t for t in okafor.texts()) >= 2, 200)
        okafor.command("/signoff T8")
        wait_for("both Turns departed or confirmed", lambda: all(
            g["status"] in ("departed", "confirmed_clear", "idle") for g in anon.call("GET", "/api/state")[1]["gates"]), 60)
        time.sleep(2.0)

        board = anon.call("GET", "/api/agent/board")[1]
        activity = anon.call("GET", "/api/agent/activity?limit=1000")[1]["entries"]
        threads = {p.person_id: p.inbox() for p in (kim, okafor)}
        elapsed = time.time() - started
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    print(_markdown(args, health, picker, console.read_text(), threads, activity, board, notes, elapsed))
    return 0


def _up(anon: Chat) -> bool:
    try:
        return anon.call("GET", "/api/health")[0] == 200
    except (urllib.error.URLError, ConnectionError, OSError):
        return False


def _clock(t) -> str:
    t = int(t or 0)
    return f"{t // 60:02d}:{t % 60:02d}"


def _markdown(args, health, picker, console, threads, activity, board, notes, elapsed) -> str:
    cost, wakes = board["cost"], [e for e in activity if e["event"] == "agent_wake"]
    title = "Keyless run (no API key: code-only routing)" if args.keyless else "Live run (Claude Haiku 5.5)"
    out = [f"## {title}", "",
           f"- Started with: `python -m fodgate.rehearse{' --keyless' if args.keyless else ''} --speed {args.speed}` "
           f"({elapsed:.0f} s of wall time at {args.speed}x).",
           f"- Claude available to the server: {health['llm_available']} ({health['llm_note']}).",
           f"- Agent: {cost['wakes']} wakes, {cost['model_requests']} model requests, {cost['tokens_in']} input and "
           f"{cost['tokens_out']} output tokens, **${cost['agent_session_usd']:.4f}**. Whole process (agent plus any "
           f"uncached Inspection calls): ${cost['process_usd']:.4f} of a ${cost['cap_usd']:.2f} cap.",
           "- Sign-in picker (`GET /api/agent/roster`): " + ", ".join(f"{p['name']} ({p['role']})" for p in picker) + "."]
    out += [f"- {n}" for n in notes]
    if wakes:
        out += ["", "| Wake | Trigger | Tools called | Tokens in / out | Seconds | Cost | Outcome |", "|---|---|---|---|---|---|---|"]
        for i, w in enumerate(wakes, 1):
            d = w["data"]
            out.append(f"| {i} | {d['trigger']} at {_clock(w['t'])} | {', '.join(d['tool_calls']) or 'none'} | "
                       f"{d['tokens_in']} / {d['tokens_out']} | {d.get('seconds')} | ${d['est_cost_usd']:.4f} | {d['outcome']} |")
    out += ["", "### Agent console (display only)", "", "```", console.rstrip(), "```"]
    for pid, box in threads.items():
        p = box["person"]
        out += ["", f"### {p['name']}'s chat thread ({p['role']}; `GET /api/agent/inbox?after=0`)", "", "```"]
        for m in box["messages"]:
            who = f"{p['person_id']}>" if m["from"] == pid else {"agent": "agent>", "code": "[code]"}.get(m["from"], m["from"] + ">")
            if m["kind"] == "timer":
                who = "[timer]"
            lines = m["text"].split("\n")
            out.append(f"{_clock(m['t'])} {who:<8} {lines[0]}")
            out += [f"{'':15}{line}" for line in lines[1:]]
        out += ["```", "", "Tasks at the end: " + ("; ".join(
            f"{t['task_id']} {t['type']} {t['finding_id'] or t['angle'] or t['gate']} {t['status']}"
            + (f" (Confirmation #{t['closed_by_confirmation_id']})" if t["closed_by_confirmation_id"] else "")
            for t in box["tasks"]) or "none") + "."]
    out += ["", "### Confirmations recorded (from `GET /api/agent/activity`)", "",
            "| Clock | Gate | What | By | Recorded at |", "|---|---|---|---|---|"]
    for e in activity:
        if e["event"] == "confirmation":
            d = e["data"]
            out.append(f"| {_clock(e['t'])} | {e['gate']} | {d['action']} {d.get('finding_id') or d.get('angle') or ''} | "
                       f"{d['by'].get('name')} ({d['by'].get('role')}) | {e['at']} |")
    counts: dict[str, int] = {}
    for e in activity:
        counts[e["event"]] = counts.get(e["event"], 0) + 1
    out += ["", "Activity log entries by event: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + "."]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m fodgate.rehearse", description=__doc__.split("\n\n")[0])
    ap.add_argument("--keyless", action="store_true", help="run with no API key: code-only routing")
    ap.add_argument("--port", type=int, default=8017)
    ap.add_argument("--speed", type=int, default=2, choices=(1, 2, 5, 10))
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
