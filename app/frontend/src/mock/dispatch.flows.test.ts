/**
 * The mock dispatcher's Shift Handover, "not found" / "still there" and
 * outside-envelope flows, as app/backend/fodgate/dispatch/ runs them.
 */
import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import { MockBackend } from './backend';
import { MockDispatcher } from './dispatch';

function setup(startAt = 0) {
  const backend = new MockBackend({ startAt });
  const d = new MockDispatcher(backend);
  const advance = (t: number) => {
    backend.advanceTo(t);
    d.step();
  };
  const join = (id: string, pin: string) => d.join(id, pin).token;
  return { backend, d, advance, join };
}

function refusal(fn: () => unknown): { code: string; message: string } {
  try {
    fn();
  } catch (e) {
    if (e instanceof ApiError) return { code: e.code, message: e.message };
    throw e;
  }
  return { code: 'no_error', message: '' };
}

const texts = (d: MockDispatcher, token: string) => d.inbox(token).messages.map((m) => m.text);
const events = (d: MockDispatcher) => d.activity().entries.map((e) => e.event);
const confirmations = (d: MockDispatcher) => d.activity().entries.filter((e) => e.event === 'confirmation');
const shiftOf = (d: MockDispatcher, id: string) => d.roster().people.find((p) => p.person_id === id)?.shift;
const boardTask = (d: MockDispatcher, taskId: string) => d.board().tasks.find((t) => t.task_id === taskId)!;
const timersOf = (d: MockDispatcher, taskId: string) => d.board().timers.filter((t) => t.task_id === taskId);

/** The T5 story at 0:17: Okafor holds the HOLD (F1, ENG-R), Kim holds the bag tag (F2, CARGO). */
function t5() {
  const s = setup();
  const kim = s.join('kim', '1111');
  const okafor = s.join('okafor', '2222');
  const reyes = s.join('reyes', '4444');
  const dana = s.join('dana', '9999');
  s.advance(17);
  const hold = s.d.inbox(okafor).tasks.find((t) => t.type === 'ack_hold' && t.gate === 'T5')!;
  const tag = s.d.inbox(kim).tasks.find((t) => t.type === 'remove' && t.gate === 'T5')!;
  // Confirmations already in the log (a scripted sign-off at another Gate): nothing below may add to them unasked.
  return { ...s, kim, okafor, reyes, dana, hold, tag, base: confirmations(s.d).length };
}

describe('mock dispatcher: not found is a Report', () => {
  it('REMOVE Task: /cant-find logs a Report, code asks the same person, and only their yes records it', () => {
    const { backend, d, kim, tag } = t5();
    const before = confirmations(d).length;
    const out = d.command(kim, `/cant-find ${tag.task_id} walked the belt loader side twice`);
    expect(out.lines[0]).toBe(`Logged your Report on ${tag.task_id}. F2 stays open until a Confirmation is recorded.`);
    expect(d.inbox(kim).tasks.find((t) => t.task_id === tag.task_id)?.status).toBe('reported');
    expect(boardTask(d, tag.task_id).reports.at(-1)).toMatchObject({ kind: 'not_found', by_person_id: 'kim', via: 'command', raw_text: 'walked the belt loader side twice' });
    // Nothing was recorded by the Report.
    expect(confirmations(d)).toHaveLength(before);
    expect(backend.getInspection(tag.inspection_id).findings.find((f) => f.finding_id === tag.inspection_finding_id)?.status).not.toBe('confirmed');

    const [prop] = d.inbox(kim).pending_proposals;
    expect(prop).toMatchObject({ kind: 'confirm', question: 'record F2 as not found on walk', created_by: 'code', action: { label: 'F2', outcome: 'not_found_on_walk' } });
    expect(d.command(kim, `y ${prop!.proposal_id}`).lines[0]).toBe('Recorded: F2 not found on walk, confirmed by Kim (Ramp Agent).');
    expect(d.inbox(kim).tasks.find((t) => t.task_id === tag.task_id)).toMatchObject({ status: 'closed', close_reason: 'F2 not found on walk, confirmed by Kim' });
    expect(confirmations(d)).toHaveLength(before + 1);
  });

  it('REMOVE Task: declining the proposal records nothing', () => {
    const { d, kim, tag, base } = t5();
    d.command(kim, `/cant-find ${tag.task_id}`);
    expect(d.command(kim, 'n').lines[0]).toMatch(/^Declined \(P-\d+\): nothing was recorded\.$/);
    expect(d.inbox(kim).tasks.find((t) => t.task_id === tag.task_id)?.status).toBe('reported');
    expect(confirmations(d)).toHaveLength(base);
  });

  it('is refused for any other Task type and for someone else\'s Task', () => {
    const { d, kim, okafor, hold, tag } = t5();
    const r = refusal(() => d.command(okafor, `/cant-find ${hold.task_id}`));
    expect(r.code).toBe('invalid_command');
    expect(r.message).toContain(`/cant-find is for a removal or walk Task; ${hold.task_id} is 'ack_hold'`);
    expect(refusal(() => d.command(okafor, `/cant-find ${tag.task_id}`)).code).toBe('not_your_task');
    expect(d.inbox(kim).pending_proposals).toHaveLength(0);
  });

  it('HOLD removal: nothing is proposed to the Ramp Agent; the Ramp Lead is told and offered a new photo', () => {
    const { d, kim, okafor, hold } = t5();
    d.command(okafor, '/ack F1');
    const sent = d.command(okafor, '/send kim F1');
    expect(sent.lines[0]).toMatch(/^K-\d+ is with Kim \(Ramp Agent\): .*F1 stays open until a Confirmation is recorded\.$/);
    const removal = d.inbox(kim).tasks.find((t) => t.type === 'remove' && t.finding_id === 'F1')!;
    expect(removal).toMatchObject({ severity: 'HOLD', angle: 'ENG-R', created_by: 'okafor' });
    expect(removal.inspection_finding_id).toBe(hold.inspection_finding_id);

    const before = confirmations(d).length;
    const out = d.command(kim, `/cant-find ${removal.task_id}`);
    expect(out.lines[0]).toBe(`Logged your Report on ${removal.task_id}. F1 stays open: a Ramp Lead records HOLDs. Okafor told.`);
    expect(d.inbox(kim).pending_proposals).toHaveLength(0);
    expect(texts(d, okafor).some((t) => t.startsWith('Kim reports they could not find the object for HOLD F1 at T5 ENG-R'))).toBe(true);
    const [prop] = d.inbox(okafor).pending_proposals;
    expect(prop).toMatchObject({ kind: 'reinspect', question: 'take a new photo of T5 ENG-R', created_by: 'code', action: { gate: 'T5', angle: 'ENG-R' } });
    expect(texts(d, okafor).at(-1)).toContain('Take a new photo of T5 ENG-R now (Kim could not find the object for HOLD F1)? A re-inspection never closes a Finding by itself.');

    // Accepting takes the photo. It is still not a Confirmation: the HOLD Task stays open.
    const pending = d.beginCommand(okafor, `y ${prop!.proposal_id}`);
    expect(pending.reinspects).toBe(true);
    // The new photo is clean, and that closes nothing: F1 is carried, still open.
    expect(d.finishCommand(pending).lines[0]).toBe(
      'New photo of T5 ENG-R: 1 open Finding on it. A re-inspection never closes a Finding; open Findings stay open until a Confirmation is recorded.',
    );
    expect(confirmations(d)).toHaveLength(before);
    expect(d.inbox(okafor).tasks.find((t) => t.task_id === hold.task_id)?.status).toBe('accepted');
  });

  it('free text "can\'t find it" does the same through the mock agent, which proposes nothing itself', () => {
    const { d, kim, tag, base } = t5();
    d.say(kim, "can't find the bag tag anywhere");
    d.drainWakes();
    expect(d.inbox(kim).tasks.find((t) => t.task_id === tag.task_id)?.status).toBe('reported');
    expect(d.inbox(kim).pending_proposals[0]).toMatchObject({ created_by: 'code', action: { label: 'F2', outcome: 'not_found_on_walk' } });
    const wake = d.activity().entries.filter((e) => e.event === 'agent_wake').at(-1)!;
    expect(wake.data.tool_calls).not.toContain('propose_confirmation');
    expect(confirmations(d)).toHaveLength(base);
  });
});

describe('mock dispatcher: debris outside the gate safety envelope', () => {
  function outside() {
    const s = setup(200);
    const tokens: Record<string, string> = { kim: s.join('kim', '1111'), okafor: s.join('okafor', '2222') };
    s.advance(215);
    const task = s.d.board().tasks.find((t) => t.type === 'report_outside_boundary' && t.gate === 'T8')!;
    return { ...s, task, token: tokens[task.assignee_id ?? '']!, label: task.finding_id! };
  }

  it('names the recipient in the instruction and sends a drafted report with the Task', () => {
    const { d, task, token, label } = outside();
    expect(task.instruction).toMatch(/^Report the object outside the gate safety envelope at T8 to Ramp 1 control; do not remove it: /);
    expect(task.inspection_finding_id).toBeTruthy();
    const message = d.inbox(token).messages.find((m) => m.task_id === task.task_id)!.text;
    expect(message).toContain(`then record who you told: /reported ${label} ramp1. Draft to send`);
    const draft = message.slice(message.indexOf('\n\n') + 2).split('\n');
    expect(draft[0]).toBe('To: Ramp 1 control');
    expect(draft[1]).toBe('From: Ramp crew, Gate T8 (flight DL519)');
    expect(draft.some((l) => l.startsWith('Rule: FOD-R10.'))).toBe(true);
    expect(draft.at(-1)).toContain('A person must review it before it is sent.');
  });

  it('/reported records who was told, and refuses a recipient it does not know', () => {
    const { d, task, token, label } = outside();
    const r = refusal(() => d.command(token, `/reported ${label} tower`));
    expect(r.code).toBe('invalid_command');
    expect(r.message).toBe(`Say who you told: /reported ${label} ramp1   or   /reported ${label} airport-ops`);
    expect(boardTask(d, task.task_id).status).toBe('assigned');

    const out = d.command(token, `/reported ${label} airport-ops`);
    expect(out.lines[0]).toMatch(new RegExp(`^Recorded: ${label} reported to Airport Operations by \\w+ \\(Ramp (Agent|Lead)\\)\\. The ramp crew does not remove it\\.$`));
    const logged = d.activity().entries.find((e) => e.event === 'outside_reported')!;
    expect(logged).toMatchObject({ gate: 'T8', turn_id: 'T8-DL519', actor: task.assignee_id, data: { finding_id: label, reported_to: 'airport_operations' } });
    expect(boardTask(d, task.task_id).status).toBe('closed');
    expect(confirmations(d).some((e) => e.data.finding_id === label && e.data.action === 'acknowledged')).toBe(true);
  });

  it('with no recipient, uses the one the draft was addressed to', () => {
    const { d, token, label } = outside();
    expect(d.command(token, `/reported ${label}`).lines[0]).toContain(`${label} reported to Ramp 1 control by`);
    expect(d.activity().entries.find((e) => e.event === 'outside_reported')?.data.reported_to).toBe('ramp_1_control');
  });

  it('refuses /reported for a Finding inside the envelope', () => {
    const { d, kim } = t5();
    expect(refusal(() => d.command(kim, '/reported F2 ramp1')).code).toBe('invalid_command');
  });
});

describe('mock dispatcher: Shift Handover', () => {
  it('asks with a brief, moves nothing until accepted, then moves every Task, keeps the timers and ends the first Shift', () => {
    const { backend, d, advance, okafor, reyes, hold, base } = t5();
    const out = d.command(okafor, '/handover reyes');
    expect(out.lines[0]).toBe('Asked Reyes (Ramp Lead) to take over 1 Task. They stay yours until they accept. You will be told if they decline or do not answer.');

    const [prop] = d.inbox(reyes).pending_proposals;
    expect(prop).toMatchObject({ kind: 'handover', question: 'take over 1 Task(s) from Okafor', created_by: 'okafor', action: { from_id: 'okafor' } });
    const brief = d.inbox(reyes).messages.find((m) => m.proposal_id === prop!.proposal_id)!;
    expect(brief.from).toBe('okafor');
    const lines = brief.text.split('\n');
    expect(lines[0]).toBe('Handover from Okafor (Ramp Lead) to Reyes (Ramp Lead): 1 open Task.');
    expect(lines[1]).toMatch(new RegExp(`^- ${hold.task_id} ack_hold at T5 ENG-R F1 \\(HOLD\\), assigned, Escalation level 0: Acknowledge and clear the HOLD at T5 ENG-R: .*\\. No Report yet\\. Timers: second call if not acknowledged in \\d+ s; `));
    expect(lines[1]).toContain('Escalation level 2 if not acknowledged in');
    expect(lines.at(-2)).toBe('Nothing in this brief is a Confirmation; open Findings stay open until one is recorded.');
    expect(lines.at(-1)).toBe(`Take these over?   [y / n]   (${prop!.proposal_id})`);

    // Asked, not moved.
    expect(d.inbox(okafor).tasks.find((t) => t.task_id === hold.task_id)?.assignee_id).toBe('okafor');
    expect(shiftOf(d, 'okafor')).toBe('on');
    expect(refusal(() => d.command(okafor, '/handover reyes'))).toMatchObject({ code: 'refused', message: `Already asked Reyes (${prop!.proposal_id}); waiting for their answer` });
    const timersBefore = timersOf(d, hold.task_id);
    expect(timersBefore.map((t) => t.kind)).toEqual(expect.arrayContaining(['hold_unack_1', 'hold_unack_2', 'hold_pushback']));

    const accepted = d.command(reyes, `y ${prop!.proposal_id}`);
    expect(accepted.lines[0]).toBe(`Handover accepted: ${hold.task_id} is now yours. Running timers carry on. Okafor's Shift has ended.`);
    const moved = d.inbox(reyes).tasks.find((t) => t.task_id === hold.task_id)!;
    expect(moved).toMatchObject({ assignee_id: 'reyes', status: 'assigned', escalation_level: 0, inspection_finding_id: hold.inspection_finding_id });
    expect(d.inbox(okafor).tasks.filter((t) => t.status === 'assigned')).toHaveLength(0);
    expect(shiftOf(d, 'okafor')).toBe('off');
    expect(texts(d, okafor).at(-1)).toBe(`Reyes accepted the Handover: ${hold.task_id} moved. Your Shift has ended. Type /back if you return.`);
    // Kept, not restarted.
    expect(timersOf(d, hold.task_id)).toEqual(timersBefore);
    expect(d.board().timers.some((t) => t.kind === 'handover_timeout')).toBe(false);
    // A Handover confirms nothing.
    expect(confirmations(d)).toHaveLength(base);
    expect(backend.getState().gates.find((g) => g.gate === 'T5')?.highest_open_severity).toBe('HOLD');
    for (const e of ['handover_requested', 'task_reassigned', 'handover']) expect(events(d)).toContain(e);
    expect(d.activity().entries.find((e) => e.event === 'handover')?.data).toMatchObject({ from: 'okafor', to: 'reyes', tasks: [hold.task_id], kept: [], shift_ended: true });

    // The running Escalation carries on against the new holder.
    advance(48);
    expect(d.inbox(reyes).tasks.find((t) => t.task_id === hold.task_id)?.escalation_level).toBe(1);
    expect(texts(d, reyes).some((t) => t.startsWith('Second call: HOLD F1 at T5 ENG-R'))).toBe(true);
    expect(texts(d, okafor).some((t) => t.startsWith('Second call'))).toBe(false);
  });

  it('carries Reports in the brief', () => {
    const { d, kim, okafor, tag } = t5();
    d.command(kim, `/done ${tag.task_id} in the FOD bin`);
    d.command(kim, '/handover okafor');
    const brief = texts(d, okafor).find((t) => t.startsWith('Handover from Kim (Ramp Agent) to Okafor (Ramp Lead): 1 open Task.'))!;
    expect(brief).toContain(`- ${tag.task_id} remove at T5 CARGO F2 (REMOVE), reported, Escalation level 0:`);
    expect(brief).toContain('Report: done by Kim ("in the FOD bin").');
  });

  it('declined: nothing moves and the first person is told', () => {
    const { d, okafor, reyes, hold } = t5();
    d.command(okafor, '/handover reyes');
    const id = d.inbox(reyes).pending_proposals[0]!.proposal_id;
    expect(d.command(reyes, `n ${id}`).lines[0]).toBe(`Declined (${id}): no Task moved. Okafor has been told.`);
    expect(texts(d, okafor).at(-1)).toBe(`Reyes declined your Handover (${id}). Your Tasks stay with you. You are still on shift.`);
    expect(d.inbox(okafor).tasks.find((t) => t.task_id === hold.task_id)?.assignee_id).toBe('okafor');
    expect(shiftOf(d, 'okafor')).toBe('on');
    expect(events(d)).toContain('handover_declined');
    expect(events(d)).not.toContain('handover');
    expect(d.board().timers.some((t) => t.kind === 'handover_timeout')).toBe(false);
  });

  it('no answer before the proposal expires: nothing moves and the first person is told once', () => {
    const { d, advance, okafor, reyes, hold } = t5();
    d.command(okafor, '/handover reyes');
    const id = d.inbox(reyes).pending_proposals[0]!.proposal_id;
    advance(17 + 119);
    expect(texts(d, okafor).some((t) => t.includes('did not answer'))).toBe(false);
    advance(17 + 121);
    const told = texts(d, okafor).filter((t) => t === `Reyes did not answer your Handover (${id}). Your Tasks stay with you. You are still on shift.`);
    expect(told).toHaveLength(1);
    expect(d.inbox(reyes).pending_proposals).toHaveLength(0);
    expect(refusal(() => d.command(reyes, `y ${id}`)).code).toBe('nothing_to_answer');
    expect(d.inbox(okafor).tasks.find((t) => t.task_id === hold.task_id)?.assignee_id).toBe('okafor');
    expect(shiftOf(d, 'okafor')).toBe('on');
    expect(events(d)).toContain('handover_expired');
    advance(17 + 200);
    expect(texts(d, okafor).filter((t) => t.includes('did not answer'))).toHaveLength(1);
  });

  it('is refused for a role that cannot take a Task, for someone off shift and with nothing to hand over', () => {
    const { d, kim, okafor, reyes, dana, hold } = t5();
    const role = refusal(() => d.command(okafor, '/handover kim'));
    expect(role).toEqual({
      code: 'role_not_allowed',
      message: `Handover refused: Kim is a Ramp Agent and cannot take ${hold.task_id} (ack hold): a Ramp Lead is required. Your Tasks stay with you.`,
    });
    expect(texts(d, okafor).at(-1)).toBe(`Refused (role_not_allowed): ${role.message}`);
    expect(d.inbox(kim).pending_proposals).toHaveLength(0);

    expect(refusal(() => d.command(reyes, '/handover okafor')).code).toBe('nothing_to_hand_over');
    expect(refusal(() => d.command(dana, '/handover okafor')).code).toBe('role_not_allowed');
    expect(refusal(() => d.command(okafor, '/handover okafor')).code).toBe('invalid_command');

    // Reyes goes off shift: Okafor is now the only Ramp Lead, with a HOLD open at his Gates.
    d.command(dana, '/shift reyes off');
    const off = refusal(() => d.command(okafor, '/handover reyes'));
    expect(off).toEqual({
      code: 'refused',
      message: 'Handover refused: Reyes is not on shift (off). Your Tasks stay with you. The supervisor has been told that no other Ramp Lead is on shift.',
    });
    expect(texts(d, dana).at(-1)).toBe(
      'Okafor is the only Ramp Lead on shift and tried to hand over to Reyes, which was refused, while a HOLD is open (F1 at T5). Nothing has moved. A Ramp Lead is needed: /shift <person> on.',
    );
    expect(d.activity().entries.find((e) => e.event === 'sole_lead_leaving')?.data).toMatchObject({ person_id: 'okafor', holds: [hold.task_id] });
    expect(d.inbox(okafor).tasks.find((t) => t.task_id === hold.task_id)?.assignee_id).toBe('okafor');
    expect(events(d)).not.toContain('handover_requested');
  });
});

describe('mock dispatcher: break and back', () => {
  it('refuses a break while the person holds an open HOLD Task, and tells the supervisor when they are the only Ramp Lead', () => {
    const { d, okafor, dana, hold } = t5();
    const first = refusal(() => d.command(okafor, '/break'));
    expect(first).toEqual({ code: 'open_hold', message: `You hold an open HOLD Task (${hold.task_id}). Hand it over first: /handover <person>` });
    expect(texts(d, okafor).at(-1)).toBe(`Refused (open_hold): ${first.message}`);
    expect(shiftOf(d, 'okafor')).toBe('on');
    expect(events(d)).not.toContain('sole_lead_leaving');

    d.command(dana, '/shift reyes off');
    const sole = refusal(() => d.command(okafor, '/break'));
    expect(sole.code).toBe('open_hold');
    expect(sole.message).toContain('The supervisor has been told that no other Ramp Lead is on shift.');
    expect(texts(d, dana).at(-1)).toContain('Okafor is the only Ramp Lead on shift and tried to go on a break while a HOLD is open (F1 at T5).');
    expect(shiftOf(d, 'okafor')).toBe('on');
  });

  it('goes on a break and comes back, logging each Shift change', () => {
    const { d, kim, dana } = t5();
    expect(d.command(kim, '/break').lines[0]).toBe('You are on a break. No new Tasks will come to you. Type /back when you return. You still hold 1 open Task.');
    expect(d.inbox(kim).person.shift).toBe('break');
    expect(d.command(kim, '/back').lines[0]).toBe('You are back on shift.');
    expect(d.inbox(kim).person.shift).toBe('on');
    d.command(dana, '/shift kim off');
    const changes = d.activity().entries.filter((e) => e.event === 'shift_changed');
    expect(changes.map((e) => [e.actor, e.data.person_id, e.data.shift])).toEqual([
      ['kim', 'kim', 'break'],
      ['kim', 'kim', 'on'],
      ['dana', 'kim', 'off'],
    ]);
    expect(changes[0]!.text).toBe('Kim (Ramp Agent) went on a break.');
  });
});

describe('mock dispatcher: still there', () => {
  /** T1 at 1:01: the box cutter at NOSE has no clean "after" frame. */
  function cutter() {
    const s = setup(60);
    const reyes = s.join('reyes', '4444');
    const patel = s.join('patel', '3333');
    const dana = s.join('dana', '9999');
    s.advance(61);
    const hold = s.d.inbox(reyes).tasks.find((t) => t.gate === 'T1' && t.angle === 'NOSE' && t.type === 'ack_hold')!;
    return { ...s, reyes, patel, dana, hold, label: hold.finding_id! };
  }

  it('re-opens the removal Task, tells its holder, raises the HOLD and says who else could be sent', () => {
    const { d, reyes, patel, dana, hold, label } = cutter();
    d.command(reyes, `/ack ${label}`);
    d.command(reyes, `/send patel ${label}`);
    const removal = d.inbox(patel).tasks.find((t) => t.type === 'remove' && t.finding_id === label)!;
    d.command(patel, `/done ${removal.task_id}`);
    expect(d.inbox(patel).tasks.find((t) => t.task_id === removal.task_id)?.status).toBe('reported');
    expect(d.inbox(patel).pending_proposals).toHaveLength(0);

    const out = d.command(reyes, `/removed ${label}`);
    expect(out.lines).toEqual([
      `The new photo of T1 NOSE still shows the object. ${label} stays open (HOLD); nothing was recorded.`,
      `${label} is at Escalation level 1; the people for that level have been told.`,
      `${removal.task_id} (remove) is open again with Patel. To send someone else: /reassign ${removal.task_id} <person>. On shift and able: Reyes.`,
    ]);
    const reopened = d.inbox(patel).tasks.find((t) => t.task_id === removal.task_id)!;
    expect(reopened.status).toBe('assigned');
    expect(reopened.inspection_finding_id).toBeTruthy();
    expect(reopened.inspection_finding_id).not.toBe(removal.inspection_finding_id);
    expect(texts(d, patel).at(-1)).toBe(`The new photo of T1 NOSE still shows the object for ${label}. ${removal.task_id} is open again: please go back and report here.`);
    expect(timersOf(d, removal.task_id).map((t) => t.kind).sort()).toEqual(['no_report_ask', 'no_report_offer']);
    expect(d.activity().entries.find((e) => e.event === 'task_reopened')?.data).toMatchObject({ task_id: removal.task_id, to: 'patel' });
    expect(d.inbox(reyes).tasks.find((t) => t.task_id === hold.task_id)).toMatchObject({ status: 'accepted', escalation_level: 1 });
    expect(confirmations(d).filter((e) => e.data.action === 'removed')).toHaveLength(0);

    // Again: level 2, every Ramp Lead and the supervisor. A third time: already at the top, and they are told again.
    const level2 = () => texts(d, dana).filter((t) => t.startsWith(`Escalation level 2: HOLD ${label} at T1 NOSE`) && t.includes('still shows the object')).length;
    expect(d.command(reyes, `/removed ${label}`).lines[1]).toBe(`${label} is at Escalation level 2; the people for that level have been told.`);
    expect(level2()).toBe(1);
    expect(d.command(reyes, `/removed ${label}`).lines[1]).toBe(`${label} is at Escalation level 2; the people for that level have been told.`);
    expect(level2()).toBe(2);
    expect(d.inbox(reyes).tasks.find((t) => t.task_id === hold.task_id)?.escalation_level).toBe(2);
  });

  it('with nobody assigned to remove it, says how to send someone', () => {
    const { d, reyes, label } = cutter();
    d.command(reyes, `/ack ${label}`);
    const out = d.command(reyes, `/removed ${label}`);
    expect(out.lines.at(-1)).toBe(`Nobody is assigned to remove it. To send someone: /send <person> ${label}. On shift and able: Patel.`);
  });
});

describe('mock dispatcher: an unusable Angle near pushback', () => {
  it('raises the check-by-eye Task to Escalation level 2 when scheduled pushback is under 2 minutes away', () => {
    const { d, advance, join } = setup();
    const reyes = join('reyes', '4444');
    const dana = join('dana', '9999');
    advance(40);
    const eye = d.inbox(reyes).tasks.filter((t) => t.type === 'check_by_eye' && t.gate === 'T2');
    expect(eye.map((t) => t.angle).sort()).toEqual(['CARGO', 'ENG-R']);
    // T2 pushes back at 250 s; the mock's gate clock runs 6 times faster, so 2 gate minutes is 20 demo seconds.
    for (const t of eye) expect(timersOf(d, t.task_id).find((x) => x.kind === 'unusable_pushback')?.fire_t).toBe(230);
    advance(229);
    expect(d.inbox(reyes).tasks.filter((t) => t.type === 'check_by_eye').every((t) => t.escalation_level === 0)).toBe(true);
    advance(231);
    const after = d.inbox(reyes).tasks.filter((t) => t.type === 'check_by_eye' && t.gate === 'T2');
    expect(after.map((t) => [t.status, t.escalation_level])).toEqual([
      ['assigned', 2],
      ['assigned', 2],
    ]);
    expect(texts(d, dana).some((t) => t.includes('ENG-R is still unusable and unchecked with scheduled pushback under 2 min'))).toBe(true);
    expect(texts(d, reyes).some((t) => /^Escalation level 2: K-\d+ \(check by eye at T2 CARGO\): CARGO is still unusable/.test(t))).toBe(true);
  });

  it('sets no such timer once the Angle is checked by eye', () => {
    const { d, advance, join } = setup();
    const reyes = join('reyes', '4444');
    advance(40);
    d.command(reyes, '/eye T2 CARGO');
    const cargo = d.board().tasks.find((t) => t.type === 'check_by_eye' && t.gate === 'T2' && t.angle === 'CARGO')!;
    expect(cargo.status).toBe('closed');
    expect(timersOf(d, cargo.task_id)).toHaveLength(0);
    advance(231);
    expect(boardTask(d, cargo.task_id).escalation_level).toBe(0);
  });
});
