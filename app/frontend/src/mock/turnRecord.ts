/**
 * The Turn record in mock mode (GET /api/turns/{turn_id}/record), built from
 * the mock backend's Inspections and store events and the mock dispatcher's
 * activity log (its Tasks, Reports and Confirmations). Read-only: building a
 * record changes nothing.
 *
 * Times: the mock backend stamps Inspections in gate time (BASE_TIME plus
 * demo seconds x GATE_TIME_SCALE), and the dispatcher logs demo seconds (`t`).
 * Every entry's `at` is derived from demo seconds the same way, so the two
 * sources sort on one clock.
 *
 * Sample entries: the mock dispatcher starts at demo time 0, so a Turn that was
 * signed off before then (a Turn "already under way") has no Task or Report.
 * For each such sign-off this file adds a sample sign-off Task, an accept
 * Report and a done Report, marked `data.sample: true`. The Confirmation
 * itself is the real one from the mock backend. At load, T2-DL2210,
 * T5-DL1776 and T8-DL1907 each have an Inspection, a Task, a Report and a
 * Confirmation.
 */
import { ApiError } from '../api/client';
import type { ActivityEntry, RosterPerson } from '../api/agentTypes';
import type { Report } from '../api/types';
import type { TurnRecord, TurnRecordEntry, TurnRecordPerson, TurnRecordRefs } from '../api/turnRecordTypes';
import { KIND_LABEL, VERDICT_LABEL } from '../lib/labels';
import { costSummary } from '../lib/report';
import { personRoleLabel } from '../lib/labels';
import { orderEntries } from '../lib/turnRecord';
import { BASE_TIME, GATE_TIME_SCALE, type MockBackend, type MockStoreEvent } from './backend';
import type { MockDispatcher } from './dispatch';

type Draft = Omit<TurnRecordEntry, 'seq'>;

/** Mock dispatcher Report kinds -> the record's report events. */
const REPORT_EVENT: Record<string, string> = { accepted: 'accept', done: 'done', not_found: 'not_found', blocked: 'cant', note: 'note' };
const STORE_CONFIRMATION: Partial<Record<MockStoreEvent['type'], string>> = {
  finding_acknowledged: 'acknowledged',
  angle_checked_by_eye: 'checked_by_eye',
  inspection_signed_off: 'signoff',
};

const isoAt = (t: number) => new Date(BASE_TIME + t * GATE_TIME_SCALE * 1000).toISOString();
const tOf = (iso: string) => Math.round(((Date.parse(iso) - BASE_TIME) / (GATE_TIME_SCALE * 1000)) * 10) / 10;
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const refs = (r: Partial<TurnRecordRefs> = {}): TurnRecordRefs => ({
  inspection_id: r.inspection_id ?? null,
  task_id: r.task_id ?? null,
  finding_id: r.finding_id ?? null,
  angle: r.angle ?? null,
});

type TaskInfo = { type: string | null; inspection_id: string | null; finding_id: string | null; angle: string | null; assignee_id: string | null };

export function buildMockTurnRecord(backend: MockBackend, dispatcher: MockDispatcher, turnId: string): TurnRecord {
  const turn = backend.turn(turnId);
  if (!turn) throw new ApiError('not_found', `Turn ${turnId} not found.`, 404);

  const roster = dispatcher.roster().people;
  const byId = new Map<string, RosterPerson>(roster.map((p) => [p.person_id, p]));
  const personById = (id: string | null | undefined): TurnRecordPerson | null => {
    const p = id ? byId.get(id) : undefined;
    return p ? { person_id: p.person_id, name: p.name, role: p.role } : null;
  };
  const personByName = (by: { name?: unknown; role?: unknown } | undefined): TurnRecordPerson | null => {
    const name = str(by?.name);
    if (!name) return null;
    const p = roster.find((x) => x.name === name);
    return { person_id: p?.person_id ?? null, name, role: str(by?.role) ?? p?.role ?? null };
  };
  const nameRole = (p: TurnRecordPerson | null) => (p ? `${p.name ?? p.person_id}${p.role ? ` (${personRoleLabel(p.role)})` : ''}` : 'nobody');

  const reports = backend.reportsForTurn(turnId);
  const drafts: Draft[] = [];

  // 1. Inspections, from the mock backend.
  for (const rep of reports) {
    drafts.push(...inspectionEntries(rep, turn.flight));
  }

  // 2. Confirmations recorded before the dispatcher started, with sample Tasks and Reports.
  for (const e of backend.events) {
    if (e.turn_id !== turnId || e.t >= 0) continue;
    const event = e.type === 'finding_confirmed' ? (e.data.outcome ?? 'confirmed') : STORE_CONFIRMATION[e.type];
    if (!event) continue;
    const person = personByName(e.data.by);
    if (e.type === 'inspection_signed_off') drafts.push(...sampleSignoffTask(e, person, nameRole(person)));
    drafts.push({
      at: isoAt(e.t),
      t: e.t,
      kind: 'confirmation',
      event,
      person,
      text:
        event === 'signoff'
          ? `Recorded: Inspection signed off by ${nameRole(person)}. ${e.gate} confirmed clear.`
          : `Recorded: ${e.data.finding_id ?? e.data.angle ?? ''} ${event.replace(/_/g, ' ')} by ${nameRole(person)}.`.replace(/ {2,}/g, ' '),
      refs: refs({ inspection_id: e.data.inspection_id ?? null, finding_id: e.data.finding_id ?? null, angle: e.data.angle ?? null }),
      data: { action: event, by: e.data.by ?? null, via: null },
    });
    if (e.type === 'inspection_signed_off') {
      drafts.push({
        at: isoAt(e.t),
        t: e.t,
        kind: 'task',
        event: 'closed',
        person,
        text: `${sampleTaskId(e.gate)} closed: signed off. Timers cancelled.`,
        refs: refs({ inspection_id: e.data.inspection_id ?? null, task_id: sampleTaskId(e.gate) }),
        data: { reason: 'signed off', sample: true },
      });
    }
  }

  // 3. Tasks, Reports and Confirmations, from the mock dispatcher's activity log.
  const log = dispatcher.activity({ turn_id: turnId, limit: 1000 }).entries;
  const tasks = new Map<string, TaskInfo>();
  // The dispatcher logs a Confirmation when it sees it. After a jump (?t=120) that is long after it was
  // recorded, so a Confirmation takes the time of the mock backend's own event.
  const used = new Set<number>();
  const recordedT = (d: Record<string, unknown>, by: { name?: unknown }): number | null => {
    const e = backend.events.find(
      (x) =>
        !used.has(x.id) &&
        x.t >= 0 &&
        x.turn_id === turnId &&
        x.data.inspection_id === d.inspection_id &&
        (x.data.angle ?? null) === (d.angle ?? null) &&
        x.data.by?.name === by.name &&
        (STORE_CONFIRMATION[x.type] ?? (x.type === 'finding_confirmed' ? x.data.outcome : undefined)) === d.action,
    );
    if (!e) return null;
    used.add(e.id);
    return e.t;
  };
  let agentUsd = 0;
  for (const entry of log) {
    if (entry.event === 'agent_wake') agentUsd += Number(entry.data.est_cost_usd) || 0;
    drafts.push(...activityEntries(entry, tasks, personById, personByName, recordedT));
  }

  const inspectionsUsd = reports.reduce((sum, r) => sum + costSummary(r.run_metadata).costUsd, 0);
  const round = (n: number) => Number(n.toFixed(6));
  return {
    turn_id: turn.turn_id,
    gate: turn.gate,
    flight: turn.flight,
    generated_at: isoAt(dispatcher.clock()),
    cost: {
      inspections_usd: round(inspectionsUsd),
      agent_usd: round(agentUsd),
      total_usd: round(inspectionsUsd + agentUsd),
      note: 'Mock mode: no model is called; the figures are illustrative. Agent cost counts the agent wakes tied to this Turn.',
    },
    entries: orderEntries(drafts).map((d, seq) => ({ seq, ...d })),
  };
}

function inspectionEntries(rep: Report, flight: string): Draft[] {
  const reinspection = rep.kind === 'on_demand' && rep.parent_inspection_id !== null;
  const kindText = reinspection ? 'Re-inspection' : KIND_LABEL[rep.kind];
  const base = { kind: 'inspection', person: null, refs: refs({ inspection_id: rep.inspection_id }) } as const;
  const out: Draft[] = [
    {
      ...base,
      at: rep.captured_at,
      t: tOf(rep.captured_at),
      event: reinspection ? 'reinspected' : 'started',
      text: `${rep.gate} ${flight} ${kindText} started (${rep.inspection_id}).`,
      data: { inspection_kind: rep.kind, parent_inspection_id: rep.parent_inspection_id },
    },
  ];
  if (rep.analysed_at) {
    const cost = costSummary(rep.run_metadata).costUsd;
    out.push({
      ...base,
      at: rep.analysed_at,
      t: tOf(rep.analysed_at),
      event: 'completed',
      text: `${rep.gate} ${flight} ${kindText} done. Verdict ${rep.verdict ? VERDICT_LABEL[rep.verdict] : 'none'} (advisory).`,
      data: {
        inspection_kind: rep.kind,
        verdict: rep.verdict,
        highest_open_severity: rep.highest_open_severity,
        findings: rep.findings.length,
        est_cost_usd: Number(cost.toFixed(6)),
      },
    });
  }
  return out;
}

const sampleTaskId = (gate: string) => `K-pre-${gate}`;

/** A sample sign-off Task with an accept Report and a done Report, just before a sign-off recorded before the dispatcher started. */
function sampleSignoffTask(e: MockStoreEvent, person: TurnRecordPerson | null, who: string): Draft[] {
  const taskId = sampleTaskId(e.gate);
  const r = refs({ inspection_id: e.data.inspection_id ?? null, task_id: taskId });
  const at = (dt: number) => ({ at: isoAt(e.t - dt), t: Math.round((e.t - dt) * 10) / 10 });
  return [
    {
      ...at(3),
      kind: 'task',
      event: 'assigned',
      person,
      text: `${taskId} sign off ${e.gate} -> ${who}.`,
      refs: r,
      data: { task_type: 'sign_off', created_by: 'code', instruction: `Sign off the Inspection at ${e.gate}`, sample: true },
    },
    {
      ...at(2),
      kind: 'report',
      event: 'accept',
      person,
      text: `Report on ${taskId} by ${person?.name ?? 'nobody'}: accepted (command).`,
      refs: r,
      data: { raw_text: null, via: 'command', sample: true },
    },
    {
      ...at(1),
      kind: 'report',
      event: 'done',
      person,
      text: `Report on ${taskId} by ${person?.name ?? 'nobody'}: done (agent).`,
      refs: r,
      data: { raw_text: 'Walked the stand. All six Angles look clean, signing off now.', via: 'agent', sample: true },
    },
  ];
}

function activityEntries(
  entry: ActivityEntry,
  tasks: Map<string, TaskInfo>,
  personById: (id: string | null | undefined) => TurnRecordPerson | null,
  personByName: (by: { name?: unknown; role?: unknown } | undefined) => TurnRecordPerson | null,
  recordedT: (d: Record<string, unknown>, by: { name?: unknown }) => number | null,
): Draft[] {
  const d = entry.data;
  const at = isoAt(entry.t);
  const taskRefs = (taskId: string | null): TurnRecordRefs => {
    const info = taskId ? tasks.get(taskId) : undefined;
    return refs({ inspection_id: info?.inspection_id, task_id: taskId, finding_id: info?.finding_id, angle: info?.angle });
  };
  const task = (event: string, taskId: string | null, data: Record<string, unknown>, text = entry.text): Draft => ({
    at,
    t: entry.t,
    kind: 'task',
    event,
    person: personById(taskId ? tasks.get(taskId)?.assignee_id : null),
    text,
    refs: taskRefs(taskId),
    data: { task_type: taskId ? tasks.get(taskId)?.type : null, finding_label: taskId ? tasks.get(taskId)?.finding_id : null, ...data, by: entry.actor },
  });

  switch (entry.event) {
    case 'task_assigned': {
      const taskId = str(d.task_id);
      if (!taskId) return [];
      tasks.set(taskId, {
        type: str(d.type),
        inspection_id: str(d.inspection_id),
        finding_id: str(d.finding_id),
        angle: str(d.angle),
        assignee_id: str(d.assignee_id),
      });
      return [task('assigned', taskId, { severity: d.severity, instruction: d.instruction, created_by: d.created_by })];
    }
    case 'task_reassigned': {
      const taskId = str(d.task_id);
      const info = taskId ? tasks.get(taskId) : undefined;
      if (info) info.assignee_id = str(d.to);
      return [task('reassigned', taskId, { from: d.from, to: d.to, reason: d.reason })];
    }
    case 'task_escalated':
      return [task('escalated', str(d.task_id), { level: d.level, reason: d.reason, notified: d.notified })];
    case 'task_reopened':
      return [task('reopened', str(d.task_id), {})];
    case 'task_closed':
    case 'task_cancelled': {
      const ids = Array.isArray(d.task_ids) ? d.task_ids.filter((x): x is string => typeof x === 'string') : [];
      const event = entry.event === 'task_closed' ? 'closed' : 'cancelled';
      return ids.map((id) =>
        task(event, id, { reason: d.reason, confirmation_id: d.confirmation_id ?? null }, `${id} ${event}: ${String(d.reason ?? '')}.`),
      );
    }
    case 'task_accepted':
    case 'task_reported': {
      const taskId = str(d.task_id);
      const kind = str(d.kind) ?? '';
      return [
        {
          at,
          t: entry.t,
          kind: 'report',
          event: REPORT_EVENT[kind] ?? kind,
          person: personById(entry.actor),
          text: entry.text,
          refs: taskRefs(taskId),
          data: { raw_text: d.raw_text ?? null, via: d.via ?? null, report_kind: kind },
        },
      ];
    }
    case 'confirmation': {
      const by = (typeof d.by === 'object' && d.by !== null ? d.by : {}) as { name?: unknown; role?: unknown };
      const t = recordedT(d, by) ?? entry.t;
      return [
        {
          at: isoAt(t),
          t,
          kind: 'confirmation',
          event: str(d.action) ?? 'recorded',
          person: personByName(by),
          text: entry.text,
          refs: refs({ inspection_id: str(d.inspection_id), finding_id: str(d.finding_id), angle: str(d.angle) }),
          data: { action: d.action ?? null, by: d.by ?? null, via: null, finding_label: str(d.finding_id) },
        },
      ];
    }
    default:
      return [];
  }
}
