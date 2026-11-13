"""FastAPI app: every endpoint and error code of app/CONTRACT.md section 2.

Run from app/backend:  uv run uvicorn fodgate.api:app --port 8000
Errors are HTTP 4xx/5xx with {"error": "<code>", "message": "..."}.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import assistant, config
from .demo import DemoPlayer
from .dispatch import Dispatcher, commands
from .dispatch.models import ACTIVE, ROLE_LABEL
from .llm import LLM, process_spend
from .rules import load_rules
from .store import Store
from .workflow import Workflow, WorkflowError

log = logging.getLogger("fodgate.api")


class Actor(BaseModel):
    role: str
    name: str


class ConfirmBody(Actor):
    outcome: str
    false_alarm_reason: str | None = None
    possible_source: str | None = None


class InspectBody(BaseModel):
    kind: str
    scene_id: str | None = None


class SpeedBody(BaseModel):
    speed: float


class AssistantBody(BaseModel):
    inspection_id: str
    message: str


class JoinBody(BaseModel):
    person_id: str | None = None
    person: str | None = None             # accepted as an alias of person_id (a roster name also works)
    pin: str


class CommandBody(BaseModel):
    text: str | None = None               # "/ack F1"
    command: str | None = None            # or the structured form: "ack" with args ["F1"]
    args: list[str | int] = []


class AnswerBody(BaseModel):
    accept: bool


class TextBody(BaseModel):
    text: str


def create_app(*, store: Store | None = None, llm: LLM | None = None, start_player: bool = True,
               assistant_create=None, agent_create=None, agent_mode: str | None = None,
               roster: dict | None = None) -> FastAPI:
    """Build the app. Tests pass their own store, a fake LLM and `start_player=False`.
    `agent_mode` (default FOD_AGENT) starts the dispatcher: `code` never calls the model, `on` may."""
    store = store or Store()
    if llm is None:
        config.load_api_key()                 # into this process only; never logged
        llm = LLM()
    wf = Workflow(store, llm)
    player = DemoPlayer(wf)
    dispatcher = Dispatcher(wf, llm, player=player, create=agent_create, mode=agent_mode, roster=roster)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if start_player:
            player.start()
            if dispatcher.mode != "off":
                dispatcher.start()
        yield
        dispatcher.stop()
        player.stop()
        wf.shutdown()

    app = FastAPI(title="Gate FOD inspection PoC", version="0.1.0", lifespan=lifespan)
    app.state.workflow, app.state.player, app.state.store, app.state.llm = wf, player, store, llm
    app.state.dispatcher = dispatcher

    # ------------------------------------------------------------------ errors
    def error(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"error": code, "message": message})

    @app.exception_handler(WorkflowError)
    async def _workflow_error(_req: Request, exc: WorkflowError):
        return error(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_req: Request, exc: RequestValidationError):
        parts = [f"{'.'.join(str(p) for p in e['loc'] if p != 'body') or 'body'}: {e['msg']}" for e in exc.errors()]
        return error(422, "invalid_request", "; ".join(parts))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_req: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unexpected(_req: Request, exc: Exception):
        log.exception("unhandled error: %s", type(exc).__name__)
        return error(500, "internal_error", "Unexpected server error")

    # ------------------------------------------------------------------ state
    def state() -> dict:
        gates, queue = wf.state()
        return {"demo": player.info(), "gates": gates, "queue": queue}

    @app.get("/api/state")
    def get_state():
        return state()

    @app.get("/api/health")
    def health():
        ok, note = llm.available()
        return {"ok": True, "llm_available": ok, "llm_note": note, "decision_model": llm.decision_model,
                "escalation": llm.escalation, "llm_cache": llm.use_cache, "spend": process_spend()}

    @app.get("/api/rules")
    def get_rules():
        return load_rules().data

    # ------------------------------------------------------------------ turns and inspections
    @app.get("/api/turns/{turn_id}")
    def get_turn(turn_id: str):
        return wf.turn_view(turn_id)

    @app.get("/api/inspections/{inspection_id}")
    def get_inspection(inspection_id: str):
        return wf.report(inspection_id)

    @app.get("/api/inspections/{inspection_id}/export")
    def export_inspection(inspection_id: str):
        return JSONResponse(wf.report(inspection_id), headers={
            "Content-Disposition": f'attachment; filename="{inspection_id}.json"'})

    # confirm-all is declared before the {finding_id} route so it is never read as a Finding ID
    @app.post("/api/inspections/{inspection_id}/findings/confirm-all")
    def confirm_all(inspection_id: str, body: Actor):
        return wf.confirm_all(inspection_id, role=body.role, name=body.name)

    @app.post("/api/inspections/{inspection_id}/findings/{finding_id}/confirm")
    def confirm(inspection_id: str, finding_id: str, body: ConfirmBody):
        return wf.confirm_finding(inspection_id, finding_id, outcome=body.outcome, role=body.role, name=body.name,
                                  false_alarm_reason=body.false_alarm_reason, possible_source=body.possible_source)

    @app.post("/api/inspections/{inspection_id}/angles/{angle}/reinspect")
    def reinspect(inspection_id: str, angle: str, body: Actor):
        return wf.reinspect(inspection_id, angle, role=body.role, name=body.name)

    @app.post("/api/inspections/{inspection_id}/angles/{angle}/checked-by-eye")
    def checked_by_eye(inspection_id: str, angle: str, body: Actor):
        return wf.checked_by_eye(inspection_id, angle, role=body.role, name=body.name)

    @app.post("/api/inspections/{inspection_id}/signoff")
    def signoff(inspection_id: str, body: Actor):
        return wf.signoff(inspection_id, role=body.role, name=body.name)

    @app.post("/api/gates/{gate}/inspect")
    def inspect(gate: str, body: InspectBody):
        return wf.start_inspection(gate, kind=body.kind, scene_id=body.scene_id)

    # ------------------------------------------------------------------ demo
    @app.post("/api/demo/play")
    def demo_play():
        player.play()
        return state()

    @app.post("/api/demo/pause")
    def demo_pause():
        player.pause()
        return state()

    @app.post("/api/demo/reset")
    def demo_reset():
        player.reset()
        return state()

    @app.post("/api/demo/speed")
    def demo_speed(body: SpeedBody):
        player.set_speed(body.speed)
        return state()

    # ------------------------------------------------------------------ assistant
    @app.post("/api/assistant")
    def ask_assistant(body: AssistantBody):
        rep = wf.report(body.inspection_id)
        out = assistant.answer(report=rep, message=body.message, llm=llm, turn=store.get_turn(rep["turn_id"]),
                               create=assistant_create)
        store.add_event(type="assistant_call", turn_id=rep["turn_id"], gate=rep["gate"], t=wf.clock(),
                        data={"inspection_id": rep["inspection_id"], **out["usage"]})
        return {"reply": out["reply"], "suggested_reinspect_angles": out["suggested_reinspect_angles"],
                "draft_report": out["draft_report"]}

    # ------------------------------------------------------------------ always-on agent (spec/dispatch.md)
    # Who is acting comes from the session token and the roster row behind it. A role or name sent in a
    # request body is ignored here (the older endpoints above still trust the body; see spec/dispatch.md).
    def signed_in(authorization: str | None) -> dict:
        scheme, _, token = (authorization or "").partition(" ")
        _, person = dispatcher.roster.session(token.strip() if scheme.lower() == "bearer" else "")
        dispatcher.roster.touch(person["person_id"])
        return person

    @app.get("/api/agent/roster")
    def agent_roster():
        """For the sign-in picker. Names, roles, Gates and Shift only; a PIN never leaves the server."""
        return {"people": dispatcher.roster.people()}

    @app.post("/api/agent/join")
    def agent_join(body: JoinBody):
        token, person = dispatcher.roster.join(body.person_id or body.person or "", body.pin)
        dispatcher.board.log("code", f"{person['name']} ({ROLE_LABEL[person['role']]}) signed in.", event="signed_in",
                             actor=person["person_id"])
        return {"token": token, "person": person}

    @app.get("/api/agent/inbox")
    def agent_inbox(after: int = 0, authorization: str | None = Header(default=None)):
        person = signed_in(authorization)
        pid, board = person["person_id"], dispatcher.board
        messages = board.thread(pid, after)
        mine = board.tasks(active=False, limit=1000) if person["role"] == "supervisor" else \
            board.tasks(assignee_id=pid, active=False, limit=1000)
        tasks = [t for t in mine if t["status"] in ACTIVE] + [t for t in mine if t["status"] not in ACTIVE][-10:]
        return {"person": person, "epoch": store.epoch, "clock_t": round(dispatcher.clock(), 1),
                "cursor": messages[-1]["message_id"] if messages else after, "messages": messages,
                "tasks": [board.task_view(t) for t in sorted(tasks, key=lambda t: t["seq"])],
                "pending_proposals": [board.proposal_view(p) for p in board.pending_proposals(pid)]}

    def run(person: dict, text: str) -> dict:
        return {"ok": True, "lines": commands.run_command(dispatcher, person, text)}

    @app.post("/api/agent/command")
    def agent_command(body: CommandBody, authorization: str | None = Header(default=None)):
        person = signed_in(authorization)
        text = body.text or ""
        if body.command:                                      # structured form, for buttons
            text = " ".join(["/" + body.command.strip().lstrip("/"), *[str(a) for a in body.args]])
        if not commands.is_command(text):
            raise WorkflowError(422, "invalid_command", "A command starts with / (or is y / n). Type /help.")
        return run(person, text)

    @app.post("/api/agent/proposals/{proposal_id}/answer")
    def agent_answer(proposal_id: str, body: AnswerBody, authorization: str | None = Header(default=None)):
        person = signed_in(authorization)
        return run(person, f"{'y' if body.accept else 'n'} {proposal_id}")

    @app.post("/api/agent/say")
    def agent_say(body: TextBody, authorization: str | None = Header(default=None)):
        person = signed_in(authorization)
        text = " ".join(body.text.split())
        if not text or len(text) > 500:
            raise WorkflowError(422, "invalid_request", "text must be 1 to 500 characters")
        if commands.is_command(text):            # commands are parsed by code and never reach the model
            return run(person, text) | {"routed": "command"}
        mid = dispatcher.board.send("agent", text, kind="person", from_id=person["person_id"])
        store.add_event(type="person_message", t=wf.clock(), data={"message_id": mid, "person_id": person["person_id"]})
        dispatcher.step()
        return {"ok": True, "routed": "agent", "message_id": mid}

    @app.get("/api/agent/board")
    def agent_board():
        return dispatcher.view()

    @app.get("/api/agent/activity")
    def agent_activity(after: int = 0, gate: str | None = None, turn_id: str | None = None, limit: int = 500):
        """The log of what happened, oldest first. Poll with the last `cursor`; start again when `epoch` changes."""
        rows = dispatcher.board.activity(after, gate=gate or None, turn_id=turn_id or None, limit=max(1, min(limit, 1000)))
        return {"epoch": store.epoch, "cursor": rows[-1]["id"] if rows else after, "entries": rows,
                "cost": dispatcher.cost()}

    # ------------------------------------------------------------------ images
    @app.get("/images/{scene_id}/{path:path}")
    def image(scene_id: str, path: str):
        base = config.crops_dir() if scene_id == "_crops" else config.data_dir() / "scenes" / scene_id
        base = base.resolve()
        target = (base / path).resolve()
        if not target.is_relative_to(base) or not target.is_file() or target.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            raise WorkflowError(404, "not_found", "Image not found")
        return FileResponse(target, headers={"Cache-Control": "max-age=3600"})

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False)
    def api_not_found(rest: str):
        raise WorkflowError(404, "not_found", f"No such endpoint: /api/{rest}")

    dist: Path = config.frontend_dist()
    if dist.is_dir() and (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
    return app


_app: FastAPI | None = None


def __getattr__(name: str):
    """`fodgate.api:app` is built on first access, so importing this module has no side effects."""
    global _app
    if name == "app":
        if _app is None:
            logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
            _app = create_app()
        return _app
    raise AttributeError(name)
