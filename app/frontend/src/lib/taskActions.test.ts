import { describe, expect, it } from 'vitest';
import type { RosterPerson, Task } from '../api/agentTypes';
import { actionCommand, handoverCandidates, outsideRecipient, taskActions, type TaskAction, type Viewer } from './taskActions';

const KIM: Viewer = { person_id: 'kim', role: 'ramp_agent' };
const OKAFOR: Viewer = { person_id: 'okafor', role: 'ramp_lead' };
const DANA: Viewer = { person_id: 'dana', role: 'supervisor' };

function task(over: Partial<Task> = {}): Task {
  return {
    task_id: 'K-3',
    type: 'remove',
    gate: 'T5',
    turn_id: 'T5-DL1776',
    inspection_id: 'insp-1',
    finding_id: 'F2',
    inspection_finding_id: 'f-2',
    angle: 'CARGO',
    severity: 'REMOVE',
    required_role: 'any',
    assignee_id: 'kim',
    instruction: 'Remove the bag tag by the belt loader',
    status: 'assigned',
    created_by: 'agent',
    escalation_level: 0,
    created_at: '2026-11-13T14:00:00Z',
    closed_at: null,
    close_reason: null,
    closed_by_confirmation_id: null,
    ...over,
  };
}

const byLabel = (actions: TaskAction[], label: string) => actions.filter((a) => a.label === label);
const sends = (actions: TaskAction[], t: Task) => actions.map((a) => actionCommand(a.id, t).command);

describe('taskActions: "Not found" on a removal or walk Task is a Report', () => {
  for (const type of ['remove', 'walk_and_report'] as const) {
    for (const status of ['assigned', 'accepted', 'reported'] as const) {
      it(`${type}, ${status}: one "Not found", sent as cant-find, and no not-found Confirmation`, () => {
        const t = task({ type, status });
        const actions = taskActions(t, KIM);
        const notFound = byLabel(actions, 'Not found');
        expect(notFound).toHaveLength(1);
        expect(notFound[0]).toMatchObject({ id: 'cant_find', group: 'report', enabled: true, needs: 'note' });
        expect(sends(actions, t)).not.toContain('not-found');
        expect(actions.some((a) => a.id === 'not_found')).toBe(false);
      });
    }
  }

  it('sends the Task ID, and the note only when one was typed', () => {
    const t = task();
    expect(actionCommand('cant_find', t)).toEqual({ command: 'cant-find', args: ['K-3'] });
    expect(actionCommand('cant_find', t, { note: '   ' })).toEqual({ command: 'cant-find', args: ['K-3'] });
    expect(actionCommand('cant_find', t, { note: ' walked it twice ' })).toEqual({ command: 'cant-find', args: ['K-3', 'walked it twice'] });
  });

  it('is offered to a Ramp Agent and to a Ramp Lead alike, on a HOLD removal too', () => {
    const hold = task({ severity: 'HOLD', finding_id: 'F1', angle: 'ENG-R' });
    for (const [viewer, t] of [
      [KIM, hold],
      [OKAFOR, task({ assignee_id: 'okafor' })],
      [OKAFOR, { ...hold, assignee_id: 'okafor' }],
    ] as const) {
      const a = byLabel(taskActions(t, viewer), 'Not found');
      expect(a).toHaveLength(1);
      expect(a[0]!.group).toBe('report');
      expect(sends(taskActions(t, viewer), t)).not.toContain('not-found');
    }
  });

  it('is not offered to someone who does not hold the Task, or to a supervisor', () => {
    expect(taskActions(task(), DANA).map((a) => a.id)).toEqual(['reassign']);
    expect(taskActions(task(), OKAFOR).map((a) => a.id)).toEqual(['reassign']);
    expect(taskActions(task({ assignee_id: 'patel' }), KIM)).toEqual([]);
  });
});

describe('taskActions: recording "not found" stays a Confirmation where it is the person\'s decision', () => {
  it('ack_hold held by a Ramp Lead: "Record not found" sends the not-found Confirmation', () => {
    const t = task({ type: 'ack_hold', severity: 'HOLD', finding_id: 'F1', angle: 'ENG-R', assignee_id: 'okafor', required_role: 'ramp_lead', status: 'accepted' });
    const actions = taskActions(t, OKAFOR);
    expect(byLabel(actions, 'Not found')).toHaveLength(0);
    const record = byLabel(actions, 'Record not found');
    expect(record).toHaveLength(1);
    expect(record[0]).toMatchObject({ id: 'not_found', group: 'confirmation', enabled: true });
    expect(actionCommand('not_found', t)).toEqual({ command: 'not-found', args: ['F1'] });
    expect(actions.some((a) => a.id === 'cant_find')).toBe(false);
  });

  it('no label is shared by a Report and a Confirmation on any Task type', () => {
    const types: Task['type'][] = ['ack_hold', 'remove', 'walk_and_report', 'check_by_eye', 'report_outside_boundary', 'sign_off'];
    for (const type of types) {
      for (const viewer of [KIM, OKAFOR]) {
        const actions = taskActions(task({ type, assignee_id: viewer.person_id }), viewer);
        const reports = new Set(actions.filter((a) => a.group === 'report').map((a) => a.label));
        for (const a of actions.filter((x) => x.group === 'confirmation')) expect(reports.has(a.label)).toBe(false);
        // Every command a Report button sends is a Report command.
        for (const a of actions.filter((x) => x.group === 'report')) {
          expect(['accept', 'done', 'cant', 'cant-find']).toContain(actionCommand(a.id, task({ type })).command);
        }
      }
    }
  });
});

describe('taskActions: debris outside the gate safety envelope', () => {
  const outside = (instruction: string) =>
    task({
      type: 'report_outside_boundary',
      finding_id: 'F3',
      angle: 'WIDE',
      severity: 'ADVISORY',
      instruction,
    });
  const ramp1 = outside('Report the object outside the gate safety envelope at T5 to Ramp 1 control; do not remove it: a loose strap on the taxilane');
  const ops = outside('Report the object outside the gate safety envelope at T5 to Airport Operations; do not remove it: debris beyond the zipper marking');

  it('offers one Confirmation for each recipient, each with its own command', () => {
    const actions = taskActions(ramp1, KIM);
    expect(actions.filter((a) => a.label.startsWith('Reported to')).map((a) => [a.id, a.label, a.group])).toEqual([
      ['reported_ramp1', 'Reported to Ramp 1 control', 'confirmation'],
      ['reported_airport_ops', 'Reported to Airport Ops', 'confirmation'],
    ]);
    expect(actionCommand('reported_ramp1', ramp1)).toEqual({ command: 'reported', args: ['F3', 'ramp1'] });
    expect(actionCommand('reported_airport_ops', ramp1)).toEqual({ command: 'reported', args: ['F3', 'airport-ops'] });
    expect(actions.some((a) => a.label.includes('/'))).toBe(false);
  });

  it('marks as primary the recipient the instruction names, Ramp 1 control by default', () => {
    const primary = (t: Task) => taskActions(t, KIM).filter((a) => a.primary).map((a) => a.id);
    expect(outsideRecipient(ramp1)).toBe('ramp1');
    expect(primary(ramp1)).toEqual(['reported_ramp1']);
    expect(outsideRecipient(ops)).toBe('airport-ops');
    expect(primary(ops)).toEqual(['reported_airport_ops']);
    // An older server, or an instruction a Ramp Lead typed with /send, names nobody.
    const plain = outside('Report the object outside the gate safety envelope at T5: a loose strap');
    expect(outsideRecipient(plain)).toBe('ramp1');
    expect(primary(plain)).toEqual(['reported_ramp1']);
  });

  it('is disabled for a Ramp Agent when the Finding is a HOLD, and has no cant-find Report', () => {
    const hold = { ...ramp1, severity: 'HOLD' as const };
    const actions = taskActions(hold, KIM);
    expect(actions.filter((a) => a.id.startsWith('reported_')).every((a) => !a.enabled && a.why)).toBe(true);
    expect(taskActions({ ...hold, assignee_id: 'okafor' }, OKAFOR).filter((a) => a.id.startsWith('reported_')).every((a) => a.enabled)).toBe(true);
    expect(actions.some((a) => a.id === 'cant_find')).toBe(false);
    expect(byLabel(actions, 'Record not found')[0]?.group).toBe('confirmation');
  });
});

describe('handoverCandidates', () => {
  const person = (person_id: string, role: RosterPerson['role'], shift: RosterPerson['shift']): RosterPerson => ({
    person_id,
    name: person_id,
    role,
    gates: [],
    shift,
    signed_in: false,
  });
  it('lists on-shift Ramp Agents and Ramp Leads other than the person asking', () => {
    const roster = [
      person('kim', 'ramp_agent', 'on'),
      person('okafor', 'ramp_lead', 'on'),
      person('patel', 'ramp_agent', 'break'),
      person('reyes', 'ramp_lead', 'on'),
      person('lee', 'ramp_lead', 'off'),
      person('dana', 'supervisor', 'on'),
    ];
    expect(handoverCandidates(roster, 'okafor').map((p) => p.person_id)).toEqual(['kim', 'reyes']);
    expect(handoverCandidates([person('okafor', 'ramp_lead', 'on')], 'okafor')).toEqual([]);
  });
});
