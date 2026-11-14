/** The activity log: grouping entries into kinds, working out who and where, and filtering. */
import type { ActivityEntry, RosterPerson } from '../api/agentTypes';
import { personRoleLabel } from './labels';

export type ActivityCategory =
  | 'inspection'
  | 'task'
  | 'report'
  | 'confirmation'
  | 'refusal'
  | 'shift'
  | 'message'
  | 'proposal'
  | 'timer'
  | 'agent'
  | 'system';

export const CATEGORY_LABEL: Record<ActivityCategory, string> = {
  inspection: 'Inspection',
  task: 'Task',
  report: 'Report',
  confirmation: 'Confirmation',
  refusal: 'Refusal',
  shift: 'Shift / Handover',
  message: 'Message',
  proposal: 'Proposal',
  timer: 'Timer / Escalation',
  agent: 'Agent wake',
  system: 'System',
};

export const CATEGORY_ORDER: readonly ActivityCategory[] = [
  'inspection',
  'task',
  'report',
  'confirmation',
  'refusal',
  'shift',
  'proposal',
  'timer',
  'message',
  'agent',
  'system',
];

const BY_EVENT: Record<string, ActivityCategory> = {
  inspection_completed: 'inspection',
  departed: 'inspection',
  task_assigned: 'task',
  task_closed: 'task',
  task_cancelled: 'task',
  task_reassigned: 'task',
  task_reopened: 'task',
  hold_alert: 'task',
  unroutable: 'task',
  // A Handover moves Tasks between people and a Shift says who is available. Neither confirms anything.
  handover_requested: 'shift',
  handover_declined: 'shift',
  handover_expired: 'shift',
  handover: 'shift',
  shift_changed: 'shift',
  sole_lead_leaving: 'shift',
  // A Report is what a person said about a Task. It never changes a Finding.
  task_accepted: 'report',
  task_reported: 'report',
  // A Confirmation is recorded on the Inspection by a named person.
  confirmation: 'confirmation',
  // Who an outside-envelope Finding was reported to: written with the Confirmation that records it.
  outside_reported: 'confirmation',
  command_refused: 'refusal',
  message: 'message',
  proposal_created: 'proposal',
  proposal_answered: 'proposal',
  task_escalated: 'timer',
  timer_fired: 'timer',
  agent_wake_started: 'agent',
  agent_wake: 'agent',
  agent_tool: 'agent',
  agent_note: 'agent',
  agent_wake_failed: 'agent',
  model_unavailable: 'agent',
  free_text_not_interpreted: 'agent',
};

export function activityCategory(entry: Pick<ActivityEntry, 'event'>): ActivityCategory {
  return BY_EVENT[entry.event] ?? 'system';
}

const str = (v: unknown): string[] => (typeof v === 'string' && v ? [v] : []);
const list = (v: unknown): string[] => (Array.isArray(v) ? v.flatMap(str) : []);

/** person_ids an entry involves: who did it, who it was sent to, who was told. */
export function entryPeople(entry: ActivityEntry, roster: Pick<RosterPerson, 'person_id' | 'name'>[]): string[] {
  const d = entry.data ?? {};
  const by = d.by && typeof d.by === 'object' ? (d.by as { name?: unknown }).name : undefined;
  const raw = [
    entry.actor,
    ...str(d.from),
    ...str(d.to),
    ...str(d.assignee_id),
    ...str(d.person_id),
    ...str(by),
    ...list(d.notified),
    ...list(d.delivered_to),
  ];
  const out = new Set<string>();
  for (const r of raw) {
    const key = r.trim().toLowerCase();
    // A Confirmation names the person ("Okafor"); everything else uses the person_id.
    const p = roster.find((x) => x.person_id === key || x.name.toLowerCase() === key);
    if (p) out.add(p.person_id);
  }
  return [...out];
}

export type ActivityFilter = {
  gate?: string | null;
  turnId?: string | null;
  personId?: string | null;
  category?: ActivityCategory | null;
};

export function filterActivity(
  entries: ActivityEntry[],
  filter: ActivityFilter,
  roster: Pick<RosterPerson, 'person_id' | 'name'>[] = [],
): ActivityEntry[] {
  return entries.filter(
    (e) =>
      (!filter.gate || e.gate === filter.gate) &&
      (!filter.turnId || e.turn_id === filter.turnId) &&
      (!filter.category || activityCategory(e) === filter.category) &&
      (!filter.personId || entryPeople(e, roster).includes(filter.personId)),
  );
}

/** Add newly polled entries: no duplicates, oldest first. */
export function mergeActivity(existing: ActivityEntry[], incoming: ActivityEntry[]): ActivityEntry[] {
  if (incoming.length === 0) return existing;
  const seen = new Set(existing.map((e) => e.id));
  const fresh = incoming.filter((e) => !seen.has(e.id));
  if (fresh.length === 0) return existing;
  return [...existing, ...fresh].sort((a, b) => a.id - b.id);
}

/** The Gates and Turns that appear in the log, for the filter pickers. */
export function activityFacets(entries: ActivityEntry[]): { gates: string[]; turns: { turn_id: string; gate: string | null }[] } {
  const gates = new Set<string>();
  const turns = new Map<string, string | null>();
  for (const e of entries) {
    if (e.gate) gates.add(e.gate);
    if (e.turn_id && !turns.get(e.turn_id)) turns.set(e.turn_id, e.gate);
  }
  return {
    gates: [...gates].sort(),
    turns: [...turns].map(([turn_id, gate]) => ({ turn_id, gate })).sort((a, b) => a.turn_id.localeCompare(b.turn_id)),
  };
}

/** The Inspection an entry is about, when it names one. */
export function entryInspectionId(entry: ActivityEntry): string | null {
  const id = entry.data?.inspection_id;
  return typeof id === 'string' && id ? id : null;
}

/** "kim> /ack F1" and "code to kim: ..." are console wording; the page shows who and what separately. */
export function entryText(entry: ActivityEntry): string {
  if (entry.event !== 'message') return entry.text;
  return entry.text.replace(/^[\w-]+> /, '').replace(/^[\w-]+ to [\w-]+: /, '');
}

/** Who did an entry: System, Agent, Timer, "Okafor (Ramp Lead)", or the actor as sent. */
export function actorLabel(actor: string, roster: readonly Pick<RosterPerson, 'person_id' | 'name' | 'role'>[]): string {
  if (actor === 'code') return 'System';
  if (actor === 'agent') return 'Agent';
  if (actor === 'timer') return 'Timer';
  // A Confirmation names the person ("Okafor"); everything else uses the person_id.
  const p = roster.find((x) => x.person_id === actor.toLowerCase() || x.name === actor);
  return p ? `${p.name} (${personRoleLabel(p.role)})` : actor;
}
