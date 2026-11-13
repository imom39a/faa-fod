"""`python -m fodgate.agent`: the always-on agent process, with a display-only console.

It starts the API server, the demo player and the dispatcher in one process and prints the activity log as it
happens: events, the agent's decisions, Tasks, timers and cost. Nothing is typed here. People (the supervisor
included) sign in on the dashboard's chat page, which talks to /api/agent/* (app/CONTRACT.md section 5).

Standard library only for the console. Colour is used when the output is a terminal and NO_COLOR is unset.
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import textwrap
import threading
import time

PREFIX = {"code": "[code]", "wake": "[wake]", "agent": "agent>", "timer": "[timer]", "cost": "[cost]",
          "idle": "[idle]", "message": "[msg]"}
COLOUR = {"code": "36", "wake": "35", "agent": "32;1", "timer": "33;1", "cost": "90", "idle": "90", "person": "34;1",
          "message": "90"}


def clock(t: float | None) -> str:
    t = int(t or 0)
    return f"{t // 60:02d}:{t % 60:02d}"


def render(entry: dict, *, width: int, colour: bool) -> str:
    """One activity entry as wrapped lines: `MM:SS prefix  text`, continuation lines indented under the text."""
    kind, text = entry["kind"], entry["text"]
    if kind == "person":                                   # "kim> /ack F1": the person's name is the prefix
        prefix, _, text = text.partition("> ")
        prefix += ">"
    else:
        prefix = PREFIX.get(kind, f"[{kind}]")
    head = f"{clock(entry.get('t'))} {prefix:<8} "
    out = []
    for i, para in enumerate(text.split("\n")):
        wrapped = textwrap.wrap(para, max(30, width - len(head))) or [""]
        for j, line in enumerate(wrapped):
            out.append((head if i == 0 and j == 0 else " " * len(head)) + line)
    if colour:
        code = COLOUR.get(kind, "0")
        out[0] = out[0].replace(prefix, f"\033[{code}m{prefix}\033[0m", 1)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m fodgate.agent", description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT") or 8000))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--play", action="store_true", help="start the scripted schedule at once (otherwise press Play in the dashboard)")
    ap.add_argument("--speed", type=int, default=2, choices=(1, 2, 5, 10), help="schedule speed when --play is given")
    ap.add_argument("--reset", action="store_true", help="clear earlier records before starting")
    ap.add_argument("--no-colour", action="store_true")
    args = ap.parse_args(argv)

    os.environ.setdefault("FOD_AGENT", "on")                         # `code` runs without ever calling the model
    os.environ.setdefault("FOD_TIMELINE", "timeline-agent.json")     # the short two-Gate schedule for this demo
    os.environ.setdefault("FOD_MAX_SPEND_USD", "1.00")
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("anthropic").setLevel(logging.ERROR)           # keep SDK notices off the display

    import uvicorn

    from . import config
    from .api import create_app

    app = create_app()
    d, player = app.state.dispatcher, app.state.player
    if args.reset:
        player.reset()
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, log_level="warning"))
    threading.Thread(target=server.run, name="uvicorn", daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    else:
        print(f"The server did not start on port {args.port} (is it in use? try PORT=8010).", file=sys.stderr)
        return 1

    colour = sys.stdout.isatty() and not args.no_colour and not os.environ.get("NO_COLOR")
    width = shutil.get_terminal_size((100, 24)).columns
    ok, why = d.model_ready()
    cap = config.max_spend_usd()
    rule = "=" * min(width, 78)
    print(rule)
    print("Gate FOD inspection: always-on agent")
    print(f"Dashboard and chat page  http://localhost:{args.port}")
    print(f"Schedule                 {config.timeline_path().name}" + ("" if args.play else "   (press Play in the dashboard)"))
    print(f"Agent model              {config.AGENT_MODEL if ok else 'not used: ' + why}")
    print(f"Spend cap                {'$%.2f' % cap if cap is not None else 'none'}")
    print("Roster                   " + "; ".join(f"{p['name']} ({p['role'].replace('_', ' ')}, {', '.join(p['gates'])})"
                                                   for p in d.roster.people() if p["role"] != "supervisor"))
    print("This console only displays. People sign in on the chat page. Ctrl-C stops the agent.")
    print(rule, flush=True)
    if args.play:
        player.set_speed(args.speed)
        player.play()

    cursor, epoch = 0, d.store.epoch
    try:
        while True:
            if d.store.epoch != epoch:
                cursor, epoch = 0, d.store.epoch
            for e in d.board.activity(cursor, console_only=True):
                cursor = e["id"]
                print(render(e, width=width, colour=colour), flush=True)
            time.sleep(0.25)                                 # reads the local log; this is not a model call
    except KeyboardInterrupt:
        print("\nStopping.")
    server.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
