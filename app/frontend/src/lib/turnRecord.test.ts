import { describe, expect, it } from 'vitest';
import type { TurnRecord, TurnRecordEntry } from '../api/turnRecordTypes';
import { buildRecordDownload, entryKindLabel, normaliseTurnRecord, orderEntries } from './turnRecord';

function entry(over: Partial<TurnRecordEntry> & Pick<TurnRecordEntry, 'at'>): TurnRecordEntry {
  return {
    seq: 0,
    t: null,
    kind: 'task',
    event: 'assigned',
    person: null,
    text: '',
    refs: { inspection_id: null, task_id: null, finding_id: null, angle: null },
    data: {},
    ...over,
  };
}

describe('orderEntries', () => {
  it('puts entries in time order, across time zone offsets', () => {
    const list = [
      entry({ at: '2026-11-13T14:05:00Z', text: 'c' }),
      entry({ at: '2026-11-13T14:01:00Z', text: 'a' }),
      // 14:03 UTC, written with an offset.
      entry({ at: '2026-11-13T15:03:00+01:00', text: 'b' }),
    ];
    expect(orderEntries(list).map((e) => e.text)).toEqual(['a', 'b', 'c']);
    // A new array: the input is left alone.
    expect(list.map((e) => e.text)).toEqual(['c', 'a', 'b']);
  });

  it('keeps the source order for entries at the same time', () => {
    const at = '2026-11-13T14:02:00.000Z';
    const list = [
      entry({ at: '2026-11-13T14:09:00Z', text: 'last' }),
      entry({ at, kind: 'inspection', text: 'first at 14:02' }),
      entry({ at, kind: 'confirmation', text: 'second at 14:02' }),
      entry({ at: '2026-11-13T14:02:00Z', kind: 'task', text: 'third at 14:02' }),
      entry({ at: '2026-11-13T14:00:00Z', text: 'earliest' }),
    ];
    expect(orderEntries(list).map((e) => e.text)).toEqual(['earliest', 'first at 14:02', 'second at 14:02', 'third at 14:02', 'last']);
  });
});

describe('normaliseTurnRecord', () => {
  it('never throws and fills a usable empty record from nothing', () => {
    for (const raw of [undefined, null, 42, 'x', [], {}]) {
      const r = normaliseTurnRecord(raw, 'T5-DL1776');
      expect(r.turn_id).toBe('T5-DL1776');
      expect(r.entries).toEqual([]);
      expect(r.cost).toEqual({ inspections_usd: 0, agent_usd: 0, total_usd: 0, note: null });
      expect(r.flight).toBeNull();
    }
  });

  it('drops malformed entries, fills missing fields and renumbers in time order', () => {
    const r = normaliseTurnRecord({
      turn_id: 'T5-DL1776',
      gate: 'T5',
      flight: 'DL1776',
      cost: { inspections_usd: 0.012, agent_usd: 0.003 },
      entries: [
        null,
        'not an entry',
        { at: '2026-11-13T14:00:00Z' }, // no kind
        { kind: 'task', at: 'yesterday' }, // unreadable time
        { kind: 'task' }, // no time
        { kind: 'report', at: '2026-11-13T14:02:00Z', seq: 7, person: { person_id: 'kim', name: 'Kim' }, data: { raw_text: 'done' } },
        { kind: 'inspection', at: '2026-11-13T14:01:00Z', refs: { inspection_id: 'insp-001', angle: 3 }, data: 'nope' },
      ],
    });
    expect(r.entries.map((e) => e.kind)).toEqual(['inspection', 'report']);
    expect(r.entries.map((e) => e.seq)).toEqual([0, 1]);
    const [insp, report] = r.entries;
    expect(insp).toMatchObject({ event: '', text: '', t: null, person: null, data: {} });
    expect(insp!.refs).toEqual({ inspection_id: 'insp-001', task_id: null, finding_id: null, angle: null });
    expect(report!.person).toEqual({ person_id: 'kim', name: 'Kim', role: null });
    expect(report!.data).toEqual({ raw_text: 'done' });
    // total_usd missing: the sum of the parts.
    expect(r.cost.total_usd).toBeCloseTo(0.015);
  });

  it('lets an unknown kind through, with a readable label', () => {
    const r = normaliseTurnRecord({
      turn_id: 'T1-DL1432',
      entries: [{ kind: 'handover', event: 'handed_over', at: '2026-11-13T14:00:00Z', text: 'Patel handed over to Reyes.' }],
    });
    expect(r.entries).toHaveLength(1);
    expect(r.entries[0]!.kind).toBe('handover');
    expect(entryKindLabel('handover')).toBe('Handover');
    expect(entryKindLabel('shift_change')).toBe('Shift change');
    expect(entryKindLabel('')).toBe('Entry');
    expect(entryKindLabel('report')).toBe('Report');
    expect(entryKindLabel('confirmation')).toBe('Confirmation');
  });
});

describe('buildRecordDownload', () => {
  const record: TurnRecord = {
    turn_id: 'T5-DL1776',
    gate: 'T5',
    flight: 'DL1776',
    generated_at: '2026-11-13T14:20:00Z',
    cost: { inspections_usd: 0.0123, agent_usd: 0.004, total_usd: 0.0163, note: 'illustrative' },
    entries: [
      entry({ seq: 0, at: '2026-11-13T14:05:00Z', kind: 'confirmation', event: 'acknowledged', text: 'second' }),
      entry({ seq: 1, at: '2026-11-13T14:01:00Z', kind: 'report', event: 'done', text: 'first', data: { raw_text: 'gone' } }),
    ],
  };

  it('is valid JSON with the cost and the entries in time order', () => {
    const { filename, text } = buildRecordDownload(record);
    expect(filename).toBe('turn-T5-DL1776-record.json');
    const parsed = JSON.parse(text) as TurnRecord;
    expect(parsed.cost).toEqual(record.cost);
    expect(parsed.turn_id).toBe('T5-DL1776');
    expect(parsed.entries.map((e) => e.text)).toEqual(['first', 'second']);
    expect(parsed.entries.map((e) => e.seq)).toEqual([0, 1]);
    expect(parsed.entries[0]!.data).toEqual({ raw_text: 'gone' });
  });

  it('keeps the file name safe', () => {
    expect(buildRecordDownload({ ...record, turn_id: 'T5/../x y' }).filename).toBe('turn-T5-..-x-y-record.json');
    expect(buildRecordDownload({ ...record, turn_id: '' }).filename).toBe('turn-unknown-record.json');
  });
});
