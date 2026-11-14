import { describe, expect, it } from 'vitest';
import { escalationsInProgress, groupRoster, openTasks, taskHref, taskInstruction, taskTypeInfo } from '../lib/crewTasks';
import { parseRoute } from '../route';
import { MockBackend } from './backend';
import { SAMPLE_CREATOR, SAMPLE_UNKNOWN_TYPE, createCrewSample } from './crewSample';
import { MockDispatcher } from './dispatch';

function setup(startAt = 0) {
  const backend = new MockBackend({ startAt });
  const dispatcher = new MockDispatcher(backend);
  return { backend, dispatcher, board: () => createCrewSample(backend)(dispatcher.board()) };
}

describe('mock mode: sample Crew and Tasks data', () => {
  it('at load, shows a Roster with a break, open Tasks of several types, activity and a cost', () => {
    const { dispatcher, board } = setup();
    expect(dispatcher.board().tasks).toEqual([]);
    const b = board();

    const roster = groupRoster(b.roster);
    expect(roster.onShift.length).toBeGreaterThan(0);
    expect(roster.onBreak.map((p) => p.person_id)).toEqual(['sample-lee']);

    const open = openTasks(b.tasks);
    expect(new Set(open.map((t) => t.type)).size).toBeGreaterThanOrEqual(4);
    expect(b.tasks.every((t) => t.created_by === SAMPLE_CREATOR)).toBe(true);
    const [first] = open;
    expect(first?.severity).toBe('HOLD');
    expect(escalationsInProgress(b.tasks).some((t) => t.severity === 'HOLD' && t.escalation_level >= 1)).toBe(true);

    const unknown = b.tasks.find((t) => (t.type as string) === SAMPLE_UNKNOWN_TYPE)!;
    expect(taskTypeInfo(unknown)).toEqual({ label: SAMPLE_UNKNOWN_TYPE, known: false, raw: SAMPLE_UNKNOWN_TYPE });
    expect(taskInstruction(unknown)).not.toBe('');

    const events = new Set(b.activity.map((e) => e.event));
    for (const e of ['task_assigned', 'task_escalated', 'agent_wake']) expect(events).toContain(e);
    expect(b.activity.filter((e) => e.data.sample === true).every((e) => e.id < 0)).toBe(true);
    expect(b.cost.agent_session_usd).toBeGreaterThan(0);

    // Open Tasks are counted against the people they are assigned to.
    expect(b.roster.find((p) => p.person_id === 'okafor')?.open_tasks).toBe(1);
  });

  it('shows only states the dispatcher can produce', () => {
    // models.py LEAD_ONLY and role_may_take(); mock/dispatch.ts uses the same list.
    const LEAD_ONLY = ['ack_hold', 'check_by_eye', 'sign_off'];
    const required = (type: string) => (LEAD_ONLY.includes(type) ? 'ramp_lead' : 'any');
    const mayTake = (role: string, type: string) => role !== 'supervisor' && (role === 'ramp_lead' || required(type) === 'any');
    const REPORT_KINDS = ['accepted', 'done', 'not_found', 'blocked', 'note'];

    // The list above still matches what the mock dispatcher assigns.
    const real = setup(120).dispatcher.board().tasks;
    expect(real.length).toBeGreaterThan(0);
    for (const t of real) expect(t.required_role).toBe(required(t.type));

    const b = setup().board();
    for (const t of b.tasks) {
      expect(t.required_role, t.task_id).toBe(required(t.type));
      const person = b.roster.find((p) => p.person_id === t.assignee_id);
      expect(person, t.task_id).toBeDefined();
      expect(mayTake(person!.role, t.type), `${t.task_id} ${t.type} -> ${person!.role}`).toBe(true);
      for (const r of t.reports) expect(REPORT_KINDS, t.task_id).toContain(r.kind);
    }

    // A timer escalates only a HOLD. A no-Report timer asks or offers reassignment; it never raises the level.
    const byId = new Map(b.tasks.map((t) => [t.task_id, t]));
    for (const e of b.activity.filter((x) => x.event === 'task_escalated' && x.actor === 'timer')) {
      expect(byId.get(String(e.data.task_id))?.type, e.text).toBe('ack_hold');
    }
    // Every escalated sample Task has a task_escalated entry that reaches its level.
    for (const t of b.tasks.filter((x) => x.escalation_level > 0)) {
      const levels = b.activity.filter((e) => e.event === 'task_escalated' && e.data.task_id === t.task_id).map((e) => Number(e.data.level));
      expect(Math.max(0, ...levels), t.task_id).toBe(t.escalation_level);
    }
  });

  it('every sample Task opens a real mock Turn', () => {
    const { backend, board } = setup();
    for (const t of board().tasks) {
      const route = parseRoute(taskHref(t));
      expect(route.name).toBe('turn');
      if (route.name !== 'turn') continue;
      const turn = backend.getTurn(route.turnId);
      expect(turn.inspections.map((r) => r.inspection_id)).toContain(route.inspectionId);
    }
  });

  it('gives way to the dispatcher once the demo has a Task, and changes nothing in it', () => {
    const { dispatcher, board } = setup(120);
    const own = dispatcher.board();
    expect(own.tasks.length).toBeGreaterThan(0);
    const b = board();
    expect(b).toEqual(own);
    expect(b.tasks.some((t) => t.created_by === SAMPLE_CREATOR)).toBe(false);
  });

  it('links a real Task to its Finding in the Task’s own Inspection', () => {
    const { backend, board } = setup(120);
    const withFinding = board().tasks.filter((t) => t.finding_id !== null);
    expect(withFinding.length).toBeGreaterThan(0);
    for (const t of withFinding) {
      const route = parseRoute(taskHref(t));
      if (route.name !== 'turn') throw new Error('not a Turn link');
      expect(route.inspectionId).toBe(t.inspection_id);
      const report = backend.getInspection(route.inspectionId!);
      const finding = report.findings.find((f) => f.finding_id === route.finding);
      expect(finding?.angle).toBe(t.angle);
      expect(finding?.severity).toBe(t.severity);
    }
  });
});
