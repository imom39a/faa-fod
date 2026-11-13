/**
 * Which actions a signed-in person is offered on a Task, and the structured
 * command each one sends. The set follows app/backend/fodgate/dispatch/commands.py
 * and the Workflow's role rules. The server still decides: an action offered
 * here can be refused, and the refusal is shown.
 *
 * Two kinds of action must never be confused:
 * - `confirmation`: records a Confirmation on the Inspection, as this person.
 * - `report`: tells the agent about the Task. It never changes a Finding.
 */
import { ACTIVE_TASK_STATUSES, type PersonRole, type StructuredCommand, type Task, type TaskStatus } from '../api/agentTypes';
import type { FalseAlarmReason } from '../api/types';

export type ActionId =
  | 'ack'
  | 'removed'
  | 'false_alarm'
  | 'not_found'
  | 'reported'
  | 'all_removed'
  | 'reinspect'
  | 'eye'
  | 'signoff'
  | 'accept'
  | 'done'
  | 'cant'
  | 'reassign';

/** `photo` takes a new photo and records nothing; `routing` moves the Task. */
export type ActionGroup = 'confirmation' | 'report' | 'photo' | 'routing';

export type TaskAction = {
  id: ActionId;
  label: string;
  group: ActionGroup;
  /** False when the role or the Task's state rules it out; `why` says so. */
  enabled: boolean;
  why?: string;
  /** Something to pick or type before it can be sent. */
  needs?: 'reason' | 'note' | 'person';
  /** The main next step for this Task. */
  primary?: boolean;
  /** Runs a re-inspection: takes a moment, and the outcome depends on the new photo. */
  reinspects?: boolean;
  /** Short enough to repeat under the agent's message about this Task. */
  quick?: boolean;
};

export type Viewer = { person_id: string; role: PersonRole };

const LEAD_ONLY_HOLD = 'Ramp Lead only: a HOLD is recorded by a Ramp Lead';
const LEAD_ONLY_EYE = 'Ramp Lead only: checked by eye is recorded by a Ramp Lead';

export function isActiveTask(task: Pick<Task, 'status'>): boolean {
  return ACTIVE_TASK_STATUSES.includes(task.status as TaskStatus);
}

/** Whether this role may record a Confirmation on a Finding of this severity (rule set `roles`). */
export function roleMayConfirm(role: PersonRole, severity: Task['severity']): boolean {
  if (role === 'ramp_lead') return true;
  return role === 'ramp_agent' && severity !== 'HOLD' && severity !== null;
}

export function taskActions(task: Task, viewer: Viewer): TaskAction[] {
  if (!isActiveTask(task)) return [];
  const { role } = viewer;
  const mine = task.assignee_id === viewer.person_id;
  const lead = role === 'ramp_lead';
  const reassign: TaskAction[] =
    lead || role === 'supervisor' ? [{ id: 'reassign', label: 'Move to…', group: 'routing', enabled: true, needs: 'person' }] : [];
  // A supervisor records nothing; Reports and Confirmations belong to the person who holds the Task.
  if (role === 'supervisor' || !mine) return reassign;

  const sev = task.severity;
  const hasFinding = task.finding_id !== null;
  const confirm = (a: Omit<TaskAction, 'group' | 'enabled'>, allowed = roleMayConfirm(role, sev), why = LEAD_ONLY_HOLD): TaskAction => ({
    ...a,
    group: 'confirmation',
    enabled: allowed && hasFinding,
    why: !hasFinding ? 'This Task names no Finding' : allowed ? undefined : why,
  });
  const cant: TaskAction = { id: 'cant', label: "Can't do", group: 'report', enabled: true, needs: 'note' };
  const reinspect: TaskAction = {
    id: 'reinspect',
    label: `Re-inspect ${task.angle ?? 'Angle'}`,
    group: 'photo',
    enabled: task.angle !== null,
    reinspects: true,
  };
  const falseAlarm = confirm({ id: 'false_alarm', label: 'False alarm…', needs: 'reason' });
  const notFound = confirm({ id: 'not_found', label: 'Not found' });
  const out: TaskAction[] = [];

  switch (task.type) {
    case 'ack_hold': {
      const acknowledged = task.status !== 'assigned';
      if (!acknowledged) out.push(confirm({ id: 'ack', label: 'Acknowledge', primary: true, quick: true }));
      out.push({
        ...confirm({ id: 'removed', label: 'Removed (takes a new photo)', primary: acknowledged, quick: acknowledged, reinspects: true }),
        ...(lead && !acknowledged ? { enabled: false, why: 'Acknowledge first' } : {}),
      });
      out.push(falseAlarm, notFound, reinspect, cant);
      break;
    }
    case 'remove':
    case 'walk_and_report': {
      if (task.status === 'assigned') out.push({ id: 'accept', label: 'Accept', group: 'report', enabled: true, quick: true });
      if (task.status !== 'reported') out.push({ id: 'done', label: 'Done', group: 'report', enabled: true, primary: true, quick: true });
      out.push(cant);
      const hold = sev === 'HOLD';
      out.push(confirm({ id: 'removed', label: hold ? 'Removed (takes a new photo)' : 'Removed', reinspects: hold, primary: task.status === 'reported' && !hold }));
      out.push(falseAlarm, notFound);
      if (!hold) out.push({ id: 'all_removed', label: `Confirm all removed at ${task.gate}`, group: 'confirmation', enabled: true });
      out.push(reinspect);
      break;
    }
    case 'report_outside_boundary':
      out.push(confirm({ id: 'reported', label: 'Reported to Ramp 1 control / Airport Ops', primary: true, quick: true }));
      out.push(falseAlarm, notFound, cant);
      break;
    case 'check_by_eye':
      out.push({ ...reinspect, primary: true, quick: true });
      out.push({
        id: 'eye',
        label: 'Checked by eye',
        group: 'confirmation',
        enabled: lead && task.angle !== null,
        why: lead ? undefined : LEAD_ONLY_EYE,
        quick: true,
      });
      out.push(cant);
      break;
    case 'sign_off':
      out.push({ id: 'signoff', label: `Sign off ${task.gate}`, group: 'confirmation', enabled: true, primary: true, quick: true });
      out.push(cant);
      break;
  }
  return [...out, ...reassign];
}

export type ActionInput = { reason?: FalseAlarmReason; note?: string; personId?: string };

/** The structured command for `POST /api/agent/command`. */
export function actionCommand(action: ActionId, task: Task, input: ActionInput = {}): StructuredCommand {
  const label = task.finding_id ?? '';
  const angle = task.angle ?? '';
  const note = (input.note ?? '').trim();
  switch (action) {
    case 'ack':
      return { command: 'ack', args: [label] };
    case 'removed':
      return { command: 'removed', args: [label] };
    case 'false_alarm':
      return { command: 'false-alarm', args: [label, input.reason ?? 'other'] };
    case 'not_found':
      return { command: 'not-found', args: [label] };
    case 'reported':
      return { command: 'reported', args: [label] };
    case 'all_removed':
      return { command: 'all-removed', args: [task.gate] };
    case 'reinspect':
      return { command: 'reinspect', args: [task.gate, angle] };
    case 'eye':
      return { command: 'eye', args: [task.gate, angle] };
    case 'signoff':
      return { command: 'signoff', args: [task.gate] };
    case 'accept':
      return { command: 'accept', args: [task.task_id] };
    case 'done':
      return { command: 'done', args: note ? [task.task_id, note] : [task.task_id] };
    case 'cant':
      return { command: 'cant', args: note ? [task.task_id, note] : [task.task_id] };
    case 'reassign':
      return { command: 'reassign', args: [task.task_id, input.personId ?? ''] };
  }
}

export const TASK_TYPE_LABEL: Record<Task['type'], string> = {
  ack_hold: 'Acknowledge and clear HOLD',
  remove: 'Remove',
  walk_and_report: 'Walk and report',
  check_by_eye: 'Check Angle by eye',
  report_outside_boundary: 'Report outside the envelope',
  sign_off: 'Sign off Inspection',
};

export const TASK_STATUS_LABEL: Record<string, string> = {
  assigned: 'Assigned',
  accepted: 'Accepted',
  reported: 'Reported, awaiting Confirmation',
  closed: 'Closed',
  cancelled: 'Cancelled',
};

export function taskStatusLabel(task: Pick<Task, 'type' | 'status'>): string {
  if (task.type === 'ack_hold' && task.status === 'assigned') return 'Not acknowledged';
  if (task.type === 'ack_hold' && task.status === 'accepted') return 'Acknowledged';
  return TASK_STATUS_LABEL[task.status] ?? task.status;
}

export function escalationLabel(level: number): string | null {
  if (level <= 0) return null;
  return level === 1 ? 'Escalated: second call' : `Escalated: level ${level}`;
}

/** Active Tasks first (HOLDs, then escalated, then oldest), closed ones last (newest first). */
export function sortTasks(tasks: Task[]): Task[] {
  const rank = (t: Task) => (isActiveTask(t) ? (t.severity === 'HOLD' ? 0 : t.escalation_level > 0 ? 1 : 2) : 3);
  return [...tasks].sort((a, b) => {
    const d = rank(a) - rank(b);
    if (d !== 0) return d;
    const byTime = a.created_at.localeCompare(b.created_at);
    return rank(a) === 3 ? -byTime : byTime;
  });
}

/** "45 s", "3 min", "1 h 05 min". */
export function formatAge(iso: string, now: number): string {
  const ms = now - new Date(iso).getTime();
  if (!Number.isFinite(ms)) return '';
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`;
}
