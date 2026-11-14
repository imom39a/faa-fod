import { describe, expect, it } from 'vitest';
import type { ActivityEntry } from '../api/agentTypes';
import { CATEGORY_LABEL, CATEGORY_ORDER, activityCategory, entryPeople, filterActivity, type ActivityCategory } from './activity';

const cat = (event: string) => activityCategory({ event });

describe('activity categories', () => {
  it('puts Handover and Shift events under "Shift / Handover"', () => {
    for (const e of ['handover_requested', 'handover_declined', 'handover_expired', 'handover', 'shift_changed', 'sole_lead_leaving']) {
      expect(cat(e)).toBe('shift');
    }
    expect(CATEGORY_LABEL.shift).toBe('Shift / Handover');
  });

  it('puts "reported to" with the Confirmation that records it, and keeps a Report apart', () => {
    expect(cat('outside_reported')).toBe('confirmation');
    expect(cat('confirmation')).toBe('confirmation');
    // "Not found" from a removal Task is a Report: it arrives as task_reported.
    expect(cat('task_reported')).toBe('report');
    expect(cat('task_reopened')).toBe('task');
    expect(cat('task_escalated')).toBe('timer');
  });

  it('shows an event it does not know under System', () => {
    expect(cat('something_new')).toBe('system');
  });

  it('offers every category in the filter, once, with a label', () => {
    const all = Object.keys(CATEGORY_LABEL) as ActivityCategory[];
    expect([...CATEGORY_ORDER].sort()).toEqual([...all].sort());
    expect(new Set(CATEGORY_ORDER).size).toBe(CATEGORY_ORDER.length);
  });

  it('finds both people of a Handover, and filters by the new category', () => {
    const entry = (id: number, event: string, actor: string, data: Record<string, unknown>): ActivityEntry => ({
      id,
      at: '2026-11-13T14:00:00Z',
      t: id,
      kind: 'code',
      event,
      gate: null,
      turn_id: null,
      actor,
      text: event,
      data,
    });
    const roster = [
      { person_id: 'okafor', name: 'Okafor' },
      { person_id: 'reyes', name: 'Reyes' },
    ];
    const asked = entry(1, 'handover_requested', 'okafor', { from: 'okafor', to: 'reyes', tasks: ['K-1'], proposal_id: 'P-1' });
    const brk = entry(2, 'shift_changed', 'okafor', { person_id: 'okafor', shift: 'break' });
    const report = entry(3, 'task_reported', 'okafor', { task_id: 'K-1', kind: 'not_found' });
    expect(entryPeople(asked, roster).sort()).toEqual(['okafor', 'reyes']);
    expect(filterActivity([asked, brk, report], { category: 'shift' }, roster).map((e) => e.id)).toEqual([1, 2]);
    expect(filterActivity([asked, brk, report], { category: 'shift', personId: 'reyes' }, roster).map((e) => e.id)).toEqual([1]);
  });
});
