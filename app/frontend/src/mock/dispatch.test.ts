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

function codeOf(fn: () => unknown): string {
  try {
    fn();
  } catch (e) {
    if (e instanceof ApiError) return e.code;
    throw e;
  }
  return 'no_error';
}

const texts = (d: MockDispatcher, token: string) => d.inbox(token).messages.map((m) => m.text);

describe('mock dispatcher: sign-in', () => {
  it('lists the roster without PINs and checks the PIN', () => {
    const { d } = setup();
    const people = d.roster().people;
    expect(people.map((p) => p.person_id)).toEqual(['kim', 'patel', 'okafor', 'reyes', 'dana']);
    expect(JSON.stringify(people)).not.toContain('1111');
    expect(codeOf(() => d.join('kim', '0000'))).toBe('bad_credentials');
    expect(d.join('Kim', '1111').person).toMatchObject({ person_id: 'kim', role: 'ramp_agent', signed_in: true });
    expect(codeOf(() => d.inbox('nope'))).toBe('not_signed_in');
  });
});

describe('mock dispatcher: the T5 HOLD story', () => {
  it('runs from the Inspection to sign-off, with every Confirmation made by a person', () => {
    const { backend, d, advance, join } = setup();
    const kim = join('kim', '1111');
    const okafor = join('okafor', '2222');
    advance(17);

    // The HOLD goes to the Ramp Lead by code; the bag tag goes to the Ramp Agent.
    const hold = d.inbox(okafor).tasks.find((t) => t.gate === 'T5')!;
    expect(hold).toMatchObject({ type: 'ack_hold', severity: 'HOLD', finding_id: 'F1', angle: 'ENG-R', status: 'assigned', required_role: 'ramp_lead' });
    const tag = d.inbox(kim).tasks[0]!;
    expect(tag).toMatchObject({ type: 'remove', severity: 'REMOVE', finding_id: 'F2', angle: 'CARGO', gate: 'T5', turn_id: 'T5-DL1776' });

    // A Ramp Agent is refused on the HOLD, and the refusal is in their thread.
    expect(codeOf(() => d.command(kim, '/ack F1'))).toBe('role_not_allowed');
    expect(texts(d, kim).at(-1)).toMatch(/^Refused \(role_not_allowed\)/);

    // Not acknowledged after 30 s: second call to the lead, the supervisor is told.
    advance(48);
    expect(d.inbox(okafor).tasks.find((t) => t.task_id === hold.task_id)?.escalation_level).toBe(1);
    expect(texts(d, okafor).some((t) => t.startsWith('Second call: HOLD F1 at T5 ENG-R'))).toBe(true);
    expect(texts(d, join('dana', '9999')).some((t) => t.startsWith('Escalation level 1: HOLD F1'))).toBe(true);

    expect(d.command(okafor, '/ack F1').lines[0]).toBe('Recorded: F1 acknowledged by Okafor (Ramp Lead).');
    expect(d.inbox(okafor).tasks.find((t) => t.task_id === hold.task_id)?.status).toBe('accepted');

    // Free text is a Report: it changes the Task and produces a proposal, never a Confirmation.
    expect(d.say(kim, 'got the hammer, its in the fod bin. bag tag picked up too')).toMatchObject({ routed: 'agent' });
    d.drainWakes();
    const afterReport = d.inbox(kim);
    expect(afterReport.tasks[0]?.status).toBe('reported');
    expect(afterReport.pending_proposals).toHaveLength(1);
    expect(afterReport.pending_proposals[0]).toMatchObject({ kind: 'confirm', question: 'record F2 as removed', action: { label: 'F2', outcome: 'removed' } });
    expect(backend.getState().gates.find((g) => g.gate === 'T5')?.highest_open_severity).toBe('HOLD');
    expect(texts(d, okafor).at(-1)).toContain('That is a Report, not a Confirmation');
    const open = backend.getInspection(tag.inspection_id).findings.filter((f) => f.status !== 'confirmed');
    expect(open).toHaveLength(2);

    // Kim accepts the proposal: that is her Confirmation.
    const answer = d.command(kim, `y ${afterReport.pending_proposals[0]!.proposal_id}`);
    expect(answer.lines[0]).toBe('Recorded: F2 removed, confirmed by Kim (Ramp Agent).');
    expect(d.inbox(kim).tasks[0]).toMatchObject({ status: 'closed', close_reason: 'F2 removed, confirmed by Kim' });

    // Removed on the HOLD takes a new photo; it is clean, so the HOLD clears and sign-off is asked for.
    const pending = d.beginCommand(okafor, '/removed F1');
    expect(pending.reinspects).toBe(true);
    expect(texts(d, okafor).at(-1)).toBe('Re-inspecting T5 ENG-R ...');
    expect(d.finishCommand(pending).lines[0]).toBe('New photo of T5 ENG-R is clean. Recorded: F1 removed, confirmed by Okafor (Ramp Lead).');
    const signoff = d.inbox(okafor).tasks.find((t) => t.type === 'sign_off' && t.gate === 'T5');
    expect(signoff).toMatchObject({ status: 'assigned', severity: null, finding_id: null });
    expect(d.command(okafor, '/signoff T5').lines[0]).toBe('Inspection signed off by Okafor (Ramp Lead). T5 confirmed clear.');
    expect(d.inbox(okafor).tasks.filter((t) => t.gate === 'T5').every((t) => t.status === 'closed')).toBe(true);
    expect(backend.getState().gates.find((g) => g.gate === 'T5')?.status).toBe('confirmed_clear');

    // The activity log has every step, oldest first, with ids that only go up.
    const log = d.activity({ gate: 'T5' }).entries;
    const events = log.map((e) => e.event);
    for (const e of ['inspection_completed', 'task_assigned', 'hold_alert', 'agent_wake', 'task_escalated', 'confirmation', 'task_reported', 'proposal_created', 'proposal_answered', 'task_closed']) {
      expect(events).toContain(e);
    }
    expect(log.map((e) => e.id)).toEqual([...log.map((e) => e.id)].sort((a, b) => a - b));
    expect(d.activity().entries.some((e) => e.event === 'command_refused' && e.actor === 'kim')).toBe(true);
    expect(d.activity().cost.agent_session_usd).toBeGreaterThan(0);
    expect(d.activity({ after: d.activity().cursor }).entries).toHaveLength(0);
  });

  it('keeps the HOLD open and escalates when the new photo still shows the object', () => {
    const { d, advance, join } = setup(60);
    const reyes = join('reyes', '4444');
    advance(61);
    // T1: the box cutter at NOSE has no clean "after" frame.
    const cutter = d.inbox(reyes).tasks.find((t) => t.gate === 'T1' && t.angle === 'NOSE')!;
    d.command(reyes, `/ack ${cutter.finding_id}`);
    const out = d.command(reyes, `/removed ${cutter.finding_id}`);
    expect(out.lines[0]).toContain('still shows the object');
    const after = d.inbox(reyes).tasks.find((t) => t.task_id === cutter.task_id)!;
    expect(after.status).toBe('accepted');
    expect(after.escalation_level).toBeGreaterThanOrEqual(1);
  });

  it('expires a proposal, refuses the wrong person and keeps a supervisor out of Confirmations', () => {
    const { d, advance, join } = setup();
    const kim = join('kim', '1111');
    const dana = join('dana', '9999');
    advance(17);
    const tag = d.inbox(kim).tasks[0]!;
    expect(codeOf(() => d.command(dana, '/removed F2'))).toBe('role_not_allowed');
    expect(codeOf(() => d.command(join('patel', '3333'), `/done ${tag.task_id}`))).toBe('not_your_task');
    d.command(kim, `/done ${tag.task_id}`);
    expect(d.inbox(kim).pending_proposals).toHaveLength(1);
    advance(17 + 121);
    expect(d.inbox(kim).pending_proposals).toHaveLength(0);
    expect(codeOf(() => d.command(kim, 'y'))).toBe('nothing_to_answer');
    // A supervisor sees every Task.
    expect(d.inbox(dana).tasks.length).toBeGreaterThan(d.inbox(kim).tasks.length);
  });

  it('starts again on a demo reset', () => {
    const { backend, d, advance, join } = setup();
    const kim = join('kim', '1111');
    advance(17);
    const before = d.inbox(kim);
    expect(before.tasks).toHaveLength(1);
    backend.reset();
    d.step();
    const after = d.inbox(kim);
    expect(after.epoch).not.toBe(before.epoch);
    expect(after.tasks).toHaveLength(0);
    expect(after.messages).toHaveLength(0);
  });
});
