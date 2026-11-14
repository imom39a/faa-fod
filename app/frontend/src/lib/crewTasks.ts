/**
 * The Crew and Tasks view: a read-only picture of GET /api/agent/board.
 * Pure functions only, so the ordering and the unknown-Task-type case can be
 * tested without a browser.
 *
 * A Task's `type` is a closed union in agentTypes.ts, but other tickets add
 * new types on the server. Everything here accepts any string at runtime and
 * never throws on a type, status, role or severity it does not know.
 */
import type { ActivityEntry, Board, RosterPerson, Task } from '../api/agentTypes';
import { turnHref } from '../route';
import { humanise, personRoleLabel } from './labels';
import { formatAge, isActiveTask, taskStatusLabel, TASK_TYPE_LABEL } from './taskActions';

export type BoardTask = Board['tasks'][number];
export type BoardPerson = Board['roster'][number];

/** HOLD > REMOVE > ADVISORY > no severity or an unknown one. */
const SEVERITY_RANK: Record<string, number> = { HOLD: 0, REMOVE: 1, ADVISORY: 2 };
const severityRank = (t: Pick<Task, 'severity'>) => SEVERITY_RANK[t.severity ?? ''] ?? 3;
const level = (t: Pick<Task, 'escalation_level'>) => (Number.isFinite(t.escalation_level) ? t.escalation_level : 0);
const time = (iso: string | null | undefined) => {
  const ms = iso ? Date.parse(iso) : NaN;
  return Number.isNaN(ms) ? Number.POSITIVE_INFINITY : ms;
};
/** "K-2" before "K-10". */
const byTaskId = (a: string, b: string) => a.localeCompare(b, 'en', { numeric: true });

/**
 * The order of the Crew and Tasks list. Each rule applies only when every rule
 * before it is a tie:
 *
 * 1. Open Tasks (assigned, accepted, reported) before closed or cancelled ones.
 * 2. HOLD Tasks first ("Needs a human" queue in spec/dashboard-ux.md: HOLDs first).
 * 3. Higher Escalation level first.
 * 4. Severity: REMOVE, then ADVISORY, then no severity or an unknown one.
 * 5. Open Tasks: oldest `created_at` first (it has waited longest).
 *    Closed Tasks: most recently closed first.
 * 6. `task_id`, in natural order ("K-2" before "K-10"), so the order never flickers.
 *
 * This differs from `sortTasks` in lib/taskActions.ts on purpose: that one
 * orders one person's own list on the chat page.
 */
export function sortCrewTasks<T extends Task>(tasks: readonly T[]): T[] {
  return [...tasks].sort((a, b) => {
    const openA = isActiveTask(a);
    const openB = isActiveTask(b);
    if (openA !== openB) return openA ? -1 : 1;
    const holdA = a.severity === 'HOLD';
    const holdB = b.severity === 'HOLD';
    if (holdA !== holdB) return holdA ? -1 : 1;
    const esc = level(b) - level(a);
    if (esc !== 0) return esc;
    const sev = severityRank(a) - severityRank(b);
    if (sev !== 0) return sev;
    // A missing or invalid time sorts after every valid one.
    const ta = time(openA ? a.created_at : (a.closed_at ?? a.created_at));
    const tb = time(openA ? b.created_at : (b.closed_at ?? b.created_at));
    if (ta !== tb) {
      if (!Number.isFinite(ta)) return 1;
      if (!Number.isFinite(tb)) return -1;
      return openA ? ta - tb : tb - ta;
    }
    return byTaskId(a.task_id, b.task_id);
  });
}

export function openTasks<T extends Task>(tasks: readonly T[]): T[] {
  return sortCrewTasks(tasks.filter((t) => isActiveTask(t)));
}

/** The last few closed or cancelled Tasks, most recently closed first. */
export function recentlyClosedTasks<T extends Task>(tasks: readonly T[], limit = 8): T[] {
  return sortCrewTasks(tasks.filter((t) => !isActiveTask(t))).slice(0, limit);
}

/** Open Tasks that have been escalated, highest level first. */
export function escalationsInProgress<T extends Task>(tasks: readonly T[]): T[] {
  return openTasks(tasks)
    .filter((t) => level(t) > 0)
    .sort((a, b) => level(b) - level(a) || time(a.created_at) - time(b.created_at) || byTaskId(a.task_id, b.task_id));
}

export type TaskTypeInfo = {
  /** What the Task is, in words. For a type this dashboard does not know, the raw type name. */
  label: string;
  /** False for a type added on the server after this dashboard was built. */
  known: boolean;
  /** The type exactly as the server sent it. */
  raw: string;
};

export function taskTypeInfo(task: { type?: unknown }): TaskTypeInfo {
  const raw = typeof task.type === 'string' ? task.type.trim() : '';
  const known = Object.prototype.hasOwnProperty.call(TASK_TYPE_LABEL, raw);
  if (known) return { label: TASK_TYPE_LABEL[raw as Task['type']], known, raw };
  return { label: raw || 'Task of no stated type', known: false, raw };
}

/** The server's instruction for the Task, or an empty string. */
export function taskInstruction(task: { instruction?: unknown }): string {
  return typeof task.instruction === 'string' ? task.instruction.trim() : '';
}

/**
 * The part of the instruction a row shows under the Task type. Instructions start by
 * restating the Task ("Acknowledge and clear the HOLD at T5 ENG-R: Hammer on ...");
 * the row already shows that, so it keeps what follows the first ": ". An instruction
 * without that shape is shown whole.
 */
export function taskDetail(instruction: string): string {
  const i = instruction.indexOf(': ');
  if (i <= 0 || i > 80) return instruction;
  const rest = instruction.slice(i + 2).trim();
  return rest || instruction;
}

/** Status in words; an unknown status is shown as the server sent it. */
export function crewStatusLabel(task: Pick<Task, 'type' | 'status'>): string {
  const status = typeof task.status === 'string' ? task.status : '';
  return taskStatusLabel({ type: task.type, status }) || humanise(status) || 'No status';
}

/** What an Escalation level means (spec/dispatch.md, "Escalation ladder"). */
export function escalationWho(level: number): string {
  if (level <= 0) return '';
  if (level === 1) return 'Second call; the supervisor is told';
  return 'Every Ramp Lead on Shift and the supervisor are told';
}

/** "Escalated · level 2", or null for a Task that is not escalated. */
export function crewEscalationLabel(escalationLevel: number): string | null {
  const n = Number.isFinite(escalationLevel) ? Math.floor(escalationLevel) : 0;
  return n > 0 ? `Escalated · level ${n}` : null;
}

/** "Level 2", or null for a Task that is not escalated. */
export function escalationLevelLabel(escalationLevel: number): string | null {
  const n = Number.isFinite(escalationLevel) ? Math.floor(escalationLevel) : 0;
  return n > 0 ? `Level ${n}` : null;
}

/** Where in its Turn a Task points: the Finding's label, the Angle, or the whole Inspection. */
export function taskTarget(task: Pick<Task, 'finding_id' | 'angle'>): string {
  if (task.finding_id) return `Finding ${task.finding_id}`;
  if (task.angle) return `Angle ${task.angle}`;
  return 'Inspection';
}

/**
 * The Turn and Finding a Task belongs to: the Turn view at the Task's
 * Inspection, with `?finding=<id>` naming the Finding by its ID in that
 * Inspection (`inspection_finding_id`), which the Turn view selects. The
 * short label (`finding_id`, "F1") cannot be looked up there, so a server
 * without that field gets a link to the Inspection only.
 */
export function taskHref(task: Pick<Task, 'turn_id' | 'inspection_id' | 'inspection_finding_id'>): string {
  const inspectionId = task.inspection_id || null;
  return turnHref(task.turn_id, inspectionId, inspectionId ? task.inspection_finding_id : null);
}

/** "45 s", "3 min", "1 h 05 min" since `iso` (formatAge in lib/taskActions); empty for a missing or bad timestamp. */
export function openFor(iso: string | null | undefined, now: number): string {
  return iso ? formatAge(iso, now) : '';
}

/** "Okafor (Ramp Lead)", the raw person_id when the Roster does not know it, or "Unassigned". */
export function assigneeLabel(assigneeId: string | null, roster: readonly Pick<RosterPerson, 'person_id' | 'name' | 'role'>[]): string {
  if (!assigneeId) return 'Unassigned';
  const p = roster.find((x) => x.person_id === assigneeId);
  return p ? `${p.name} (${personRoleLabel(p.role)})` : assigneeId;
}

const ROLE_ORDER: Record<string, number> = { ramp_lead: 0, ramp_agent: 1, supervisor: 2 };

export type RosterGroups<P extends RosterPerson> = { onShift: P[]; onBreak: P[]; offShift: P[] };

/** People on shift, on a break and off shift; within each, Ramp Leads, Ramp Agents, then supervisors, by name. */
export function groupRoster<P extends RosterPerson>(roster: readonly P[]): RosterGroups<P> {
  const sorted = [...roster].sort(
    (a, b) => (ROLE_ORDER[a.role] ?? 3) - (ROLE_ORDER[b.role] ?? 3) || a.name.localeCompare(b.name) || a.person_id.localeCompare(b.person_id),
  );
  return {
    onShift: sorted.filter((p) => p.shift === 'on'),
    onBreak: sorted.filter((p) => p.shift === 'break'),
    // Off shift, or a Shift value this dashboard does not know.
    offShift: sorted.filter((p) => p.shift !== 'on' && p.shift !== 'break'),
  };
}

/** The newest activity entries first, at most `limit`. */
export function recentActivity(entries: readonly ActivityEntry[], limit = 15): ActivityEntry[] {
  return [...entries].sort((a, b) => b.id - a.id).slice(0, limit);
}

/** Seconds until a Task's next timer fires on the demo clock, or null when none is set. */
export function nextTimerIn(taskId: string, timers: Board['timers'], clockT: number): number | null {
  const due = timers.filter((t) => t.task_id === taskId).map((t) => t.fire_t - clockT);
  return due.length ? Math.max(0, Math.min(...due)) : null;
}
