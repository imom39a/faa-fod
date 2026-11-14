import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import type { Person, Report } from '../api/types';
import { buildTimeline, canSignOff, holdRemovalOutcome, inspectionRecords, signoffBlockers, supersededIds } from '../lib/report';
import { MockBackend } from './backend';

const AGENT: Person = { role: 'ramp_agent', name: 'R. Ortiz' };
const LEAD: Person = { role: 'ramp_lead', name: 'K. Bauer' };

function codeOf(fn: () => unknown): string {
  try {
    fn();
  } catch (e) {
    if (e instanceof ApiError) return e.code;
    throw e;
  }
  return 'no_error';
}

function latest(b: MockBackend, gate: string): Report {
  const g = b.getState().gates.find((x) => x.gate === gate);
  if (!g?.turn?.latest_inspection_id) throw new Error(`no Inspection at ${gate}`);
  return b.getInspection(g.turn.latest_inspection_id);
}

const statuses = (b: MockBackend) => Object.fromEntries(b.getState().gates.map((g) => [g.gate, g.status]));

describe('mock backend: demo clock and Gate status', () => {
  it('always returns the 5 Gates in contract order and starts paused', () => {
    const s = new MockBackend().getState();
    expect(s.gates.map((g) => g.gate)).toEqual(['T1', 'T2', 'T4', 'T5', 'T8']);
    expect(s.demo).toMatchObject({ playing: false, speed: 1, t: 0 });
  });

  it('reaches every Gate status over the scripted demo', () => {
    const seen = new Set<string>();
    const b = new MockBackend();
    for (let t = 0; t <= 200; t += 1) {
      b.advanceTo(t);
      Object.values(statuses(b)).forEach((s) => seen.add(s));
    }
    expect([...seen].sort()).toEqual(
      ['awaiting_confirmation', 'awaiting_pre_arrival', 'confirmed_clear', 'departed', 'idle', 'inspecting', 'on_stand'].sort(),
    );
  });

  it('moves the clock only while playing, at the chosen speed, and resets', () => {
    const b = new MockBackend();
    b.tick(5);
    expect(b.getState().demo.t).toBe(0);
    b.setSpeed(10);
    b.play();
    b.tick(2);
    expect(b.getState().demo.t).toBe(20);
    b.pause();
    b.tick(2);
    expect(b.getState().demo.t).toBe(20);
    expect(codeOf(() => b.setSpeed(3))).toBe('invalid_speed');
    expect(b.reset().demo).toMatchObject({ t: 0, playing: false });
  });

  it('holds pushback until the pre-departure Inspection is signed off', () => {
    const b = new MockBackend({ startAt: 360 });
    expect(statuses(b).T1).toBe('awaiting_confirmation');
    expect(b.getState().gates[0]?.turn?.minutes_to_pushback).toBeLessThan(0);
    expect(statuses(new MockBackend({ startAt: 168 })).T8).toBe('idle');
  });
});

describe('mock backend: queue', () => {
  it('lists HOLDs first, then by minutes to pushback ascending', () => {
    const q = new MockBackend({ startAt: 110 }).getState().queue;
    // Two HOLDs are open at 1:50: T5 (earlier pushback) and T1.
    expect(q.slice(0, 2).map((x) => [x.gate, x.reason])).toEqual([['T5', 'hold'], ['T1', 'hold']]);
    const rest = q.slice(2).map((x) => x.minutes_to_pushback ?? Infinity);
    expect(q.slice(2).every((x) => x.reason !== 'hold')).toBe(true);
    expect(rest).toEqual([...rest].sort((a, b) => a - b));
    expect(q.map((x) => x.reason)).toEqual(expect.arrayContaining(['hold', 'findings', 'incomplete']));
  });
});

describe('mock backend: HOLD Confirmation', () => {
  const setup = () => {
    const b = new MockBackend({ startAt: 60 });
    const report = latest(b, 'T1');
    const hold = (angle: string) => report.findings.find((f) => f.severity === 'HOLD' && f.angle === angle)!;
    return { b, report, bolt: hold('ENG-L'), cutter: hold('NOSE') };
  };

  it('refuses a Ramp Agent on a HOLD', () => {
    const { b, report, bolt } = setup();
    expect(report.verdict).toBe('FINDINGS');
    expect(report.highest_open_severity).toBe('HOLD');
    for (const outcome of ['acknowledged', 'removed', 'false_alarm'] as const) {
      expect(codeOf(() => b.confirmFinding(report.inspection_id, bolt.finding_id, { ...AGENT, outcome }))).toBe('role_not_allowed');
    }
  });

  it('needs an acknowledge before removed', () => {
    const { b, report, bolt } = setup();
    expect(codeOf(() => b.confirmFinding(report.inspection_id, bolt.finding_id, { ...LEAD, outcome: 'removed' }))).toBe(
      'hold_needs_acknowledge',
    );
  });

  it('clears the HOLD when the re-inspection frame is clean, and keeps the record', () => {
    const { b, report, bolt } = setup();
    const acked = b.confirmFinding(report.inspection_id, bolt.finding_id, { ...LEAD, outcome: 'acknowledged' });
    expect(acked.findings.find((f) => f.finding_id === bolt.finding_id)?.status).toBe('acknowledged');
    const next = b.confirmFinding(report.inspection_id, bolt.finding_id, { ...LEAD, outcome: 'removed' });
    expect(next.inspection_id).not.toBe(report.inspection_id);
    expect(next).toMatchObject({ kind: 'on_demand', parent_inspection_id: report.inspection_id });
    expect(holdRemovalOutcome(bolt, next)).toBe('cleared');
    const carried = next.findings.find((f) => f.finding_id === bolt.finding_id);
    expect(carried?.confirmation).toMatchObject({ outcome: 'removed', confirmed_by: LEAD });
    expect(carried?.confirmation?.after_photo_ref).toBeTruthy();
    // Other Angles and their Findings are inherited.
    expect(next.findings.length).toBe(report.findings.length);
    expect(next.angles.find((a) => a.angle === 'CARGO')?.source_inspection_id).toBe(report.inspection_id);
    expect(next.angles.find((a) => a.angle === 'ENG-L')?.source_inspection_id).toBe(next.inspection_id);
    const turn = b.getTurn(report.turn_id);
    expect(supersededIds(turn.inspections).has(report.inspection_id)).toBe(true);
    expect(inspectionRecords(next).map((r) => r.text)).toEqual([expect.stringContaining('Removed')]);
  });

  it('keeps the HOLD open when the item is still there', () => {
    const { b, report, cutter } = setup();
    b.confirmFinding(report.inspection_id, cutter.finding_id, { ...LEAD, outcome: 'acknowledged' });
    const next = b.confirmFinding(report.inspection_id, cutter.finding_id, { ...LEAD, outcome: 'removed' });
    expect(holdRemovalOutcome(cutter, next)).toBe('still_there');
    expect(next.highest_open_severity).toBe('HOLD');
    expect(next.findings.filter((f) => f.angle === 'NOSE' && f.confirmation === null)).toHaveLength(1);
  });

  it('keeps a Finding that is found again acknowledged, so "removed" can be recorded again', () => {
    const { b, report, cutter } = setup();
    b.confirmFinding(report.inspection_id, cutter.finding_id, { ...LEAD, outcome: 'acknowledged' });
    const next = b.confirmFinding(report.inspection_id, cutter.finding_id, { ...LEAD, outcome: 'removed' });
    const again = next.findings.find((f) => f.angle === 'NOSE' && f.confirmation === null)!;
    expect(again.finding_id).not.toBe(cutter.finding_id);
    expect(again.status).toBe('acknowledged');
    const third = b.confirmFinding(next.inspection_id, again.finding_id, { ...LEAD, outcome: 'removed' });
    expect(third.highest_open_severity).toBe('HOLD');
  });

  it('never drops an open Finding on a re-inspection: a clean new photo is not a Confirmation', () => {
    const { b, report, bolt } = setup();
    // The ENG-L re-inspection frame is clean. Nobody has confirmed anything.
    const next = b.reinspectAngle(report.inspection_id, 'ENG-L', AGENT);
    const carried = next.findings.find((f) => f.finding_id === bolt.finding_id);
    expect(carried).toMatchObject({ status: 'open', confirmation: null, carried_from_inspection_id: report.inspection_id });
    expect(next.highest_open_severity).toBe('HOLD');
    expect(canSignOff(next)).toBe(false);
    // The Ramp Lead's two steps still close it, on the newest Inspection.
    b.confirmFinding(next.inspection_id, bolt.finding_id, { ...LEAD, outcome: 'acknowledged' });
    const cleared = b.confirmFinding(next.inspection_id, bolt.finding_id, { ...LEAD, outcome: 'removed' });
    expect(cleared.findings.filter((f) => f.finding_id === bolt.finding_id)).toHaveLength(1);
    expect(cleared.findings.find((f) => f.finding_id === bolt.finding_id)?.confirmation).toMatchObject({ outcome: 'removed', confirmed_by: LEAD });
  });

  it('accepts a false alarm on a HOLD without a re-inspection, but needs a reason', () => {
    const { b, report, cutter } = setup();
    expect(codeOf(() => b.confirmFinding(report.inspection_id, cutter.finding_id, { ...LEAD, outcome: 'false_alarm' }))).toBe(
      'false_alarm_reason_required',
    );
    const same = b.confirmFinding(report.inspection_id, cutter.finding_id, { ...LEAD, outcome: 'false_alarm', false_alarm_reason: 'marking' });
    expect(same.inspection_id).toBe(report.inspection_id);
    expect(same.findings.find((f) => f.finding_id === cutter.finding_id)?.confirmation?.false_alarm_reason).toBe('marking');
  });

  it('rejects actions on a superseded Inspection', () => {
    const { b, report, bolt } = setup();
    b.reinspectAngle(report.inspection_id, 'WIDE', AGENT);
    expect(codeOf(() => b.confirmFinding(report.inspection_id, bolt.finding_id, { ...LEAD, outcome: 'acknowledged' }))).toBe('superseded');
  });
});

describe('mock backend: confirm-all, checked by eye, sign-off', () => {
  it('confirm-all marks every open REMOVE/ADVISORY Finding removed and leaves HOLDs', () => {
    const b = new MockBackend({ startAt: 60 });
    const report = latest(b, 'T1');
    const after = b.confirmAll(report.inspection_id, AGENT);
    expect(after.findings.filter((f) => f.severity !== 'HOLD').every((f) => f.confirmation?.outcome === 'removed')).toBe(true);
    expect(after.findings.filter((f) => f.severity === 'HOLD').every((f) => f.status === 'open')).toBe(true);
    expect(codeOf(() => b.signoff(report.inspection_id, LEAD))).toBe('open_findings');
  });

  it('blocks sign-off on unusable Angles until re-inspected usable or checked by eye by a Ramp Lead', () => {
    const b = new MockBackend({ startAt: 60 });
    let report = latest(b, 'T2');
    expect(report.verdict).toBe('INCOMPLETE');
    expect(report.missing_angles).toEqual(['ENG-R', 'CARGO']);
    expect(signoffBlockers(report).unusableAngles.map((a) => a.angle)).toEqual(['ENG-R', 'CARGO']);
    expect(codeOf(() => b.signoff(report.inspection_id, LEAD))).toBe('unusable_angles');

    report = b.reinspectAngle(report.inspection_id, 'ENG-R', AGENT);
    expect(report.angles.find((a) => a.angle === 'ENG-R')?.status).toBe('usable');
    report = b.reinspectAngle(report.inspection_id, 'CARGO', AGENT);
    expect(report.angles.find((a) => a.angle === 'CARGO')).toMatchObject({ status: 'unusable', unusable_reason: 'glare' });

    expect(codeOf(() => b.checkedByEye(report.inspection_id, 'CARGO', AGENT))).toBe('role_not_allowed');
    expect(codeOf(() => b.checkedByEye(report.inspection_id, 'NOSE', LEAD))).toBe('angle_usable');
    report = b.checkedByEye(report.inspection_id, 'CARGO', LEAD);
    expect(report.angles.find((a) => a.angle === 'CARGO')?.checked_by_eye?.by).toEqual(LEAD);
    expect(canSignOff(report)).toBe(true);

    report = b.signoff(report.inspection_id, LEAD);
    expect(report).toMatchObject({ status: 'confirmed', inspection_signoff: { by: LEAD } });
    expect(b.getState().gates.find((g) => g.gate === 'T2')?.status).toBe('confirmed_clear');
    expect(b.getState().queue.some((q) => q.gate === 'T2')).toBe(false);
    expect(codeOf(() => b.signoff(report.inspection_id, LEAD))).toBe('already_signed_off');
  });

  it('routes an outside-boundary Finding to the airport and closes it once reported', () => {
    const b = new MockBackend({ startAt: 215 });
    const report = latest(b, 'T8');
    const outside = report.findings.find((f) => f.zone_tier === 'outside_boundary')!;
    expect(outside).toMatchObject({ responsible_party: 'airport', rule_id: 'FOD-R10', angle: 'WIDE' });
    expect(outside.rule.text).toContain('reported');
    const after = b.confirmFinding(report.inspection_id, outside.finding_id, { ...AGENT, outcome: 'removed', possible_source: 'Told Ramp 1 control' });
    expect(after.findings.find((f) => f.finding_id === outside.finding_id)?.confirmation?.possible_source).toBe('Told Ramp 1 control');
  });

  it('needs a name on every Confirmation', () => {
    const b = new MockBackend({ startAt: 60 });
    const report = latest(b, 'T5');
    expect(codeOf(() => b.confirmAll(report.inspection_id, { role: 'ramp_agent', name: '  ' }))).toBe('name_required');
  });

  it('stages GSE inside the equipment restraint line as a REMOVE under FOD-R9 at pre-arrival', () => {
    const b = new MockBackend({ startAt: 70 });
    const report = latest(b, 'T4');
    expect(report.kind).toBe('pre_arrival');
    expect(report.findings.find((f) => f.finding_type === 'equipment_staging')).toMatchObject({ severity: 'REMOVE', rule_id: 'FOD-R9', category: null });
    expect(report.observations[0]?.kind).toBe('spill');
    expect(report.dismissed_candidates.length).toBeGreaterThan(0);
  });
});

describe('timeline', () => {
  it('orders milestones and Inspections, and marks scheduled ones that have not run', () => {
    const b = new MockBackend({ startAt: 30 });
    const entries = buildTimeline(b.getTurn('T1-DL1432'), 30);
    expect(entries.map((e) => (e.type === 'inspection' ? e.report.kind : e.type === 'scheduled' ? `scheduled:${e.kind}` : e.key))).toEqual([
      'stand_prep',
      'pre_arrival',
      'block_in',
      'scheduled:pre_departure',
      'scheduled_pushback',
    ]);
    expect(entries.filter((e) => e.type === 'milestone').map((e) => e.done)).toEqual([true, true, false]);
  });

  it('runs a manual on-demand Inspection through inspecting to a Verdict', () => {
    const b = new MockBackend({ startAt: 60 });
    const started = b.inspectGate('T5', { kind: 'on_demand' });
    expect(started.status).toBe('inspecting');
    expect(b.getState().gates.find((g) => g.gate === 'T5')?.status).toBe('inspecting');
    b.completeInspection(started.inspection_id);
    expect(b.getInspection(started.inspection_id)).toMatchObject({ status: 'awaiting_confirmation', verdict: 'FINDINGS' });
    expect(codeOf(() => new MockBackend().inspectGate('T4', { kind: 'on_demand' }))).toBe('no_active_turn');
  });
});
