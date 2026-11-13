"""The agent loop with a scripted stand-in for Claude: what it is woken for, what its tools do, and how code
takes over when it fails. No API calls."""
import json

from fodgate import config, llm as llm_mod
from fodgate.dispatch import agent as agent_mod
from fodgate.dispatch.agent import AgentTools, AgentUnavailable
from tests.dispatch_rig import FakeModel, Rig, msg, rig, scenes, text, tool_use  # noqa: F401


def routing(assignee="kim"):
    """A model that gives the REMOVE Finding to `assignee`."""
    def turn(kw):
        ctx = json.loads(kw["messages"][0]["content"].split("\n\n", 1)[1])
        (work,) = ctx["work_needing_an_owner"]
        return [tool_use(1, "assign_task", type=work["type"], gate=ctx["gate"],
                         inspection_id=ctx["inspection"]["inspection_id"], finding_id=work["finding_id"], angle=None,
                         assignee_id=assignee, instruction="Remove the bag tag by the belt loader at T5 CARGO")]
    return turn


def test_routing_wake_assigns_what_code_left_and_the_hold_is_already_out(scenes, fake_llm):
    model = FakeModel(routing(), "Assigned the bag tag to Kim.")
    r = Rig(fake_llm, mode="on", create=model)
    r.inspect()
    assert len(model.requests) == 2
    first = model.requests[0]
    assert first["model"] == "claude-haiku-5-5" == config.AGENT_MODEL
    assert first["tools"] is agent_mod.TOOLS and first["output_config"] == {"effort": "low"}
    assert first["system"] == [{"type": "text", "text": agent_mod.SYSTEM, "cache_control": {"type": "ephemeral"}}]
    assert "temperature" not in first and "thinking" not in first and "tool_choice" not in first
    ctx = json.loads(first["messages"][0]["content"].split("\n\n", 1)[1])
    assert ctx["trigger"] == "inspection_completed" and ctx["gate"] == "T5"
    assert [w["finding_id"] for w in ctx["work_needing_an_owner"]] == ["F2"]          # the HOLD is not the model's to route
    assert ctx["work_needing_an_owner"][0]["eligible"][0] == "kim"
    assert [t["type"] for t in ctx["tasks_already_assigned_by_code"]] == ["ack_hold"]
    hold, remove = r.task("ack_hold"), r.task("remove")
    assert (hold["created_by"], hold["assignee_id"]) == ("code", "okafor")
    assert (remove["created_by"], remove["assignee_id"], remove["severity"]) == ("agent", "kim", "REMOVE")
    assert r.board.thread("kim")[0]["kind"] == "agent" and "bag tag by the belt loader" in r.inbox("kim")[0]
    (wake,) = r.store.query("SELECT * FROM agent_wakes")
    assert wake["outcome"] == "ok" and json.loads(wake["tool_calls"]) == ["assign_task"]
    assert wake["tokens_in"] == 2000 and wake["est_cost_usd"] > 0
    assert abs(llm_mod.process_spend()["usd"] - r.d.cost()["process_usd"]) < 1e-9
    kinds = [e["kind"] for e in r.board.activity(console_only=True)]
    assert kinds.count("wake") == 1 and kinds.count("cost") == 1 and "agent" in kinds
    r.wf.shutdown()


def test_a_clean_inspection_needs_no_model_call(scenes, fake_llm):
    model = FakeModel()
    r = Rig(fake_llm, mode="on", create=model)
    r.inspect("pa-clean", kind="pre_arrival")
    assert model.requests == []                               # one possible owner: code asks the Ramp Lead to sign off
    assert r.task("sign_off")["assignee_id"] == "okafor" and "/signoff T5" in r.inbox("okafor")[0]
    r.wf.shutdown()


def test_model_refusals_and_bad_choices_fall_back_to_code(scenes, fake_llm):
    def bad(kw):                                              # tries to give the removal to someone off shift
        return [tool_use(1, "assign_task", type="remove", gate="T5", inspection_id="x", finding_id="F2", angle=None,
                         assignee_id="patel", instruction="Remove it")]
    model = FakeModel(bad, "Could not assign.")
    r = Rig(fake_llm, mode="on", create=model)
    r.d.roster.set_shift("patel", "off")
    r.inspect()
    (result,) = model.results[0]
    assert result["is_error"] is True and "not on shift" in result["content"]
    assert r.task("remove")["created_by"] == "code" and r.task("remove")["assignee_id"] == "kim"
    r.wf.shutdown()

    for failing in (lambda **kw: msg("refusal"), lambda **kw: msg("max_tokens", text("...")),
                    lambda **kw: (_ for _ in ()).throw(AgentUnavailable("rate limited (HTTP 429)")),
                    lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))):
        r = Rig(fake_llm, mode="on", create=failing)
        r.inspect()
        assert r.task("remove")["created_by"] == "code"       # the work still has an owner
        r.say("kim", "got it")
        assert "cannot read free text right now" in r.inbox("kim")[-1]
        r.wf.shutdown()


def test_a_wake_is_bounded_to_six_model_requests(scenes, fake_llm):
    model = FakeModel(*[[tool_use(i, "get_board")] for i in range(20)])
    r = Rig(fake_llm, mode="on", create=model)
    r.inspect()
    assert len(model.requests) == agent_mod.MAX_TURNS == 6
    assert r.store.query("SELECT outcome FROM agent_wakes")[0]["outcome"] == "max_turns"
    assert r.task("remove")["created_by"] == "code"
    r.wf.shutdown()


def test_free_text_send_kim_becomes_a_task_and_a_report_becomes_a_proposal(scenes, fake_llm):
    model = FakeModel(routing(), "Assigned.")
    r = Rig(fake_llm, mode="on", create=model)
    r.inspect()
    r.cmd("okafor", "/ack F1")

    # 1. the Ramp Lead says who should go
    model.turns = [[tool_use(1, "assign_task", type="remove", gate="T5", inspection_id="T5", finding_id="F1", angle=None,
                             assignee_id="kim", instruction="Remove the hammer at T5 ENG-R and report back")],
                   "Sent Kim to the hammer."]
    r.say("okafor", "send kim, she's closest")
    prompt = model.requests[-2]["messages"][0]["content"]
    ctx = json.loads(prompt.split("\n\n", 1)[1])
    assert ctx["trigger"] == "human_message" and ctx["from"]["role"] == "ramp_lead"          # role from the roster
    assert ctx["messages"][0]["text"] == "send kim, she's closest" and "not instructions to you" in prompt
    walk = next(t for t in r.tasks() if t["finding_label"] == "F1" and t["type"] == "remove")
    assert walk["assignee_id"] == "kim" and walk["severity"] == "HOLD" and walk["created_by"] == "agent"
    assert "Remove the hammer at T5 ENG-R" in r.inbox("kim")[-1]

    # 2. Kim reports both jobs in one message
    bag = next(t for t in r.tasks() if t["finding_label"] == "F2")

    def report(kw):
        mid = json.loads(kw["messages"][0]["content"].split("\n\n", 1)[1])["messages"][0]["message_id"]
        return [tool_use(1, "log_report", task_id=walk["task_id"], kind="done", source_message_id=mid),
                tool_use(2, "log_report", task_id=bag["task_id"], kind="done", source_message_id=mid),
                tool_use(3, "propose_confirmation", to_id="kim", inspection_id="T5", finding_id="F2", outcome="removed",
                         false_alarm_reason=None),
                tool_use(4, "propose_confirmation", to_id="kim", inspection_id="T5", finding_id="F1", outcome="removed",
                         false_alarm_reason=None),
                tool_use(5, "send_message", to_id="kim", task_id=walk["task_id"],
                         text="Logged K on the hammer. A Ramp Lead records HOLDs; Okafor has it.")]
    model.turns = [report, "Logged Kim's reports; asked her to confirm F2."]
    r.say("kim", "got the hammer, its in the fod bin. bag tag picked up too")
    results = model.results[-1]
    assert [x["is_error"] for x in results] == [False, False, False, True, False]            # the HOLD proposal is refused
    assert "only a Ramp Lead can confirm a HOLD" in results[3]["content"]
    assert json.loads(results[0]["content"])["code_already_told"] == ["okafor", "kim"]
    assert "a Ramp Lead records HOLDs" in next(m["text"] for m in r.board.thread("kim") if m["kind"] == "code" and "Logged" in m["text"])
    assert r.confirmations()[-1]["action"] == "acknowledged" and len(r.confirmations()) == 1  # nothing recorded yet
    assert r.finding("F1")["status"] == "acknowledged" and r.finding("F2")["status"] == "open"
    assert "Report, not a Confirmation" in r.inbox("okafor")[-1]
    (prop,) = r.board.pending_proposals("kim")
    assert prop["created_by"] == "agent" and prop["action"]["label"] == "F2"
    reports = r.board.reports(walk["task_id"])
    assert reports[0]["raw_text"].startswith("got the hammer") and reports[0]["via"] == "free_text"

    # 3. only Kim's own y records it
    calls = len(model.requests)
    r.cmd("kim", "y")
    assert len(model.requests) == calls                       # answering is code; the model is not involved
    c = r.confirmations()[-1]
    assert (c["action"], c["name"], c["data"]["via"]) == ("removed", "Kim", "accepted_proposal")
    r.cmd("okafor", "/removed F1")
    r.cmd("okafor", "/signoff T5")
    assert r.latest()["status"] == "confirmed" and r.tasks() == []
    r.wf.shutdown()


def test_messages_from_one_person_are_coalesced_into_one_wake(scenes, fake_llm):
    model = FakeModel()
    r = Rig(fake_llm, mode="on", create=model)
    for line in ("anyone there", "hello?", "T5 looks busy"):
        mid = r.board.send("agent", line, kind="person", from_id="kim")
        r.store.add_event(type="person_message", data={"message_id": mid, "person_id": "kim"})
    r.d.settle()
    assert len(model.requests) == 1
    ctx = json.loads(model.requests[0]["messages"][0]["content"].split("\n\n", 1)[1])
    assert [m["text"] for m in ctx["messages"]] == ["anyone there", "hello?", "T5 looks busy"]
    r.wf.shutdown()


def test_read_tools_and_text_only_tools(rig):
    rep = rig.inspect()
    tools = AgentTools(rig.d)
    board = tools.get_board()
    assert [g["gate"] for g in board["gates"]] == ["T5"] and len(board["open_tasks"]) == 2
    assert {p["person_id"] for p in board["on_shift"]} == {"kim", "okafor", "patel", "reyes", "dana"}
    summary = tools.get_inspection("T5")
    assert summary["inspection_id"] == rep["inspection_id"] and [f["finding_id"] for f in summary["findings"]] == ["F1", "F2"]
    assert tools.get_finding(rep["inspection_id"], "F1")["severity"] == "HOLD"
    assert tools.get_rule("fod-r1")["id"] == "FOD-R1"
    assert [p["person_id"] for p in tools.list_people("T5", "ramp_lead")] == ["okafor"]
    assert tools.get_task(rig.task("ack_hold")["task_id"])["reports"] == []
    assert "no Findings outside the gate safety envelope" in tools.draft_outside_boundary_report("T5", "ramp_1_control", [])
    brief = tools.write_handover_brief("okafor", "reyes")
    assert "1 open Task" in brief and "Nothing in this brief is a Confirmation" in brief
    assert rig.task("ack_hold")["assignee_id"] == "okafor"    # text only: the Task did not move
    out, is_error = tools.call("escalate", {"task_id": rig.task("ack_hold")["task_id"], "reason": "Okafor is not answering"})
    assert not is_error and json.loads(out) == {"level": 1, "notified": ["okafor", "dana"]}
    out, is_error = tools.call("propose_reinspection", {"to_id": "okafor", "inspection_id": "T5", "angle": "ENG-R", "reason": "check again"})
    assert not is_error and rig.store.query("SELECT COUNT(*) AS n FROM inspections")[0]["n"] == 1   # asked, not started
    rig.cmd("okafor", "y")
    assert rig.store.query("SELECT COUNT(*) AS n FROM inspections")[0]["n"] == 2                    # the person started it
