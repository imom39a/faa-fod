import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import { normaliseTurnRecord } from '../lib/turnRecord';
import { MockBackend } from './backend';
import { MockDispatcher } from './dispatch';
import { buildMockTurnRecord } from './turnRecord';

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

const kinds = (r: { entries: { kind: string }[] }) => new Set(r.entries.map((e) => e.kind));

describe('mock Turn record', () => {
  it('has an Inspection, a Task, a Report and a Confirmation at load', () => {
    const { backend, d } = setup();
    const r = buildMockTurnRecord(backend, d, 'T5-DL1776');
    expect(r).toMatchObject({ turn_id: 'T5-DL1776', gate: 'T5', flight: 'DL1776' });
    expect([...kinds(r)].sort()).toEqual(['confirmation', 'inspection', 'report', 'task']);
    // The Task and Reports before the dispatcher started are marked as sample entries; the Confirmation is the real one.
    const signoff = r.entries.find((e) => e.kind === 'confirmation')!;
    expect(signoff).toMatchObject({ event: 'signoff', person: { name: 'T. Alvarez (scripted)', role: 'ramp_lead' } });
    expect(signoff.data.sample).toBeUndefined();
    const said = r.entries.find((e) => e.kind === 'report' && e.event === 'done')!;
    expect(said.data).toMatchObject({ via: 'agent', sample: true });
    expect(typeof said.data.raw_text).toBe('string');
    // In time order, numbered 0..n-1, and unchanged by the client's normaliser.
    expect(r.entries.map((e) => e.seq)).toEqual(r.entries.map((_, i) => i));
    const times = r.entries.map((e) => Date.parse(e.at));
    expect(times).toEqual([...times].sort((a, b) => a - b));
    expect(normaliseTurnRecord(structuredClone(r))).toEqual(r);
  });

  it('is 404 for an unknown Turn', () => {
    const { backend, d } = setup();
    try {
      buildMockTurnRecord(backend, d, 'T9-NOPE');
      expect.unreachable();
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).code).toBe('not_found');
      expect((e as ApiError).status).toBe(404);
    }
  });

  it('records the T5 HOLD story: Tasks, a free-text Report and Confirmations, kept apart', () => {
    const { d, backend, advance, join } = setup();
    const kim = join('kim', '1111');
    const okafor = join('okafor', '2222');
    advance(17);
    advance(48);
    d.command(okafor, '/ack F1');
    d.say(kim, 'got the hammer, its in the fod bin. bag tag picked up too');
    d.drainWakes();
    const proposal = d.inbox(kim).pending_proposals[0]!;
    d.command(kim, `y ${proposal.proposal_id}`);

    const before = JSON.stringify(d.board().tasks);
    const r = buildMockTurnRecord(backend, d, 'T5-DL1776');
    // Building the record changes nothing.
    expect(JSON.stringify(d.board().tasks)).toBe(before);

    const ev = (kind: string) => r.entries.filter((e) => e.kind === kind && !e.data.sample).map((e) => e.event);
    expect(ev('inspection')).toEqual(expect.arrayContaining(['started', 'completed']));
    expect(ev('task')).toEqual(expect.arrayContaining(['assigned', 'escalated', 'closed']));
    expect(ev('confirmation')).toEqual(expect.arrayContaining(['acknowledged', 'removed']));

    // The Report is what Kim said, with her words; the Confirmation is what was recorded.
    const report = r.entries.find((e) => e.kind === 'report' && e.event === 'done' && !e.data.sample)!;
    expect(report.person).toEqual({ person_id: 'kim', name: 'Kim', role: 'ramp_agent' });
    expect(report.data).toMatchObject({ raw_text: 'got the hammer, its in the fod bin. bag tag picked up too', via: 'agent' });
    const ack = r.entries.find((e) => e.kind === 'confirmation' && e.event === 'acknowledged')!;
    expect(ack).toMatchObject({ person: { person_id: 'okafor', role: 'ramp_lead' }, refs: { finding_id: 'F1' } });
    expect(r.entries.filter((e) => e.kind === 'report').every((e) => !('action' in e.data))).toBe(true);

    const escalated = r.entries.find((e) => e.kind === 'task' && e.event === 'escalated')!;
    expect(escalated.data.level).toBe(1);
    expect(escalated.refs.task_id).toMatch(/^K-/);

    // Time order, the HOLD Inspection before its Task.
    const firstTask = r.entries.findIndex((e) => e.kind === 'task' && !e.data.sample);
    const holdInspection = r.entries.findIndex((e) => e.kind === 'inspection' && e.event === 'completed' && e.data.inspection_kind === 'pre_departure');
    expect(holdInspection).toBeGreaterThanOrEqual(0);
    expect(holdInspection).toBeLessThan(firstTask);
    expect(r.cost.agent_usd).toBeGreaterThan(0);
    expect(r.cost.total_usd).toBeCloseTo(r.cost.inspections_usd + r.cost.agent_usd, 6);
  });

  it('puts a Confirmation at the time it was recorded, even when the page starts mid-demo', () => {
    // With ?t=120 the dispatcher sees every earlier event at once, at t=120.
    const { backend, d } = setup(120);
    const r = buildMockTurnRecord(backend, d, 'T1-DL1432');
    const brief = r.entries.map((e) => `${e.kind}:${e.event}:${e.refs.inspection_id ?? ''}`);
    const signoff = r.entries.find((e) => e.kind === 'confirmation' && e.event === 'signoff')!;
    expect(signoff.t).toBeLessThan(120);
    expect(brief.indexOf('confirmation:signoff:insp-004')).toBeLessThan(brief.indexOf('inspection:started:insp-009'));
    expect(r.entries.map((e) => e.at)).toEqual([...r.entries.map((e) => e.at)].sort());
  });
});
