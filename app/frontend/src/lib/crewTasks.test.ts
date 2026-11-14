import { describe, expect, it } from 'vitest';
import type { ActivityEntry, Board, RosterPerson, Task } from '../api/agentTypes';
import { actorLabel } from './activity';
import {
  assigneeLabel,
  crewEscalationLabel,
  escalationLevelLabel,
  taskDetail,
  crewStatusLabel,
  escalationsInProgress,
  groupRoster,
  nextTimerIn,
  openFor,
  openTasks,
  recentActivity,
  recentlyClosedTasks,
  sortCrewTasks,
  taskHref,
  taskInstruction,
  taskTarget,
  taskTypeInfo,
} from './crewTasks';

function task(over: Partial<Task> & { task_id: string }): Task {
  return {
    type: 'remove',
    gate: 'T5',
    turn_id: 'turn-T5-1',
    inspection_id: 'insp-009',
    finding_id: 'F1',
    angle: 'ENG-L',
    severity: 'REMOVE',
    required_role: 'any',
    assignee_id: 'kim',
    instruction: 'Remove the item.',
    status: 'assigned',
    created_by: 'code',
    escalation_level: 0,
    created_at: '2026-11-13T14:00:00.000Z',
    closed_at: null,
    close_reason: null,
    closed_by_confirmation_id: null,
    ...over,
  };
}

function person(over: Partial<RosterPerson> & { person_id: string; name: string }): RosterPerson & { open_tasks: number } {
  return { role: 'ramp_agent', gates: ['T5'], shift: 'on', signed_in: false, open_tasks: 0, ...over };
}

const ids = (tasks: Task[]) => tasks.map((t) => t.task_id);

describe('sortCrewTasks: the Task list ordering', () => {
  it('puts open Tasks before closed and cancelled ones', () => {
    const out = sortCrewTasks([
      task({ task_id: 'K-1', status: 'closed', closed_at: '2026-11-13T14:05:00Z', severity: 'HOLD', escalation_level: 2 }),
      task({ task_id: 'K-2', status: 'cancelled', closed_at: '2026-11-13T14:04:00Z' }),
      task({ task_id: 'K-3', status: 'reported', severity: 'ADVISORY' }),
    ]);
    expect(ids(out)).toEqual(['K-3', 'K-1', 'K-2']);
  });

  it('puts HOLD Tasks first among open Tasks, even above an escalated non-HOLD Task', () => {
    const out = sortCrewTasks([
      task({ task_id: 'K-1', severity: 'REMOVE', escalation_level: 2, created_at: '2026-11-13T13:00:00Z' }),
      task({ task_id: 'K-2', severity: 'HOLD', type: 'ack_hold' }),
    ]);
    expect(ids(out)).toEqual(['K-2', 'K-1']);
  });

  it('orders by Escalation level, high to low, within the same HOLD rank', () => {
    const out = sortCrewTasks([
      task({ task_id: 'K-1', severity: 'HOLD', escalation_level: 0, created_at: '2026-11-13T13:00:00Z' }),
      task({ task_id: 'K-2', severity: 'HOLD', escalation_level: 2 }),
      task({ task_id: 'K-3', severity: 'HOLD', escalation_level: 1 }),
    ]);
    expect(ids(out)).toEqual(['K-2', 'K-3', 'K-1']);
  });

  it('orders by severity: REMOVE, ADVISORY, then none or unknown', () => {
    const out = sortCrewTasks([
      task({ task_id: 'K-1', severity: null, created_at: '2026-11-13T13:00:00Z' }),
      task({ task_id: 'K-2', severity: 'ADVISORY', created_at: '2026-11-13T13:01:00Z' }),
      task({ task_id: 'K-3', severity: 'NEW_SEVERITY' as Task['severity'], created_at: '2026-11-13T12:00:00Z' }),
      task({ task_id: 'K-4', severity: 'REMOVE', created_at: '2026-11-13T13:02:00Z' }),
    ]);
    expect(ids(out)).toEqual(['K-4', 'K-2', 'K-3', 'K-1']);
  });

  it('puts the oldest open Task first when everything else is equal', () => {
    const out = sortCrewTasks([
      task({ task_id: 'K-1', created_at: '2026-11-13T14:02:00Z' }),
      task({ task_id: 'K-2', created_at: '2026-11-13T14:00:00Z' }),
      task({ task_id: 'K-3', created_at: 'not a time' }),
      task({ task_id: 'K-4', created_at: '2026-11-13T14:01:00Z' }),
    ]);
    expect(ids(out)).toEqual(['K-2', 'K-4', 'K-1', 'K-3']);
  });

  it('puts the most recently closed Task first among closed ones', () => {
    const out = sortCrewTasks([
      task({ task_id: 'K-1', status: 'closed', closed_at: '2026-11-13T14:01:00Z' }),
      task({ task_id: 'K-2', status: 'closed', closed_at: '2026-11-13T14:09:00Z' }),
    ]);
    expect(ids(out)).toEqual(['K-2', 'K-1']);
  });

  it('breaks a full tie on task_id in natural order, whatever the input order', () => {
    const tied = [task({ task_id: 'K-10' }), task({ task_id: 'K-2' }), task({ task_id: 'K-1' })];
    expect(ids(sortCrewTasks(tied))).toEqual(['K-1', 'K-2', 'K-10']);
    expect(ids(sortCrewTasks([...tied].reverse()))).toEqual(['K-1', 'K-2', 'K-10']);
  });

  it('does not change its input', () => {
    const input = [task({ task_id: 'K-2' }), task({ task_id: 'K-1' })];
    sortCrewTasks(input);
    expect(ids(input)).toEqual(['K-2', 'K-1']);
  });

  it('filters open, recently closed and escalated Tasks', () => {
    const tasks = [
      task({ task_id: 'K-1', status: 'accepted', escalation_level: 1 }),
      task({ task_id: 'K-2', status: 'closed', closed_at: '2026-11-13T14:03:00Z', escalation_level: 2 }),
      task({ task_id: 'K-3', status: 'reported' }),
      task({ task_id: 'K-4', status: 'assigned', severity: 'HOLD', escalation_level: 2 }),
    ];
    expect(ids(openTasks(tasks))).toEqual(['K-4', 'K-1', 'K-3']);
    expect(ids(recentlyClosedTasks(tasks))).toEqual(['K-2']);
    // A closed Task is no longer an Escalation in progress.
    expect(ids(escalationsInProgress(tasks))).toEqual(['K-4', 'K-1']);
  });
});

describe('an unknown Task type', () => {
  const later = task({ task_id: 'K-9', type: 'handover_brief' as Task['type'], instruction: '  Brief Reyes on T5.  ', severity: null, finding_id: null });

  it('shows its raw name and its instruction', () => {
    expect(taskTypeInfo(later)).toEqual({ label: 'handover_brief', known: false, raw: 'handover_brief' });
    expect(taskInstruction(later)).toBe('Brief Reyes on T5.');
  });

  it('labels known types in words', () => {
    expect(taskTypeInfo(task({ task_id: 'K-1', type: 'ack_hold' }))).toEqual({ label: 'Acknowledge and clear HOLD', known: true, raw: 'ack_hold' });
  });

  it('does not throw on a missing or odd type, instruction or status', () => {
    const odd = { ...later, type: undefined, instruction: 42, status: 'paused' } as unknown as Task;
    expect(taskTypeInfo(odd)).toEqual({ label: 'Task of no stated type', known: false, raw: '' });
    expect(taskInstruction(odd)).toBe('');
    expect(crewStatusLabel(odd)).toBe('paused');
    expect(taskTypeInfo({ type: 'toString' }).known).toBe(false);
  });

  it('sorts and filters with known types', () => {
    const out = openTasks([later, task({ task_id: 'K-1', severity: 'HOLD', type: 'ack_hold' })]);
    expect(ids(out)).toEqual(['K-1', 'K-9']);
  });
});

describe('labels', () => {
  it('names the Escalation level, and nothing at level 0', () => {
    expect(crewEscalationLabel(0)).toBeNull();
    expect(crewEscalationLabel(1)).toBe('Escalated · level 1');
    expect(crewEscalationLabel(2)).toBe('Escalated · level 2');
    expect(crewEscalationLabel(Number.NaN)).toBeNull();
    expect(escalationLevelLabel(0)).toBeNull();
    expect(escalationLevelLabel(2)).toBe('Level 2');
    expect(escalationLevelLabel(Number.NaN)).toBeNull();
  });

  it('says where a Task points', () => {
    expect(taskTarget({ finding_id: 'F3', angle: 'ENG-L' })).toBe('Finding F3');
    expect(taskTarget({ finding_id: null, angle: 'NOSE' })).toBe('Angle NOSE');
    expect(taskTarget({ finding_id: null, angle: null })).toBe('Inspection');
  });

  it('links a Task to its Turn, Inspection and Finding', () => {
    expect(
      taskHref(task({ task_id: 'K-1', turn_id: 'turn-T5-1', inspection_id: 'insp-009', finding_id: 'F2', inspection_finding_id: 'insp-009-f3' })),
    ).toBe('#/turn/turn-T5-1/insp-009?finding=insp-009-f3');
    // The label alone cannot be found in the Turn view: link to the Inspection.
    expect(taskHref(task({ task_id: 'K-1', turn_id: 'turn-T5-1', inspection_id: 'insp-009', finding_id: 'F2' }))).toBe('#/turn/turn-T5-1/insp-009');
    expect(taskHref(task({ task_id: 'K-1', turn_id: 'turn-T5-1', inspection_id: 'insp-009', finding_id: null }))).toBe('#/turn/turn-T5-1/insp-009');
  });

  it('measures how long a Task has been open against an injected now', () => {
    const now = Date.parse('2026-11-13T15:05:30Z');
    expect(openFor('2026-11-13T15:05:00Z', now)).toBe('30 s');
    expect(openFor('2026-11-13T15:02:00Z', now)).toBe('3 min');
    expect(openFor('2026-11-13T13:00:00Z', now)).toBe('2 h 05 min');
    expect(openFor('2026-11-13T15:06:00Z', now)).toBe('0 s');
    expect(openFor('nonsense', now)).toBe('');
    expect(openFor(null, now)).toBe('');
  });

  it('names assignees and actors from the Roster', () => {
    const roster = [person({ person_id: 'okafor', name: 'Okafor', role: 'ramp_lead' })];
    expect(assigneeLabel('okafor', roster)).toBe('Okafor (Ramp Lead)');
    expect(assigneeLabel('ghost', roster)).toBe('ghost');
    expect(assigneeLabel(null, roster)).toBe('Unassigned');
    expect(actorLabel('Okafor', roster)).toBe('Okafor (Ramp Lead)');
    expect(actorLabel('timer', roster)).toBe('Timer');
  });
});

describe('taskDetail: the line under the Task type', () => {
  it('drops the restated Task before the first colon', () => {
    expect(taskDetail('Acknowledge and clear the HOLD at T5 ENG-R: Hammer on the pavement.')).toBe('Hammer on the pavement.');
  });
  it('keeps an instruction without that shape whole', () => {
    expect(taskDetail('Check T2 ENG-R by eye or re-inspect it')).toBe('Check T2 ENG-R by eye or re-inspect it');
    expect(taskDetail('Nothing after: ')).toBe('Nothing after: ');
    expect(taskDetail('')).toBe('');
  });
});

describe('groupRoster', () => {
  it('groups people on shift, on a break and off shift, Ramp Leads first', () => {
    const g = groupRoster([
      person({ person_id: 'kim', name: 'Kim' }),
      person({ person_id: 'dana', name: 'Dana', role: 'supervisor' }),
      person({ person_id: 'okafor', name: 'Okafor', role: 'ramp_lead' }),
      person({ person_id: 'patel', name: 'Patel', shift: 'break' }),
      person({ person_id: 'reyes', name: 'Reyes', role: 'ramp_lead', shift: 'off' }),
    ]);
    expect(g.onShift.map((p) => p.person_id)).toEqual(['okafor', 'kim', 'dana']);
    expect(g.onBreak.map((p) => p.person_id)).toEqual(['patel']);
    expect(g.offShift.map((p) => p.person_id)).toEqual(['reyes']);
  });

  it('handles an empty Roster', () => {
    expect(groupRoster([])).toEqual({ onShift: [], onBreak: [], offShift: [] });
  });

  it('handles empty Tasks', () => {
    expect(sortCrewTasks([])).toEqual([]);
    expect(openTasks([])).toEqual([]);
    expect(escalationsInProgress([])).toEqual([]);
    expect(recentlyClosedTasks([])).toEqual([]);
  });
});

describe('activity and timers', () => {
  const entry = (id: number): ActivityEntry => ({ id, at: '', t: id, kind: 'code', event: 'task_assigned', gate: null, turn_id: null, actor: 'code', text: '', data: {} });

  it('shows the newest activity first, capped', () => {
    expect(recentActivity([entry(1), entry(3), entry(2)], 2).map((e) => e.id)).toEqual([3, 2]);
    expect(recentActivity([])).toEqual([]);
  });

  it('gives the seconds until a Task’s next timer', () => {
    const timers: Board['timers'] = [
      { task_id: 'K-1', kind: 'hold_ack_1', fire_t: 130 },
      { task_id: 'K-1', kind: 'hold_ack_2', fire_t: 160 },
      { task_id: null, kind: 'other', fire_t: 100 },
    ];
    expect(nextTimerIn('K-1', timers, 120)).toBe(10);
    expect(nextTimerIn('K-1', timers, 200)).toBe(0);
    expect(nextTimerIn('K-2', timers, 120)).toBeNull();
  });
});
