"""Slash commands typed by a signed-in person, parsed by ordinary code. No model is involved here.

This is the only dispatch module that calls the Workflow's Confirmation methods, and it always calls them as
the person who typed: role and name come from the roster row behind the session, never from the text. A
Confirmation is therefore recorded in exactly two ways: a command (`/ack F1`) or the same person's `y` to a
proposal. The Workflow still decides whether the role may do it and whether a HOLD needs a new photo first.
"""
from __future__ import annotations

import re

from .. import assistant, config, report as R
from ..workflow import FALSE_ALARM_REASONS, WorkflowError
from .dispatcher import OUTSIDE_WORD, outside_recipient
from .models import ACTIVE, ROLE_LABEL, TYPE_LABEL, WORK_ROLES, DispatchError, role_may_take
from .tasks import follow_finding

HELP = {
    "ramp_agent": [
        "/tasks                      your open Tasks",
        "/accept K-3                 say you are on it",
        "/done K-3 [note]            report it done (a Report, not a Confirmation)",
        "/cant K-3 <reason>          say you cannot do it",
        "/cant-find K-3 [note]       report that you looked and could not find it (a Report, not a Confirmation)",
        "/removed F2                 record a REMOVE or ADVISORY Finding as removed",
        "/false-alarm F2 <reason>    shadow | marking | equipment_in_place | other",
        "/not-found F2               record that you walked it and found nothing",
        "/all-removed T5             record every open REMOVE and ADVISORY Finding at a Gate as removed",
        "/reinspect T5 ENG-R         take a new photo of one Angle",
        "/signoff T5                 sign off the Gate's latest Inspection",
        "y / n                       answer the question the agent asked you",
        "/reported F3 ramp1|airport-ops   record debris outside the envelope as reported, and who you told",
        "/handover <person>          ask someone to take all your open Tasks; your Shift ends when they accept",
        "/break  /back  /who",
        "Anything else you type goes to the agent as free text.",
    ],
    "ramp_lead": [
        "/ack F1                     acknowledge a HOLD: someone is going to it",
        "/removed F1                 record a HOLD as removed (takes a new photo; clears only if it is clean)",
        "/eye T4 ENG-R               record an unusable Angle as checked by eye",
        "/send <person> F1 [text]    send someone to a Finding (they report back; you record the HOLD)",
        "/reassign K-3 <person>      move a Task",
    ],
    "supervisor": [
        "/tasks  /who                every open Task; the roster",
        "/reassign K-3 <person>      move a Task",
        "/shift <person> on|break|off",
        "/msg <person> <text>        send a message to one person",
        "A supervisor does not record Confirmations.",
    ],
}
ANSWERS = {"y": True, "yes": True, "/y": True, "/yes": True, "n": False, "no": False, "/n": False, "/no": False}


def is_command(text: str) -> bool:
    """Text that code handles itself and that is therefore never shown to the model: a slash command, or a
    bare answer (`y`, `n`, optionally with the proposal ID). "no idea where it is" is free text."""
    t = (text or "").strip().lower()
    return t.startswith("/") or re.fullmatch(r"(y|yes|n|no)( p-\d+)?", t) is not None


def _bad(message: str) -> WorkflowError:
    return WorkflowError(422, "invalid_command", message)


def run_command(d, person: dict, text: str) -> list[str]:
    """Run one command as `person` (a roster row). Returns the lines to show them. Raises WorkflowError with
    the same codes the dashboard gets (role_not_allowed, hold_needs_acknowledge, open_findings, ...)."""
    text = " ".join((text or "").split())
    pid = person["person_id"]
    d.board.send("code", text, kind="command", from_id=pid)           # the command is part of the person's thread
    try:
        with d.lock:
            lines = _run(d, person, text)
    except DispatchError as e:
        err = WorkflowError(409, "refused", str(e))
    except WorkflowError as e:
        err = e
    else:
        d.board.send(pid, "\n".join(lines))
        d.step()                               # close Tasks and cancel timers now, not on the next tick
        return lines
    for fid, label in d.board.alias.items():                  # people know Findings by their short label
        err.message = err.message.replace(fid, label)
    d.board.send(pid, f"Refused ({err.code}): {err.message}")
    d.board.log("code", f"Refused ({err.code}): {err.message}", event="command_refused", actor=pid,
                data={"command": text, "error": err.code})
    raise err from None


def _run(d, person: dict, text: str) -> list[str]:
    parts = text.split(" ")
    cmd, args = parts[0].lower(), parts[1:]
    if cmd in ANSWERS:
        return _answer(d, person, ANSWERS[cmd], args[0] if args else None, text)
    handler = COMMANDS.get(cmd)
    if handler is None:
        raise _bad(f"Unknown command {cmd}. Type /help.")
    return handler(d, person, args, text)


# ---------------------------------------------------------------------- helpers
def _actor(person: dict) -> dict:
    if person["role"] not in WORK_ROLES:
        raise WorkflowError(403, "role_not_allowed", "A supervisor does not record Confirmations; a Ramp Agent or Ramp Lead does")
    return {"role": person["role"], "name": person["name"]}       # from the roster, never from the request


def _who(person: dict) -> str:
    return f"{person['name']} ({ROLE_LABEL[person['role']]})"


def _gate_report(d, gate: str | None) -> tuple[str, dict]:
    gate = (gate or "").upper()
    if gate not in d.wf.gates:
        raise _bad(f"Name a Gate: one of {', '.join(d.wf.gates)}")
    turn = d.store.current_turn(gate)
    latest = d.store.latest_report(turn["turn_id"]) if turn and turn["phase"] != "departed" else None
    if latest is None:
        raise WorkflowError(404, "not_found", f"Gate {gate} has no Inspection in a Turn in progress")
    return gate, latest


def _finding(d, label: str | None) -> tuple[dict, dict, dict]:
    if not label or not re.fullmatch(r"[Ff]\d+", label):
        raise _bad("Name a Finding by its short ID, for example F1")
    try:
        return d.board.resolve(label)
    except DispatchError as e:
        raise WorkflowError(404, "not_found", str(e)) from None


def _recorded(d, before: int, person: dict, via: str, raw: str, proposal_id: str | None = None,
              extra: dict | None = None) -> None:
    """Stamp how the Confirmation rows just written were made (spec/dispatch.md: audit)."""
    d.store.annotate_confirmations(before, {"via": via, "raw_text": raw, "person_id": person["person_id"],
                                            **({"proposal_id": proposal_id} if proposal_id else {}), **(extra or {})})


def _confirm(d, person: dict, label: str, outcome: str, *, reason: str | None = None, source: str | None = None,
             via: str = "command", raw: str = "", proposal_id: str | None = None, extra: dict | None = None) -> list[str]:
    """Record a Confirmation on a Finding as this person, always on the Turn's latest Inspection."""
    by = _actor(person)
    ref, report, f = _finding(d, label)
    label, angle, gate = ref["label"], f["angle"], report["gate"]
    hold_removed = f["severity"] == "HOLD" and outcome == "removed"
    if hold_removed and f["status"] == "acknowledged" and d.rules.role_may_confirm(by["role"], "HOLD"):
        d.board.send(person["person_id"], f"Re-inspecting {gate} {angle} ...")
    before = d.store.last_confirmation_id()
    new = d.wf.confirm_finding(report["inspection_id"], f["finding_id"], outcome=outcome, role=by["role"],
                               name=by["name"], false_alarm_reason=reason, possible_source=source)
    _recorded(d, before, person, via, raw, proposal_id, extra)
    if outcome == "acknowledged":
        return [f"Recorded: {label} acknowledged by {_who(person)}."]
    if not hold_removed:
        return [f"Recorded: {label} {outcome.replace('_', ' ')}, confirmed by {_who(person)}."]
    after = follow_finding(f, new) if new["inspection_id"] != report["inspection_id"] else None
    if after is not None and not R.is_open(after):
        return [f"New photo of {gate} {angle} is clean. Recorded: {label} removed, confirmed by {_who(person)}."]
    d.board.advance_refs(ref["turn_id"])
    more = d.hold_still_present(label, person["person_id"])
    return [f"The new photo of {gate} {angle} still shows the object. {label} stays open (HOLD); nothing was recorded.",
            *more]


# ---------------------------------------------------------------------- Confirmation commands
def _ack(d, person, args, text):
    return _confirm(d, person, args[0] if args else None, "acknowledged", raw=text)


def _removed(d, person, args, text):
    return _confirm(d, person, args[0] if args else None, "removed", source=" ".join(args[1:]) or None, raw=text)


def _false_alarm(d, person, args, text):
    reason = args[1].lower() if len(args) > 1 else "other"
    if reason not in FALSE_ALARM_REASONS:
        raise _bad(f"Reason must be one of {', '.join(FALSE_ALARM_REASONS)}")
    return _confirm(d, person, args[0] if args else None, "false_alarm", reason=reason, raw=text)


def _not_found(d, person, args, text):
    return _confirm(d, person, args[0] if args else None, "not_found_on_walk", raw=text)


_TOLD = {word: key for key, word in OUTSIDE_WORD.items()} | {"ramp-1": "ramp_1_control", "ramp1control": "ramp_1_control",
                                                             "airport": "airport_operations", "ops": "airport_operations",
                                                             "airportops": "airport_operations"}


def _reported(d, person, args, text):
    """Record debris outside the gate safety envelope as reported, with who was told. With no recipient named,
    the one the Task's draft was addressed to is used."""
    ref, report, f = _finding(d, args[0] if args else None)
    if f["zone_tier"] != "outside_boundary":
        raise _bad("/reported is for debris outside the gate safety envelope; use /removed, /false-alarm or /not-found")
    word = args[1].lower() if len(args) > 1 else None
    if word is not None and word not in _TOLD:
        raise _bad("Say who you told: /reported " + ref["label"] + " ramp1   or   /reported " + ref["label"] + " airport-ops")
    told = _TOLD[word] if word else outside_recipient(f)
    name = assistant.RECIPIENTS[told]
    _confirm(d, person, ref["label"], "acknowledged", raw=text, extra={"reported_to": told, "reported_to_name": name})
    d.board.log("code", f"Recorded: {ref['label']} at {report['gate']} reported to {name} by {_who(person)}.",
                event="outside_reported", gate=report["gate"], turn={"turn_id": ref["turn_id"]}, actor=person["person_id"],
                data={"finding_id": ref["label"], "reported_to": told, "by": person["person_id"]})
    return [f"Recorded: {ref['label']} reported to {name} by {_who(person)}. The ramp crew does not remove it."]


def _all_removed(d, person, args, text):
    by = _actor(person)
    gate, latest = _gate_report(d, args[0] if args else None)
    before = d.store.last_confirmation_id()
    rep = d.wf.confirm_all(latest["inspection_id"], role=by["role"], name=by["name"])
    n = len(d.store.annotate_confirmations(before, {"via": "command", "raw_text": text, "person_id": person["person_id"]}))
    holds = [x for x in R.open_findings(rep) if x["severity"] == "HOLD"]
    return [f"Recorded: {n} REMOVE / ADVISORY Finding{'s' if n != 1 else ''} at {gate} removed, confirmed by {_who(person)}."
            + (f" {len(holds)} HOLD stays open: a HOLD is never part of this." if holds else "")]


def _eye(d, person, args, text):
    by = _actor(person)
    gate, latest = _gate_report(d, args[0] if args else None)
    angle = (args[1] if len(args) > 1 else "").upper()
    before = d.store.last_confirmation_id()
    d.wf.checked_by_eye(latest["inspection_id"], angle, role=by["role"], name=by["name"])
    _recorded(d, before, person, "command", text)
    return [f"Recorded: {gate} {angle} checked by eye by {_who(person)}. The Verdict stays INCOMPLETE: the cameras did not cover it."]


def _signoff(d, person, args, text):
    by = _actor(person)
    gate, latest = _gate_report(d, args[0] if args else None)
    before = d.store.last_confirmation_id()
    d.wf.signoff(latest["inspection_id"], role=by["role"], name=by["name"])
    _recorded(d, before, person, "command", text)
    return [f"Inspection signed off by {_who(person)}. {gate} confirmed clear."]


def _reinspect(d, person, args, text, via: str = "command"):
    by = _actor(person)
    gate, latest = _gate_report(d, args[0] if args else None)
    angle = (args[1] if len(args) > 1 else "").upper()
    if angle not in config.ANGLES:
        raise _bad(f"Name an Angle: one of {', '.join(config.ANGLES)}")
    d.board.send(person["person_id"], f"Re-inspecting {gate} {angle} ...")
    new = d.wf.reinspect(latest["inspection_id"], angle, role=by["role"], name=by["name"])
    entry = next(a for a in new["angles"] if a["angle"] == angle)
    still = [f for f in R.open_findings(new) if f["angle"] == angle]
    state = f"unusable ({entry['unusable_reason']})" if entry["status"] != "usable" else \
        (f"{len(still)} open Finding{'s' if len(still) != 1 else ''} on it" if still else "nothing new seen on it")
    return [f"New photo of {gate} {angle}: {state}. A re-inspection never closes a Finding; open Findings stay open "
            "until a Confirmation is recorded."]


# ---------------------------------------------------------------------- Task commands (Reports)
def _my_task(d, person: dict, task_id: str | None) -> dict:
    if not task_id:
        raise _bad("Name a Task, for example K-3")
    t = d.board.task(task_id)
    if t is None:
        raise WorkflowError(404, "not_found", f"No Task {task_id}")
    if t["status"] not in ACTIVE:
        raise WorkflowError(409, "task_closed", f"{t['task_id']} is {t['status']}")
    if t["assignee_id"] != person["person_id"]:
        raise WorkflowError(403, "not_your_task", f"{t['task_id']} is with {d._name(t['assignee_id'])}")
    return t


def _task_line(d, t: dict) -> str:
    return (f"{t['task_id']}  {t['status']:<9} {t['gate']} {t['angle'] or '-':<5} {t['finding_label'] or '-':<4} "
            f"{t['severity'] or '-':<8} {t['instruction']}"
            + (f"  [Escalation level {t['escalation_level']}]" if t["escalation_level"] else ""))


def _tasks(d, person, args, text):
    mine = d.board.tasks() if person["role"] == "supervisor" else d.board.tasks(assignee_id=person["person_id"])
    if not mine:
        return ["No open Tasks."]
    return [_task_line(d, t) + (f"  -> {d._name(t['assignee_id'])}" if person["role"] == "supervisor" else "") for t in mine]


def _accept(d, person, args, text):
    t = _my_task(d, person, args[0] if args else None)
    return d.record_report(t, person, "accepted", " ".join(args[1:]) or None, "command")["lines"]


def _done(d, person, args, text):
    t = _my_task(d, person, args[0] if args else None)
    return d.record_report(t, person, "done", " ".join(args[1:]) or None, "command")["lines"]


def _cant_find(d, person, args, text):
    """A Report that the person looked and found nothing. It records no Confirmation: for a REMOVE or ADVISORY
    Finding the person is offered a proposal; for a HOLD the Ramp Lead is told and offered a re-inspection."""
    t = _my_task(d, person, args[0] if args else None)
    if t["type"] not in ("remove", "walk_and_report"):
        raise _bad(f"/cant-find is for a removal or walk Task; {t['task_id']} is '{t['type']}'. Use /cant {t['task_id']} <reason>.")
    return d.record_report(t, person, "not_found", " ".join(args[1:]) or None, "command")["lines"]


def _cant(d, person, args, text):
    t = _my_task(d, person, args[0] if args else None)
    return d.record_report(t, person, "blocked", " ".join(args[1:]) or None, "command")["lines"]


def _reassign(d, person, args, text):
    if person["role"] not in ("ramp_lead", "supervisor"):
        raise WorkflowError(403, "role_not_allowed", "Only a Ramp Lead or the supervisor can move a Task")
    if len(args) < 2:
        raise _bad("Usage: /reassign K-3 <person>")
    target = d.roster.find(args[1])
    if target is None:
        raise WorkflowError(404, "not_found", f"No such person: {args[1]}")
    t = d.reassign(args[0], target["person_id"], " ".join(args[2:]) or f"moved by {person['name']}", by=person["person_id"])
    return [f"{t['task_id']} is now with {_who(target)}."]


def _send(d, person, args, text):
    """A Ramp Lead sends someone to a Finding: the code-parsed form of "send kim, she's closest"."""
    if person["role"] not in ("ramp_lead", "supervisor"):
        raise WorkflowError(403, "role_not_allowed", "Only a Ramp Lead or the supervisor can send someone to a Finding")
    target = d.roster.find(args[0] if args else None)
    if target is None or len(args) < 2:
        raise _bad("Usage: /send <person> F1 [instruction]")
    ref, report, f = _finding(d, args[1])
    kind = "report_outside_boundary" if f["zone_tier"] == "outside_boundary" else "remove"
    t = d.assign(type=kind, gate=report["gate"], finding_label=ref["label"], angle=None, assignee_id=target["person_id"],
                 instruction=" ".join(args[2:]) or None, created_by=person["person_id"])
    return [f"{t['task_id']} is with {_who(target)}: {t['instruction']}. {ref['label']} stays open until a Confirmation is recorded."]


# ---------------------------------------------------------------------- answers to proposals
def _answer(d, person: dict, yes: bool, proposal_id: str | None, raw: str) -> list[str]:
    pending = d.board.pending_proposals(person["person_id"])
    if proposal_id:
        pending = [p for p in pending if p["proposal_id"].upper() == proposal_id.upper()]
    if not pending:
        raise WorkflowError(409, "nothing_to_answer", "There is no open question for you (it may have expired). "
                            "Use a slash command instead: /help")
    prop = pending[0]
    action = prop["action"]
    if not yes:
        d.board.set_proposal(prop["proposal_id"], "declined")
        if action["kind"] == "handover":
            d.timers.cancel(prop["proposal_id"], ("handover_timeout",))
            d.handover_not_taken(prop, "declined")
            return [f"Declined ({prop['proposal_id']}): no Task moved. {d._name(action['from_id'])} has been told."]
        return [f"Declined ({prop['proposal_id']}): nothing was recorded."]
    try:
        if action["kind"] == "confirm":
            _, _, f = _finding(d, action["label"])
            if not R.is_open(f) or f["status"] != action.get("finding_status"):
                d.board.set_proposal(prop["proposal_id"], "void")
                raise WorkflowError(409, "proposal_void", f"{prop['proposal_id']} is void: {action['label']} has changed "
                                    "since the question was asked. Nothing was recorded.")
            lines = _confirm(d, person, action["label"], action["outcome"], reason=action.get("false_alarm_reason"),
                             via="accepted_proposal", raw=raw, proposal_id=prop["proposal_id"])
        elif action["kind"] == "reinspect":
            lines = _reinspect(d, person, [action["gate"], action["angle"]], raw, via="accepted_proposal")
        elif action["kind"] == "handover":
            d.timers.cancel(prop["proposal_id"], ("handover_timeout",))
            lines = d.complete_handover(person, action)
        else:
            raise _bad("Unknown proposal")
    except WorkflowError:
        if d.board.proposal(prop["proposal_id"])["status"] == "pending":
            d.board.set_proposal(prop["proposal_id"], "void")
        raise
    d.board.set_proposal(prop["proposal_id"], "accepted")
    return lines


# ---------------------------------------------------------------------- Shift and Handover
def _holds_open_hold(d, person: dict) -> list[dict]:
    return [t for t in d.board.tasks(assignee_id=person["person_id"]) if t["severity"] == "HOLD"]


def _break(d, person, args, text):
    holds = _holds_open_hold(d, person)
    if holds:
        told = d.sole_lead_leaving(person, "tried to go on a break")
        raise WorkflowError(409, "open_hold", "You hold an open HOLD Task (" + ", ".join(t["task_id"] for t in holds)
                            + "). Hand it over first: /handover <person>."
                            + (" The supervisor has been told that no other Ramp Lead is on shift." if told else ""))
    d.sole_lead_leaving(person, "went on a break")
    d.roster.set_shift(person["person_id"], "break")
    left = d.board.tasks(assignee_id=person["person_id"])
    d.board.log("code", f"{_who(person)} went on a break.", event="shift_changed", actor=person["person_id"],
                data={"person_id": person["person_id"], "shift": "break"})
    return ["You are on a break. No new Tasks will come to you. Type /back when you return."
            + (f" You still hold {len(left)} open Task{'s' if len(left) != 1 else ''}." if left else "")]


def _back(d, person, args, text):
    d.roster.set_shift(person["person_id"], "on")
    d.board.log("code", f"{_who(person)} is back on shift.", event="shift_changed", actor=person["person_id"],
                data={"person_id": person["person_id"], "shift": "on"})
    d.resync()
    return ["You are back on shift."]


def _handover(d, person, args, text):
    if person["role"] not in WORK_ROLES:
        raise WorkflowError(403, "role_not_allowed", "A supervisor holds no Tasks; move one with /reassign")
    target = d.roster.find(args[0] if args else None)
    if target is None or target["person_id"] == person["person_id"]:
        raise _bad("Usage: /handover <person>")
    tasks = d.board.tasks(assignee_id=person["person_id"])
    if not tasks:
        raise WorkflowError(409, "nothing_to_hand_over", "You have no open Tasks to hand over")
    refusal = None
    if target["shift"] != "on":
        refusal = WorkflowError(409, "refused", f"Handover refused: {target['name']} is not on shift ({target['shift']}). "
                                "Your Tasks stay with you.")
    blocked = [t for t in tasks if not role_may_take(target["role"], t["type"])]
    if refusal is None and blocked:
        refusal = WorkflowError(403, "role_not_allowed", f"Handover refused: {target['name']} is a "
                                f"{ROLE_LABEL[target['role']]} and cannot take "
                                + ", ".join(f"{t['task_id']} ({TYPE_LABEL[t['type']]})" for t in blocked)
                                + ": a Ramp Lead is required. Your Tasks stay with you.")
    if refusal is not None:
        if d.sole_lead_leaving(person, f"tried to hand over to {target['name']}, which was refused,"):
            refusal.message += " The supervisor has been told that no other Ramp Lead is on shift."
        raise refusal
    for p in d.board.pending_proposals(target["person_id"]):
        if p["action"].get("kind") == "handover" and p["action"].get("from_id") == person["person_id"]:
            raise WorkflowError(409, "refused", f"Already asked {target['name']} ({p['proposal_id']}); waiting for their answer")
    d.start_handover(person, target)
    return [f"Asked {_who(target)} to take over {len(tasks)} Task{'s' if len(tasks) != 1 else ''}. "
            "They stay yours until they accept. You will be told if they decline or do not answer."]


# ---------------------------------------------------------------------- information and supervisor commands
def _who_cmd(d, person, args, text):
    return [f"{p['person_id']:<10} {ROLE_LABEL[p['role']]:<11} shift {p['shift']:<6} "
            f"{'signed in' if p['signed_in'] else 'not signed in':<14} Gates {', '.join(p['gates']) or '-'}"
            for p in d.roster.people()]


def _help(d, person, args, text):
    lines = list(HELP["supervisor"]) if person["role"] == "supervisor" else list(HELP["ramp_agent"])
    if person["role"] == "ramp_lead":
        lines = HELP["ramp_lead"] + lines
    return lines


def _shift(d, person, args, text):
    if person["role"] != "supervisor":
        raise WorkflowError(403, "role_not_allowed", "Only the supervisor sets someone else's shift; use /break and /back")
    target = d.roster.find(args[0] if args else None)
    if target is None or len(args) < 2:
        raise _bad("Usage: /shift <person> on|break|off")
    if args[1].lower() != "on" and _holds_open_hold(d, target):
        raise WorkflowError(409, "open_hold", f"{target['name']} holds an open HOLD Task; move it first with /reassign")
    d.roster.set_shift(target["person_id"], args[1].lower())
    d.board.log("code", f"{target['name']} is now {args[1].lower()} (set by {_who(person)}).", event="shift_changed",
                actor=person["person_id"], data={"person_id": target["person_id"], "shift": args[1].lower()})
    d.resync()
    return [f"{target['name']} is now {args[1].lower()}."]


def _msg(d, person, args, text):
    if person["role"] != "supervisor":
        raise WorkflowError(403, "role_not_allowed", "Only the supervisor uses /msg; type plain text to reach the agent")
    target = d.roster.find(args[0] if args else None)
    if target is None or len(args) < 2:
        raise _bad("Usage: /msg <person> <text>")
    d.board.send(target["person_id"], " ".join(args[1:]), kind="person", from_id=person["person_id"])
    return [f"Sent to {target['name']}."]


COMMANDS = {
    "/help": _help, "/tasks": _tasks, "/who": _who_cmd, "/roster": _who_cmd,
    "/accept": _accept, "/done": _done, "/cant": _cant, "/cant-find": _cant_find, "/reassign": _reassign, "/send": _send,
    "/ack": _ack, "/removed": _removed, "/false-alarm": _false_alarm, "/not-found": _not_found,
    "/reported": _reported, "/all-removed": _all_removed,
    "/reinspect": _reinspect, "/eye": _eye, "/signoff": _signoff,
    "/handover": _handover, "/break": _break, "/back": _back, "/shift": _shift, "/msg": _msg,
}
