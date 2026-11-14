import { describe, expect, it } from 'vitest';
import type { GateState, QueueItem } from '../api/types';
import { formatPushback, isAbnormal, overviewCounts, queueRows, shortPushback, stripLabel, tileModel, type Tone } from './gates';

function gate(over: Partial<GateState> = {}, minutes: number | null = 30): GateState {
  return {
    gate: 'T1',
    status: 'awaiting_confirmation',
    verdict: 'FINDINGS',
    highest_open_severity: null,
    turn: {
      turn_id: 'T1-DL1432',
      flight: 'DL1432',
      aircraft_type: 'A321',
      phase: 'pre_departure',
      minutes_to_pushback: minutes,
      latest_inspection_id: 'insp-001',
    },
    ...over,
  };
}

describe('tileModel', () => {
  it('shows the Verdict beneath an awaiting-Confirmation status and marks it advisory', () => {
    const m = tileModel(gate({ verdict: 'ALL_CLEAR' }));
    expect(m.statusLabel).toBe('Awaiting Confirmation');
    expect(m.verdictLabel).toBe('ALL CLEAR');
    expect(m.advisory).toBe(true);
    expect(m.humanConfirmed).toBe(false);
    expect(m.tone).toBe('clear');
  });

  it('only a human-confirmed Gate shows as confirmed clear, with no advisory mark', () => {
    const m = tileModel(gate({ status: 'confirmed_clear', verdict: 'ALL_CLEAR' }));
    expect(m.statusLabel).toBe('Confirmed clear');
    expect(m.advisory).toBe(false);
    expect(m.humanConfirmed).toBe(true);
    expect(m.tone).toBe('confirmed');
  });

  it('shows a HOLD even when the Verdict is INCOMPLETE', () => {
    const m = tileModel(gate({ verdict: 'INCOMPLETE', highest_open_severity: 'HOLD' }));
    expect(m.verdictLabel).toBe('INCOMPLETE');
    expect(m.severity).toBe('HOLD');
    expect(m.tone).toBe('hold');
  });

  it('uses the highest open severity for the tone, then the Verdict', () => {
    expect(tileModel(gate({ highest_open_severity: 'REMOVE' })).tone).toBe('remove');
    expect(tileModel(gate({ highest_open_severity: 'ADVISORY' })).tone).toBe('advisory');
    expect(tileModel(gate({ verdict: 'INCOMPLETE' })).tone).toBe('incomplete');
    expect(tileModel(gate({ verdict: 'FINDINGS' })).tone).toBe('await');
  });

  it('marks an Inspection in progress as advisory with no Verdict yet', () => {
    const m = tileModel(gate({ status: 'inspecting', verdict: null }));
    expect(m.statusLabel).toBe('Inspecting');
    expect(m.verdictLabel).toBeNull();
    expect(m.advisory).toBe(true);
    expect(m.tone).toBe('busy');
  });

  it('covers every Gate status with a label and no advisory mark where there is no Verdict', () => {
    const labels = (['idle', 'awaiting_pre_arrival', 'on_stand', 'departed'] as const).map((status) => {
      const m = tileModel(gate({ status, verdict: null }));
      expect(m.advisory).toBe(false);
      expect(m.verdictLabel).toBeNull();
      return m.statusLabel;
    });
    expect(labels).toEqual(['Idle', 'Awaiting pre-arrival', 'Aircraft on stand', 'Departed']);
  });

  it('renders an idle Gate with no Turn', () => {
    const m = tileModel({ gate: 'T4', status: 'idle', verdict: null, highest_open_severity: null, turn: null });
    expect(m.flight).toBeNull();
    expect(m.turnId).toBeNull();
    expect(m.pushbackText).toBeNull();
    expect(m.tone).toBe('idle');
  });

  it('shows flight, aircraft type and minutes to pushback', () => {
    const m = tileModel(gate({}, 34));
    expect(m.flight).toBe('DL1432');
    expect(m.aircraftType).toBe('A321');
    expect(m.pushbackText).toBe('34 min to pushback');
    expect(m.pushbackOverdue).toBe(false);
    expect(tileModel(gate({}, -3)).pushbackOverdue).toBe(true);
    expect(tileModel(gate({ status: 'departed', verdict: null }, null)).pushbackText).toBeNull();
  });
});

describe('formatPushback', () => {
  it('formats future, due, past and unknown times', () => {
    expect(formatPushback(12.4)).toBe('12 min to pushback');
    expect(formatPushback(0)).toBe('Pushback due');
    expect(formatPushback(-5)).toBe('5 min past scheduled pushback');
    expect(formatPushback(null)).toBeNull();
  });
});

describe('queueRows', () => {
  const item = (over: Partial<QueueItem>): QueueItem => ({
    gate: 'T1',
    turn_id: 'T1-DL1432',
    inspection_id: 'insp-001',
    reason: 'findings',
    severity: 'REMOVE',
    minutes_to_pushback: 20,
    text: '2 open Findings',
    ...over,
  });

  it('keeps exactly the order the API gives', () => {
    const queue = [
      item({ gate: 'T5', reason: 'hold', severity: 'HOLD', minutes_to_pushback: 40, inspection_id: 'a' }),
      item({ gate: 'T2', reason: 'incomplete', severity: null, minutes_to_pushback: 9, inspection_id: 'b' }),
      item({ gate: 'T8', reason: 'signoff', severity: null, minutes_to_pushback: 3, inspection_id: 'c' }),
      item({ gate: 'T1', reason: 'findings', minutes_to_pushback: 25, inspection_id: 'd' }),
    ];
    expect(queueRows(queue).map((r) => r.gate)).toEqual(['T5', 'T2', 'T8', 'T1']);
  });

  it('gives each reason a text label and tone, so colour is not the only signal', () => {
    const rows = queueRows([
      item({ reason: 'hold', severity: 'HOLD' }),
      item({ reason: 'findings', severity: 'ADVISORY', inspection_id: 'x' }),
      item({ reason: 'incomplete', severity: null, inspection_id: 'y' }),
      item({ reason: 'signoff', severity: null, minutes_to_pushback: null, inspection_id: 'z' }),
    ]);
    expect(rows.map((r) => r.reasonLabel)).toEqual(['HOLD', 'Findings to confirm', 'INCOMPLETE', 'Ready for sign-off']);
    expect(rows.map((r) => r.tone)).toEqual(['hold', 'advisory', 'incomplete', 'await']);
    expect(rows[3]?.pushbackText).toBeNull();
    expect(new Set(rows.map((r) => r.key)).size).toBe(4);
  });
});

describe('calm display helpers', () => {
  it('treats only the severities and INCOMPLETE as abnormal', () => {
    const abnormal: Tone[] = ['hold', 'remove', 'advisory', 'incomplete'];
    const normal: Tone[] = ['idle', 'waiting', 'busy', 'onstand', 'clear', 'await', 'confirmed'];
    expect(abnormal.every(isAbnormal)).toBe(true);
    expect(normal.some(isAbnormal)).toBe(false);
  });

  it('shortens the pushback countdown and flags an overdue one', () => {
    expect(shortPushback(gate({}, 34.4))).toEqual({ text: '34 min', overdue: false });
    expect(shortPushback(gate({}, 0))).toEqual({ text: 'due now', overdue: true });
    expect(shortPushback(gate({}, -5))).toEqual({ text: '+5 min late', overdue: true });
    expect(shortPushback(gate({}, null))).toBeNull();
    expect(shortPushback(gate({ status: 'idle' }))).toBeNull();
  });

  it('puts an open severity before the Verdict, and an unconfirmed Verdict before the status', () => {
    expect(stripLabel(tileModel(gate({ highest_open_severity: 'HOLD' })))).toBe('HOLD open');
    expect(stripLabel(tileModel(gate({ verdict: 'ALL_CLEAR' })))).toBe('ALL CLEAR, unconfirmed');
    expect(stripLabel(tileModel(gate({ status: 'confirmed_clear', verdict: 'ALL_CLEAR' })))).toBe('Confirmed clear');
    expect(stripLabel(tileModel(gate({ status: 'inspecting', verdict: null })))).toBe('Inspecting');
  });

  it('counts the queue by reason and the Gates confirmed clear', () => {
    const q = (reason: QueueItem['reason']): QueueItem => ({
      gate: 'T1',
      turn_id: 't',
      inspection_id: 'i',
      reason,
      severity: null,
      minutes_to_pushback: 10,
      text: '',
    });
    const counts = overviewCounts([gate({ status: 'confirmed_clear' }), gate()], [q('hold'), q('hold'), q('signoff')]);
    expect(counts.map((c) => [c.key, c.n])).toEqual([
      ['hold', 2],
      ['findings', 0],
      ['incomplete', 0],
      ['signoff', 1],
      ['confirmed', 1],
    ]);
    expect(counts.find((c) => c.key === 'confirmed')?.calm).toBe(true);
  });
});
