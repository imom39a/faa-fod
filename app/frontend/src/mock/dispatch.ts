/**
 * In-memory mock of the always-on agent (`/api/agent/*`): roster and PIN
 * sign-in, Tasks, Reports, messages, proposals, timers, Escalation and the
 * activity log. It follows app/backend/fodgate/dispatch/ rule for rule and
 * returns the same shapes, so the chat and activity pages need no change to run
 * against the real backend.
 *
 * Every Confirmation still goes through MockBackend as the signed-in person.
 * No model is called: the "agent" here is a few fixed patterns over free text,
 * and its cost figures are illustrative.
 *
 * It has no timers of its own: the caller advances the clock (`tick`).
 */
import { ApiError } from '../api/client';
import type {
  ActivityEntry,
  ActivityQuery,
  ActivityResponse,
  AgentCost,
  Board,
  ChatMessage,
  CommandResult,
  Inbox,
  JoinResponse,
  PersonRole,
  Proposal,
  RosterPerson,
  RosterResponse,
  SayResult,
  ShiftStatus,
  Task,
  TaskReport,
  TaskType,
} from '../api/agentTypes';
import { ANGLE_ORDER, type AngleName, type FalseAlarmReason, type Finding, type Report, type Role } from '../api/types';
import { GATE_TIME_SCALE, MockBackend, RULES, isOpen, type MockStoreEvent, type MockTurnInfo } from './backend';
import { GATES } from './fixtures';

/** Demo roster, as app/data/roster/roster.json. The PINs stand in for sign-in and are not secrets. */
export const MOCK_ROSTER: { person_id: string; name: string; role: PersonRole; gates: string[]; pin: string; shift: ShiftStatus }[] = [
  { person_id: 'kim', name: 'Kim', role: 'ramp_agent', gates: ['T5', 'T8'], pin: '1111', shift: 'on' },
  { person_id: 'okafor', name: 'Okafor', role: 'ramp_lead', gates: ['T5', 'T8'], pin: '2222', shift: 'on' },
  { person_id: 'patel', name: 'Patel', role: 'ramp_agent', gates: ['T1', 'T2', 'T4'], pin: '3333', shift: 'on' },
  { person_id: 'reyes', name: 'Reyes', role: 'ramp_lead', gates: ['T1', 'T2', 'T4'], pin: '4444', shift: 'on' },
  { person_id: 'dana', name: 'Dana', role: 'supervisor', gates: ['T1', 'T2', 'T4', 'T5', 'T8'], pin: '9999', shift: 'on' },
];

/** Seconds are demo-clock seconds, as in the backend's escalation ladder. */
export const LADDER = {
  hold_unacknowledged_s: [30, 60] as const,
  hold_pushback_under_min: 2,
  no_report_ask_s: 60,
  no_report_offer_s: 120,
  proposal_expires_s: 120,
};

const MOCK_MODEL = 'claude-haiku-5-5 (mock)';
const SIGNED_IN_WINDOW_MS = 15_000;
const MAX_LEVEL = 2;
const ACTIVE = ['assigned', 'accepted', 'reported'];
const ROLE_LABEL: Record<PersonRole, string> = { ramp_agent: 'Ramp Agent', ramp_lead: 'Ramp Lead', supervisor: 'Supervisor' };
const LEAD_ONLY: TaskType[] = ['ack_hold', 'check_by_eye', 'sign_off'];
const FINDING_TASKS: TaskType[] = ['ack_hold', 'remove', 'walk_and_report', 'report_outside_boundary'];
const TYPE_LABEL: Record<TaskType, string> = {
  ack_hold: 'acknowledge HOLD',
  remove: 'remove',
  walk_and_report: 'walk and report',
  check_by_eye: 'check by eye',
  report_outside_boundary: 'report outside the envelope',
  sign_off: 'sign off',
};
const FALSE_ALARM_REASONS = ['shadow', 'marking', 'equipment_in_place', 'other'];
const ANSWERS: Record<string, boolean> = { y: true, yes: true, '/y': true, '/yes': true, n: false, no: false, '/n': false, '/no': false };

const HELP: Record<PersonRole, string[]> = {
  ramp_agent: [
    '/tasks                      your open Tasks',
    '/accept K-3                 say you are on it',
    '/done K-3 [note]            report it done (a Report, not a Confirmation)',
    '/cant K-3 <reason>          say you cannot do it',
    '/removed F2                 record a REMOVE or ADVISORY Finding as removed',
    '/false-alarm F2 <reason>    shadow | marking | equipment_in_place | other',
    '/not-found F2               record that you walked it and found nothing',
    '/all-removed T5             record every open REMOVE and ADVISORY Finding at a Gate as removed',
    '/reinspect T5 ENG-R         take a new photo of one Angle',
    "/signoff T5                 sign off the Gate's latest Inspection",
    'y / n                       answer the question the agent asked you',
    '/handover <person>  /break  /back  /who',
    'Anything else you type goes to the agent as free text.',
  ],
  ramp_lead: [
    '/ack F1                     acknowledge a HOLD: someone is going to it',
    '/removed F1                 record a HOLD as removed (takes a new photo; clears only if it is clean)',
    '/eye T4 ENG-R               record an unusable Angle as checked by eye',
    '/reported F3                record debris outside the envelope as reported',
    '/reassign K-3 <person>      move a Task',
  ],
  supervisor: [
    '/tasks  /who                every open Task; the roster',
    '/reassign K-3 <person>      move a Task',
    '/shift <person> on|break|off',
    '/msg <person> <text>        send a message to one person',
    'A supervisor does not record Confirmations.',
  ],
};

type PersonRow = { person_id: string; name: string; role: PersonRole; gates: string[]; pin: string; shift: ShiftStatus };
type TaskRow = Task & { seq: number; reports: TaskReport[] };
type ProposalAction = {
  kind: 'confirm' | 'reinspect' | 'handover';
  text: string;
  label?: string;
  outcome?: string;
  false_alarm_reason?: string | null;
  finding_status?: string;
  gate?: string;
  angle?: string;
  turn_id?: string;
  from_id?: string;
};
type ProposalRow = {
  proposal_id: string;
  to_id: string;
  action: ProposalAction;
  status: string;
  created_by: string;
  created_at: string;
  expires_t: number;
};
type TimerRow = { id: number; task_id: string; kind: string; fire_t: number; fired: boolean; cancelled: boolean };
type Ref = { label: string; turn_id: string; gate: string; key: string };
type Needed = { type: TaskType; label: string | null; angle: AngleName | null; finding: Finding | null };
type Wake = { person_id: string; message_id: number; text: string };
type LogOptions = {
  event: string;
  task?: { gate: string; turn_id: string } | null;
  turn?: { gate?: string; turn_id: string } | null;
  gate?: string | null;
  actor?: string;
  data?: Record<string, unknown>;
};
/** What `beginCommand` hands to `finishCommand`. */
export type PendingCommand = { person: PersonRow; text: string; reinspects: boolean };

class DispatchError extends Error {}

function fail(status: number, code: string, message: string): never {
  throw new ApiError(code, message, status);
}

function bad(message: string): never {
  fail(422, 'invalid_command', message);
}

function short(text: string, limit = 90): string {
  const t = String(text).split(/\s+/).filter(Boolean).join(' ');
  return t.length <= limit ? t : `${t.slice(0, limit - 1)}…`;
}

const requiredRole = (type: TaskType): 'ramp_lead' | 'any' => (LEAD_ONLY.includes(type) ? 'ramp_lead' : 'any');

function roleMayTake(role: PersonRole, type: TaskType): boolean {
  if (role === 'supervisor') return false;
  return role === 'ramp_lead' || requiredRole(type) === 'any';
}

function roleMayConfirm(role: PersonRole, severity: string): boolean {
  if (role === 'supervisor') return false;
  return (RULES.roles[role] as string[]).includes(severity);
}

const who = (p: { name: string; role: PersonRole }) => `${p.name} (${ROLE_LABEL[p.role]})`;
const plural = (n: number) => (n === 1 ? '' : 's');
const nowIso = () => new Date().toISOString();
const unresolvedUnusable = (r: Report): AngleName[] => r.angles.filter((a) => a.status === 'unusable' && !a.checked_by_eye).map((a) => a.angle);
const openFindings = (r: Report): Finding[] => r.findings.filter(isOpen);

export function isCommand(text: string): boolean {
  const t = (text ?? '').trim().toLowerCase();
  return t.startsWith('/') || (t.split(' ')[0] ?? '') in ANSWERS;
}

export class MockDispatcher {
  private people: PersonRow[] = MOCK_ROSTER.map((p) => ({ ...p, gates: [...p.gates] }));
  private sessions = new Map<string, string>();
  private seen = new Map<string, number>();
  private messages: ChatMessage[] = [];
  private tasks: TaskRow[] = [];
  private proposals: ProposalRow[] = [];
  private timers: TimerRow[] = [];
  private log: ActivityEntry[] = [];
  private refs: Ref[] = [];
  private confirmations = 0;
  private confirmationByLabel = new Map<string, number>();
  private cursor = 0;
  private epoch: number;
  private overtime = 0;
  private unroutable = new Set<string>();
  private idleAnnounced = true;
  private wakes: Wake[] = [];
  private spend = { usd: 0, wakes: 0, tokens_in: 0, tokens_out: 0 };

  constructor(private readonly backend: MockBackend) {
    this.epoch = backend.epoch;
    this.start();
  }

  private start(): void {
    this.writeLog('code', 'Dispatcher started. Mock mode: no model is called; the agent replies from fixed patterns. Waiting for events.', {
      event: 'dispatcher_started',
    });
    this.step();
  }

  // ------------------------------------------------------------------ clock and loop

  /** Demo seconds. Once the scripted demo has ended the clock keeps going, so a pending Escalation does not freeze. */
  clock(): number {
    return this.backend.clock() + this.overtime;
  }

  /** Call after the backend's own tick, with the same wall-clock seconds. */
  tick(realSeconds: number): void {
    if (this.backend.finished()) this.overtime += realSeconds * this.backend.demoSpeed();
    this.step();
  }

  /** Handle new events and due timers. */
  step(): void {
    if (this.backend.epoch !== this.epoch) {
      this.epoch = this.backend.epoch;
      this.cursor = 0;
      this.overtime = 0;
      this.messages = [];
      this.tasks = [];
      this.proposals = [];
      this.timers = [];
      this.log = [];
      this.refs = [];
      this.wakes = [];
      this.confirmations = 0;
      this.confirmationByLabel.clear();
      this.unroutable.clear();
      this.idleAnnounced = true;
      this.spend = { usd: 0, wakes: 0, tokens_in: 0, tokens_out: 0 };
      this.writeLog('code', 'Demo reset. Tasks, messages and timers cleared. Waiting for events.', { event: 'demo_reset' });
    }
    const events = this.backend.events;
    while (this.cursor < events.length) {
      const e = events[this.cursor]!;
      this.cursor += 1;
      // Turns already under way when the demo starts were inspected before this "process" started.
      if (e.t >= 0) this.onEvent(e);
    }
    for (const tm of this.timers) {
      if (!tm.fired && !tm.cancelled && tm.fire_t <= this.clock()) {
        tm.fired = true;
        this.onTimer(tm);
      }
    }
    this.announceIdle();
  }

  /** Run the mock agent on free text that arrived since the last call. */
  drainWakes(): void {
    while (this.wakes.length > 0) this.runWake(this.wakes.shift()!);
    this.step();
  }

  // ------------------------------------------------------------------ people

  private view(p: PersonRow): RosterPerson {
    const seen = this.seen.get(p.person_id);
    return {
      person_id: p.person_id,
      name: p.name,
      role: p.role,
      gates: [...p.gates],
      shift: p.shift,
      signed_in: seen !== undefined && Date.now() - seen < SIGNED_IN_WINDOW_MS,
    };
  }

  private person(id: string | null | undefined): PersonRow | null {
    const key = (id ?? '').trim().toLowerCase();
    return this.people.find((p) => p.person_id === key) ?? null;
  }

  private find(text: string | null | undefined): PersonRow | null {
    const key = (text ?? '').trim().toLowerCase().replace(/^@/, '');
    return this.people.find((p) => p.person_id === key || p.name.toLowerCase() === key) ?? null;
  }

  private name(id: string | null | undefined): string {
    return this.person(id)?.name ?? id ?? 'nobody';
  }

  private roster_(filter: { onShift?: boolean; role?: PersonRole } = {}): PersonRow[] {
    const order: PersonRole[] = ['ramp_agent', 'ramp_lead', 'supervisor'];
    return [...this.people]
      .sort((a, b) => order.indexOf(a.role) - order.indexOf(b.role) || a.person_id.localeCompare(b.person_id))
      .filter((p) => (!filter.onShift || p.shift === 'on') && (!filter.role || p.role === filter.role));
  }

  private leads(): PersonRow[] {
    return this.roster_({ onShift: true, role: 'ramp_lead' });
  }

  private supervisors(): PersonRow[] {
    return this.roster_({ role: 'supervisor' });
  }

  private session(token: string): PersonRow {
    const p = this.person(this.sessions.get(token));
    if (!p) fail(401, 'not_signed_in', 'Sign in first: POST /api/agent/join with a roster name and PIN');
    this.seen.set(p.person_id, Date.now());
    return p;
  }

  // ------------------------------------------------------------------ log and messages

  private writeLog(kind: string, text: string, o: LogOptions): number {
    const src = o.task ?? o.turn ?? null;
    const id = this.log.length + 1;
    this.log.push({
      id,
      at: nowIso(),
      t: Math.round(this.clock() * 10) / 10,
      kind,
      event: o.event,
      gate: o.gate ?? src?.gate ?? null,
      turn_id: src?.turn_id ?? null,
      actor: o.actor ?? 'code',
      text,
      data: o.data ?? {},
    });
    return id;
  }

  private send(
    toId: string,
    text: string,
    o: { kind?: string; from?: string; taskId?: string | null; proposalId?: string | null } = {},
  ): number {
    const kind = o.kind ?? 'code';
    const from = o.from ?? 'code';
    const id = this.messages.length + 1;
    this.messages.push({
      message_id: id,
      from,
      to: toId,
      kind,
      text,
      task_id: o.taskId ?? null,
      proposal_id: o.proposalId ?? null,
      at: nowIso(),
      t: Math.round(this.clock() * 10) / 10,
    });
    const typed = (kind === 'person' || kind === 'command') && (toId === 'agent' || toId === 'code');
    this.writeLog(typed ? 'person' : 'message', typed ? `${from}> ${text}` : `${from} to ${toId}: ${text}`, {
      event: 'message',
      task: o.taskId ? this.task(o.taskId) : null,
      actor: from,
      data: { message_id: id, from, to: toId, kind, task_id: o.taskId ?? null, proposal_id: o.proposalId ?? null },
    });
    return id;
  }

  // ------------------------------------------------------------------ tasks

  private task(id: string | null | undefined): TaskRow | null {
    const key = (id ?? '').trim().toUpperCase();
    return this.tasks.find((t) => t.task_id === key) ?? null;
  }

  private activeTasks(filter: { turnId?: string; assigneeId?: string } = {}): TaskRow[] {
    return this.tasks.filter(
      (t) =>
        ACTIVE.includes(t.status) &&
        (!filter.turnId || t.turn_id === filter.turnId) &&
        (!filter.assigneeId || t.assignee_id === filter.assigneeId),
    );
  }

  private taskView(t: TaskRow): Task {
    const { seq: _seq, reports: _reports, ...view } = t;
    return { ...view };
  }

  private close(tasks: TaskRow[], reason: string, confirmationId: number | null, cancelled = false): void {
    for (const t of tasks) {
      t.status = cancelled ? 'cancelled' : 'closed';
      t.closed_at = nowIso();
      t.close_reason = reason;
      t.closed_by_confirmation_id = confirmationId;
      this.cancelTimers(t.task_id);
    }
    const first = tasks[0];
    if (!first) return;
    const ids = tasks.map((t) => t.task_id);
    this.writeLog('code', `Task${tasks.length > 1 ? 's' : ''} ${ids.join(', ')} ${cancelled ? 'cancelled' : 'closed'}: ${reason}. Timers cancelled.`, {
      event: cancelled ? 'task_cancelled' : 'task_closed',
      task: first,
      data: { task_ids: ids, reason, confirmation_id: confirmationId },
    });
  }

  // ------------------------------------------------------------------ timers

  private setTimer(kind: string, afterS: number, taskId: string): void {
    this.timers.push({ id: this.timers.length + 1, task_id: taskId, kind, fire_t: this.clock() + Math.max(0, afterS), fired: false, cancelled: false });
  }

  private cancelTimers(taskId: string, kinds?: string[]): void {
    for (const tm of this.timers) {
      if (tm.task_id === taskId && !tm.fired && (!kinds || kinds.includes(tm.kind))) tm.cancelled = true;
    }
  }

  private startTimers(task: TaskRow, turn: MockTurnInfo | null): void {
    this.cancelTimers(task.task_id);
    if (task.type === 'ack_hold') {
      if (task.status === 'assigned') {
        this.setTimer('hold_unack_1', LADDER.hold_unacknowledged_s[0], task.task_id);
        this.setTimer('hold_unack_2', LADDER.hold_unacknowledged_s[1], task.task_id);
      }
      if (turn?.pushback_t != null) {
        // The mock's pushback countdown runs GATE_TIME_SCALE times faster than its demo clock.
        const fireT = turn.pushback_t - (LADDER.hold_pushback_under_min * 60) / GATE_TIME_SCALE;
        this.timers.push({ id: this.timers.length + 1, task_id: task.task_id, kind: 'hold_pushback', fire_t: fireT, fired: false, cancelled: false });
      }
    } else if (task.type !== 'sign_off') {
      this.setTimer('no_report_ask', LADDER.no_report_ask_s, task.task_id);
      this.setTimer('no_report_offer', LADDER.no_report_offer_s, task.task_id);
    }
  }

  // ------------------------------------------------------------------ Finding labels (F1, F2, ...)

  private settledLatest(turnId: string): Report | null {
    const reports = this.backend.reportsForTurn(turnId).filter((r) => r.status !== 'inspecting');
    return reports.at(-1) ?? null;
  }

  /** Label Findings seen for the first time. A re-inspection gives a Finding a new ID; people keep the label. */
  private advanceRefs(turnId: string): Report | null {
    const latest = this.settledLatest(turnId);
    if (!latest) return null;
    for (const f of latest.findings) {
      const key = this.backend.itemKey(f.finding_id);
      if (!key || !isOpen(f)) continue;
      if (!this.refs.some((r) => r.turn_id === turnId && r.key === key)) {
        this.refs.push({ label: `F${this.refs.length + 1}`, turn_id: turnId, gate: latest.gate, key });
      }
    }
    return latest;
  }

  private labelOf(turnId: string, findingId: string | undefined): string | null {
    const key = findingId ? this.backend.itemKey(findingId) : null;
    return this.refs.find((r) => r.turn_id === turnId && r.key === key)?.label ?? null;
  }

  private findingFor(ref: Ref, report: Report): Finding | null {
    const same = report.findings.filter((f) => this.backend.itemKey(f.finding_id) === ref.key);
    return same.find(isOpen) ?? same[0] ?? null;
  }

  /** (ref, latest report, Finding) for a label, always on the Turn's latest Inspection. */
  private resolve(label: string | null | undefined): { ref: Ref; report: Report; finding: Finding } {
    const key = (label ?? '').trim().toUpperCase();
    const ref = this.refs.find((r) => r.label === key);
    if (!ref) throw new DispatchError(`No Finding ${label}`);
    const report = this.advanceRefs(ref.turn_id);
    const finding = report ? this.findingFor(ref, report) : null;
    if (!report || !finding) throw new DispatchError(`Finding ${ref.label} is no longer in the latest Inspection`);
    return { ref, report, finding };
  }

  // ------------------------------------------------------------------ events

  private pushback(turn: MockTurnInfo | null): string {
    const m = turn?.minutes_to_pushback;
    return m === null || m === undefined ? '' : `Scheduled pushback in ${m} min.`;
  }

  private onEvent(e: MockStoreEvent): void {
    const turn = this.backend.turn(e.turn_id);
    if (!turn) return;
    this.advanceRefs(e.turn_id);
    const by = e.data.by;
    const byText = by ? `${by.name} (${ROLE_LABEL[by.role]})` : '?';
    const label = this.labelOf(e.turn_id, e.data.finding_id) ?? e.data.finding_id ?? null;
    const conf = (action: string | undefined): LogOptions => {
      this.confirmations += 1;
      if (label) this.confirmationByLabel.set(label, this.confirmations);
      return {
        event: 'confirmation',
        turn,
        actor: by?.name ?? '?',
        data: { action, finding_id: label, angle: e.data.angle ?? null, by: by ?? {}, inspection_id: e.data.inspection_id ?? null },
      };
    };
    if (e.type === 'inspection_completed') {
      this.logInspection(turn, this.backend.reportsForTurn(e.turn_id).find((r) => r.inspection_id === e.data.inspection_id) ?? null);
    } else if (e.type === 'finding_acknowledged') {
      this.writeLog('code', `Recorded: ${label} acknowledged by ${byText}.`, conf('acknowledged'));
    } else if (e.type === 'finding_confirmed') {
      this.writeLog('code', `Recorded: ${label} ${(e.data.outcome ?? '').replace(/_/g, ' ')}, confirmed by ${byText}.`, conf(e.data.outcome));
    } else if (e.type === 'angle_checked_by_eye') {
      this.writeLog('code', `Recorded: ${e.gate} ${e.data.angle} checked by eye by ${byText}.`, conf('checked_by_eye'));
    } else if (e.type === 'inspection_signed_off') {
      this.writeLog('code', `Inspection signed off by ${byText}. ${e.gate} confirmed clear.`, conf('signoff'));
    } else if (e.type === 'departed') {
      this.writeLog('code', `${e.gate} ${turn.flight} departed.`, { event: 'departed', turn });
    }
    this.syncTurn(e.turn_id);
  }

  private logInspection(turn: MockTurnInfo, rep: Report | null): void {
    if (!rep || rep.status === 'inspecting') return;
    let kind = rep.kind.replace(/_/g, '-');
    if (rep.kind === 'on_demand') {
      const fresh = rep.angles.filter((a) => a.source_inspection_id === rep.inspection_id).map((a) => a.angle);
      kind = `re-inspection${fresh.length > 0 && fresh.length < rep.angles.length ? ` of ${fresh.join(', ')}` : ''}`;
    }
    const lines = [`${rep.gate} ${turn.flight} ${kind} Inspection done. Verdict ${(rep.verdict ?? '').replace(/_/g, ' ')} (advisory).`];
    for (const f of openFindings(rep)) {
      const label = this.labelOf(rep.turn_id, f.finding_id) ?? '?';
      lines.push(`${label.padEnd(3)} ${f.severity.padEnd(8)} ${f.angle.padEnd(5)} ${f.rule_id.padEnd(7)} ${short(f.description, 70)}`);
    }
    for (const a of rep.angles) {
      if (a.status === 'unusable' && !a.checked_by_eye) lines.push(`${a.angle} unusable (${a.unusable_reason}): not covered by the cameras`);
    }
    if (this.pushback(turn)) lines.push(this.pushback(turn));
    this.writeLog('code', lines.join('\n'), {
      event: 'inspection_completed',
      turn,
      data: {
        inspection_id: rep.inspection_id,
        kind: rep.kind,
        verdict: rep.verdict,
        highest_open_severity: rep.highest_open_severity,
        open_findings: openFindings(rep).map((f) => this.labelOf(rep.turn_id, f.finding_id)),
      },
    });
  }

  // ------------------------------------------------------------------ keeping Tasks in step with the record

  private needed(latest: Report): Needed[] {
    const out: Needed[] = [];
    for (const f of openFindings(latest)) {
      const type: TaskType = f.zone_tier === 'outside_boundary' ? 'report_outside_boundary' : f.severity === 'HOLD' ? 'ack_hold' : 'remove';
      out.push({ type, label: this.labelOf(latest.turn_id, f.finding_id), angle: f.angle, finding: f });
    }
    for (const a of unresolvedUnusable(latest)) out.push({ type: 'check_by_eye', label: null, angle: a, finding: null });
    if (out.length === 0) out.push({ type: 'sign_off', label: null, angle: null, finding: null });
    return out;
  }

  private syncTurn(turnId: string): void {
    const turn = this.backend.turn(turnId);
    const latest = this.advanceRefs(turnId);
    if (!turn || !latest) return;
    const active = this.activeTasks({ turnId });
    if (turn.phase === 'departed' || latest.status === 'confirmed') {
      this.close(active, 'Inspection signed off', this.confirmations || null);
      return;
    }
    const unresolved = unresolvedUnusable(latest);
    const needed = this.needed(latest);
    for (const t of active) {
      if (FINDING_TASKS.includes(t.type)) {
        const ref = this.refs.find((r) => r.label === t.finding_id);
        const f = ref ? this.findingFor(ref, latest) : null;
        if (!f) {
          this.close([t], 'replaced by a newer Inspection', null, true);
        } else if (!isOpen(f)) {
          const how = f.confirmation?.outcome ?? 'reported';
          const by = f.confirmation?.confirmed_by.name ?? '?';
          this.close([t], `${t.finding_id} ${how.replace(/_/g, ' ')}, confirmed by ${by}`, this.confirmationByLabel.get(t.finding_id ?? '') ?? null);
        } else {
          t.inspection_id = latest.inspection_id;
          t.inspection_finding_id = f.finding_id;
          if (t.type === 'ack_hold' && f.status === 'acknowledged' && t.status === 'assigned') {
            t.status = 'accepted';
            this.cancelTimers(t.task_id, ['hold_unack_1', 'hold_unack_2']);
          }
        }
      } else if (t.type === 'check_by_eye') {
        if (t.angle && unresolved.includes(t.angle)) t.inspection_id = latest.inspection_id;
        else this.close([t], `${t.angle} re-inspected or checked by eye`, null);
      } else if (t.type === 'sign_off') {
        if (needed[0]?.type === 'sign_off') t.inspection_id = latest.inspection_id;
        else this.close([t], 'the Inspection has open work again', null, true);
      }
    }
    const have = new Set(this.activeTasks({ turnId }).map((t) => `${t.type}|${t.finding_id ?? t.angle ?? ''}`));
    const missing = needed.filter((n) => !have.has(`${n.type}|${n.label ?? n.angle ?? ''}`));
    if (missing.length > 0) this.route(turn, missing);
  }

  /** People on shift who may be given this Task, best first. */
  private eligible(type: TaskType, gate: string, severity: string | null): (PersonRow & { open: number })[] {
    const out = this.roster_({ onShift: true })
      .filter((p) => roleMayTake(p.role, type))
      .filter((p) => !(type === 'report_outside_boundary' && severity && !roleMayConfirm(p.role, severity)))
      .map((p) => ({ ...p, open: this.activeTasks({ assigneeId: p.person_id }).length }));
    const covering = out.filter((p) => p.gates.includes(gate));
    const prefer: PersonRole = requiredRole(type) === 'ramp_lead' ? 'ramp_lead' : 'ramp_agent';
    const signedIn = (p: PersonRow) => this.view(p).signed_in;
    return (covering.length > 0 ? covering : out).sort(
      (a, b) =>
        Number(a.role !== prefer) - Number(b.role !== prefer) ||
        Number(!signedIn(a)) - Number(!signedIn(b)) ||
        a.open - b.open ||
        a.person_id.localeCompare(b.person_id),
    );
  }

  /** HOLD alerts and sign-off requests are always sent by code. The (mock) agent is woken only when the rest could go to more than one person. */
  private route(turn: MockTurnInfo, missing: Needed[]): void {
    const rest: Needed[] = [];
    for (const m of missing) {
      if (m.type === 'ack_hold' || m.type === 'sign_off') this.assignByCode(turn, m, 'code');
      else rest.push(m);
    }
    if (rest.length === 0) return;
    const choice = rest.some((m) => this.eligible(m.type, turn.gate, m.finding?.severity ?? null).length > 1);
    if (!choice) {
      for (const m of rest) this.assignByCode(turn, m, 'code');
      return;
    }
    this.writeLog('wake', `trigger=inspection_completed  model=${MOCK_MODEL}`, {
      event: 'agent_wake_started',
      actor: 'agent',
      turn,
      data: { trigger: 'inspection_completed' },
    });
    const tools: string[] = [];
    for (const m of rest) {
      const task = this.assignByCode(turn, m, 'agent');
      if (task) tools.push('assign_task');
    }
    this.endWake('inspection_completed', tools, `Routed ${tools.length} Task${plural(tools.length)} at ${turn.gate}.`, turn);
  }

  private assignByCode(turn: MockTurnInfo, m: Needed, createdBy: 'code' | 'agent'): TaskRow | null {
    const people = this.eligible(m.type, turn.gate, m.finding?.severity ?? null);
    const key = `${turn.turn_id}|${m.type}|${m.label ?? m.angle ?? ''}`;
    const first = people[0];
    if (!first) {
      if (!this.unroutable.has(key)) {
        this.unroutable.add(key);
        const what = `${TYPE_LABEL[m.type]} ${m.label ?? m.angle ?? ''}`.trim();
        const text = `Cannot route '${what}' at ${turn.gate}: nobody on shift may take it${requiredRole(m.type) === 'ramp_lead' ? ' (a Ramp Lead is required).' : '.'}`;
        for (const s of this.supervisors()) this.send(s.person_id, text);
        this.writeLog('code', `${text} Supervisor told.`, { event: 'unroutable', turn });
      }
      return null;
    }
    try {
      return this.assign({ type: m.type, gate: turn.gate, label: m.label, angle: m.angle, assigneeId: first.person_id, instruction: null, createdBy });
    } catch (err) {
      if (!(err instanceof DispatchError)) throw err;
      return null;
    }
  }

  /** Create a Task for a person. Every check is made here, whoever asks. */
  private assign(a: {
    type: TaskType;
    gate: string;
    label: string | null;
    angle: AngleName | null;
    assigneeId: string;
    instruction: string | null;
    createdBy: string;
  }): TaskRow {
    const turn = this.backend.currentTurn(a.gate);
    if (!turn || turn.phase === 'departed') throw new DispatchError(`There is no Turn in progress at Gate ${a.gate}`);
    const latest = this.advanceRefs(turn.turn_id);
    if (!latest) throw new DispatchError(`Gate ${a.gate} has no finished Inspection yet`);
    if (latest.status === 'confirmed') throw new DispatchError(`The latest Inspection at ${a.gate} is already signed off`);
    const person = this.person(a.assigneeId);
    if (!person) throw new DispatchError(`No such person: ${a.assigneeId}`);
    if (person.shift !== 'on') throw new DispatchError(`${person.name} is not on shift (${person.shift})`);
    if (!roleMayTake(person.role, a.type)) {
      throw new DispatchError(`A '${TYPE_LABEL[a.type]}' Task can only go to a Ramp Lead; ${person.name} is a ${ROLE_LABEL[person.role]}`);
    }
    let f: Finding | null = null;
    let label: string | null = null;
    let angle: AngleName | null = a.angle;
    if (FINDING_TASKS.includes(a.type)) {
      const found = this.resolve(a.label);
      if (found.ref.turn_id !== turn.turn_id) throw new DispatchError(`${found.ref.label} is not at Gate ${a.gate}`);
      f = found.finding;
      if (!isOpen(f)) throw new DispatchError(`${found.ref.label} is already closed by a Confirmation`);
      const outside = f.zone_tier === 'outside_boundary';
      if (a.type === 'ack_hold' && (f.severity !== 'HOLD' || outside)) throw new DispatchError(`${found.ref.label} is not a HOLD inside the gate safety envelope`);
      if (a.type === 'report_outside_boundary' && !outside) throw new DispatchError(`${found.ref.label} is inside the gate safety envelope`);
      if ((a.type === 'remove' || a.type === 'walk_and_report') && outside) {
        throw new DispatchError(`${found.ref.label} is outside the gate safety envelope: it is reported, not removed by the ramp crew`);
      }
      label = found.ref.label;
      angle = f.angle;
    } else if (a.type === 'sign_off') {
      angle = null;
    }
    for (const t of this.activeTasks({ turnId: turn.turn_id })) {
      if (t.type === a.type && (t.finding_id ?? t.angle ?? '') === (label ?? angle ?? '')) {
        throw new DispatchError(`Already assigned: ${t.task_id} (${TYPE_LABEL[a.type]}) is with ${this.name(t.assignee_id)}`);
      }
    }
    const seq = this.tasks.length + 1;
    const task: TaskRow = {
      seq,
      reports: [],
      task_id: `K-${seq}`,
      type: a.type,
      gate: a.gate,
      turn_id: turn.turn_id,
      inspection_id: latest.inspection_id,
      finding_id: label,
      inspection_finding_id: f?.finding_id ?? null,
      angle,
      severity: f?.severity ?? null,
      required_role: requiredRole(a.type),
      assignee_id: person.person_id,
      instruction: a.instruction ? short(a.instruction, 300) : this.defaultInstruction(a.type, a.gate, angle, f),
      status: 'assigned',
      created_by: a.createdBy,
      escalation_level: 0,
      created_at: nowIso(),
      closed_at: null,
      close_reason: null,
      closed_by_confirmation_id: null,
    };
    this.tasks.push(task);
    this.idleAnnounced = false;
    const byAgent = a.createdBy === 'agent';
    this.send(person.person_id, this.taskText(task, f, turn, latest), { kind: byAgent ? 'agent' : 'code', from: a.createdBy, taskId: task.task_id });
    this.startTimers(task, turn);
    const line = `${task.task_id} ${TYPE_LABEL[a.type]} ${label ?? angle ?? a.gate} -> ${who(person)}.`;
    if (byAgent) {
      this.writeLog('agent', `assign_task(${task.task_id} "${short(task.instruction, 60)}", to=${person.person_id})  [code: ok, role ${person.role}]`, {
        event: 'agent_tool',
        actor: 'agent',
        task,
        data: { tool: 'assign_task', args: { type: a.type, gate: a.gate, finding_id: label, assignee_id: person.person_id }, ok: true, result: line },
      });
    }
    this.writeLog('code', line, { event: 'task_assigned', task, actor: a.createdBy, data: { ...this.taskView(task) } });
    if (a.type === 'ack_hold' && f) {
      const others = this.leads().filter((p) => p.person_id !== person.person_id);
      for (const p of others) {
        this.send(
          p.person_id,
          `HOLD at ${a.gate} ${angle} (${label}): ${short(f.description)} (${f.rule_id}). Assigned to ${person.name}. No action for you unless it escalates.`,
          { taskId: task.task_id },
        );
      }
      const told = [person, ...others].map((p) => p.person_id);
      this.writeLog('code', `HOLD alert delivered to every on-shift Ramp Lead: ${told.join(', ')}.`, {
        event: 'hold_alert',
        task,
        data: { task_id: task.task_id, delivered_to: told },
      });
    }
    return task;
  }

  private defaultInstruction(type: TaskType, gate: string, angle: string | null, f: Finding | null): string {
    const d = f?.description ?? '';
    if (type === 'ack_hold') return `Acknowledge and clear the HOLD at ${gate} ${angle}: ${short(d)}`;
    if (type === 'remove') return `Remove the object flagged at ${gate} ${angle}: ${short(d, 110)}`;
    if (type === 'walk_and_report') return `Walk to ${gate} ${angle}, look for the flagged object and report back: ${short(d, 110)}`;
    if (type === 'report_outside_boundary') return `Report the object outside the gate safety envelope at ${gate}: ${short(d, 110)}`;
    if (type === 'check_by_eye') return `Check ${gate} ${angle} by eye or re-inspect it`;
    return `Sign off the latest Inspection at ${gate}`;
  }

  private taskText(task: TaskRow, f: Finding | null, turn: MockTurnInfo, latest: Report): string {
    const { task_id: tid, gate, angle, finding_id: label } = task;
    const push = this.pushback(turn);
    if (task.type === 'ack_hold' && f) {
      return `HOLD at ${gate} ${angle} (${label}): ${short(f.description)} (${f.rule_id}). ${turn.flight}: ${push || 'no scheduled pushback time.'} Nothing moves until a Ramp Lead clears this. Type /ack ${label} when someone is going to it. Task ${tid}.`;
    }
    if (task.type === 'remove' || task.type === 'walk_and_report') {
      return `Task ${tid}: ${task.instruction.replace(/\.$/, '')} (${task.severity}, ${gate} ${angle}, ${label}). Report back here when done, or type /done ${tid}.`;
    }
    if (task.type === 'report_outside_boundary' && f) {
      return `Task ${tid}: ${short(f.description)} lies outside the gate safety envelope at ${gate} (${label}, ${task.severity}). It is not the ramp crew's to remove: report it to Ramp 1 control or Airport Operations, then record /reported ${label}.`;
    }
    if (task.type === 'check_by_eye') {
      const reason = latest.angles.find((a) => a.angle === angle)?.unusable_reason ?? 'unusable';
      return `Task ${tid}: ${gate} ${angle} is unusable (${reason}), so the Inspection is INCOMPLETE. Take a new photo with /reinspect ${gate} ${angle}, or check it in person and record /eye ${gate} ${angle}.`;
    }
    return `Task ${tid}: ${gate} ${turn.flight} has no open Findings. Ready for your sign-off: /signoff ${gate}. ${push}`.trim();
  }

  private reassign(taskId: string | undefined, assigneeId: string, reason: string, by: string): TaskRow {
    const task = this.task(taskId);
    if (!task) throw new DispatchError(`No Task ${taskId}`);
    if (!ACTIVE.includes(task.status)) throw new DispatchError(`${task.task_id} is ${task.status}`);
    const person = this.person(assigneeId);
    if (!person) throw new DispatchError(`No such person: ${assigneeId}`);
    if (person.shift !== 'on') throw new DispatchError(`${person.name} is not on shift (${person.shift})`);
    if (!roleMayTake(person.role, task.type)) {
      throw new DispatchError(`A '${TYPE_LABEL[task.type]}' Task can only go to a Ramp Lead; ${person.name} is a ${ROLE_LABEL[person.role]}`);
    }
    if (person.person_id === task.assignee_id) throw new DispatchError(`${task.task_id} is already with ${person.name}`);
    const old = task.assignee_id;
    task.status = task.type === 'ack_hold' && task.status === 'accepted' ? 'accepted' : 'assigned';
    task.assignee_id = person.person_id;
    this.startTimers(task, this.backend.turn(task.turn_id));
    this.send(
      person.person_id,
      `Task ${task.task_id} has moved to you from ${this.name(old)} (${short(reason, 120)}): ${task.instruction} (${task.severity ?? task.type}, ${task.gate} ${task.angle ?? ''} ${task.finding_id ?? ''}).`.replace(/ {2,}/g, ' '),
      { taskId: task.task_id },
    );
    if (old) this.send(old, `Task ${task.task_id} has moved to ${person.name}.`, { taskId: task.task_id });
    this.writeLog('code', `${task.task_id} moved from ${this.name(old)} to ${who(person)}: ${short(reason, 80)}.`, {
      event: 'task_reassigned',
      task,
      actor: by,
      data: { task_id: task.task_id, from: old, to: person.person_id, reason },
    });
    return task;
  }

  // ------------------------------------------------------------------ Reports (never a Confirmation)

  private owners(task: TaskRow, exclude: string | null, holdLabel: string | null = null): PersonRow[] {
    let people: PersonRow[] = [];
    if (holdLabel) {
      for (const t of this.activeTasks({ turnId: task.turn_id })) {
        const p = t.type === 'ack_hold' && t.finding_id === holdLabel ? this.person(t.assignee_id) : null;
        if (p) people.push(p);
      }
    }
    if (people.length === 0) {
      const leads = this.leads();
      const covering = leads.filter((p) => p.gates.includes(task.gate));
      people = covering.length > 0 ? covering : leads;
    }
    people = people.filter((p) => p.person_id !== exclude);
    return people.length > 0 ? people : this.supervisors();
  }

  /** Record what a person said about a Task and tell whoever has to act on it. The Finding is untouched. */
  private recordReport(
    task: TaskRow,
    person: PersonRow,
    kind: 'accepted' | 'done' | 'not_found' | 'blocked',
    rawText: string | null,
    via: string,
  ): { lines: string[]; proposalId: string | null } {
    task.reports.push({ by_person_id: person.person_id, at: nowIso(), kind, raw_text: rawText, via });
    const { task_id: tid, finding_id: label, gate, angle } = task;
    const lines: string[] = [];
    let proposalId: string | null = null;
    const names = (people: PersonRow[]) => people.map((p) => p.name).join(', ') || 'Nobody';
    if (kind === 'accepted') {
      if (task.status === 'assigned' && task.type !== 'ack_hold') task.status = 'accepted';
    } else if (kind === 'done' || kind === 'not_found') {
      if (task.type !== 'ack_hold') {
        task.status = 'reported';
        this.cancelTimers(tid, ['no_report_ask', 'no_report_offer']);
      }
    } else {
      this.cancelTimers(tid, ['no_report_ask', 'no_report_offer']);
    }
    this.writeLog('code', `Report on ${tid} by ${person.name}: ${kind.replace(/_/g, ' ')} (${via.replace(/_/g, ' ')}).${label ? ` Finding ${label} stays open.` : ''}`, {
      event: kind === 'accepted' ? 'task_accepted' : 'task_reported',
      task,
      actor: person.person_id,
      data: { task_id: tid, kind, via, raw_text: rawText },
    });
    let f: Finding | null = null;
    if (label) {
      try {
        f = this.resolve(label).finding;
      } catch {
        f = null;
      }
    }
    const hold = f !== null && f.severity === 'HOLD' && f.zone_tier !== 'outside_boundary';
    const removal = task.type === 'remove' || task.type === 'walk_and_report';
    if (kind === 'blocked') {
      const targets = this.owners(task, person.person_id);
      for (const p of targets) {
        this.send(
          p.person_id,
          `${person.name} cannot do ${tid} (${task.instruction}): ${short(rawText || 'no reason given', 160)}. To move it: /reassign ${tid} <person>, or tell me who should take it.`,
          { taskId: tid },
        );
      }
      lines.push(`Logged: you cannot do ${tid}. ${names(targets)} told.`);
    } else if ((kind === 'done' || kind === 'not_found') && removal && hold) {
      const targets = this.owners(task, null, label);
      for (const p of targets) {
        const text =
          kind === 'done'
            ? `${person.name} reports the object for HOLD ${label} at ${gate} ${angle} is removed (${tid}). That is a Report, not a Confirmation: only a Ramp Lead can record it. /removed ${label} takes a new photo of ${angle}; the HOLD clears only if the new photo is clean.`
            : `${person.name} reports they could not find the object for HOLD ${label} at ${gate} ${angle} (${tid}). The HOLD stays open. /reinspect ${gate} ${angle} takes a new photo; /false-alarm ${label} <reason> or /not-found ${label} are yours to record.`;
        this.send(p.person_id, text, { taskId: tid });
      }
      lines.push(`Logged your Report on ${tid}. ${label} stays open: a Ramp Lead records HOLDs. ${names(targets)} told.`);
    } else if ((kind === 'done' || kind === 'not_found') && removal && f !== null && label) {
      lines.push(`Logged your Report on ${tid}. ${label} stays open until a Confirmation is recorded.`);
      if (roleMayConfirm(person.role, f.severity)) {
        try {
          const prop = this.proposeConfirmation(person.person_id, label, kind === 'done' ? 'removed' : 'not_found_on_walk', null, via === 'command' ? 'code' : 'agent');
          proposalId = prop.proposal_id;
        } catch (err) {
          if (!(err instanceof DispatchError)) throw err;
          lines.push(err.message);
        }
      }
    } else if (kind === 'done' || kind === 'not_found') {
      const hint: Partial<Record<TaskType, string>> = {
        ack_hold: `/removed ${label} records a HOLD as removed (it takes a new photo first).`,
        check_by_eye: `/eye ${gate} ${angle} records the check; /reinspect ${gate} ${angle} takes a new photo.`,
        sign_off: `/signoff ${gate} records the sign-off.`,
        report_outside_boundary: `/reported ${label} records that it was reported.`,
      };
      lines.push(`Logged your Report on ${tid}. A Report does not record anything on the Inspection. ${hint[task.type] ?? ''}`.trim());
    } else {
      lines.push(`Logged on ${tid}: ${kind}.`);
    }
    return { lines, proposalId };
  }

  // ------------------------------------------------------------------ proposals (a person must accept)

  private createProposal(toId: string, action: ProposalAction, createdBy: string): ProposalRow {
    const id = `P-${this.proposals.length + 1}`;
    const prop: ProposalRow = {
      proposal_id: id,
      to_id: toId,
      action,
      status: 'pending',
      created_by: createdBy,
      created_at: nowIso(),
      expires_t: this.clock() + LADDER.proposal_expires_s,
    };
    this.proposals.push(prop);
    this.writeLog('code', `Asked ${toId} (${createdBy}): ${action.text}?  [y / n]  (${id})`, {
      event: 'proposal_created',
      actor: createdBy,
      gate: action.gate ?? null,
      turn: action.turn_id ? { turn_id: action.turn_id, gate: this.backend.turn(action.turn_id)?.gate } : null,
      data: { proposal_id: id, to: toId, action },
    });
    return prop;
  }

  private pendingProposals(toId: string): ProposalRow[] {
    for (const p of this.proposals) {
      if (p.status === 'pending' && p.expires_t <= this.clock()) p.status = 'expired';
    }
    return this.proposals.filter((p) => p.to_id === toId && p.status === 'pending');
  }

  private setProposal(prop: ProposalRow, status: string): void {
    prop.status = status;
    this.writeLog('code', `${prop.to_id} answered ${prop.proposal_id} (${prop.action.text}): ${status}.`, {
      event: 'proposal_answered',
      actor: prop.to_id,
      gate: prop.action.gate ?? null,
      turn: prop.action.turn_id ? { turn_id: prop.action.turn_id, gate: this.backend.turn(prop.action.turn_id)?.gate } : null,
      data: { proposal_id: prop.proposal_id, status, action: prop.action },
    });
  }

  private proposalView(p: ProposalRow): Proposal {
    const { text: _text, finding_status: _status, ...action } = p.action;
    return {
      proposal_id: p.proposal_id,
      kind: p.action.kind,
      question: p.action.text,
      action,
      created_by: p.created_by,
      created_at: p.created_at,
      status: p.status,
      expires_t: p.expires_t,
      expires_in_s: Math.max(0, Math.round((p.expires_t - this.clock()) * 10) / 10),
    };
  }

  private proposeConfirmation(toId: string, findingLabel: string, outcome: string, reason: string | null, createdBy: string): ProposalRow {
    const person = this.person(toId);
    if (!person || person.role === 'supervisor') throw new DispatchError(`${toId} is not a Ramp Agent or Ramp Lead on the roster`);
    const { ref, report, finding: f } = this.resolve(findingLabel);
    if (!isOpen(f)) throw new DispatchError(`${ref.label} is already closed by a Confirmation`);
    if (!roleMayConfirm(person.role, f.severity)) {
      throw new DispatchError(`Refused: only a Ramp Lead can confirm a ${f.severity} Finding; ${person.name} is a ${ROLE_LABEL[person.role]}`);
    }
    const holdRemoved = f.severity === 'HOLD' && outcome === 'removed';
    if (holdRemoved && f.status !== 'acknowledged') {
      throw new DispatchError(`${ref.label} is a HOLD that has not been acknowledged; the Ramp Lead types /ack ${ref.label} first`);
    }
    for (const p of this.pendingProposals(person.person_id)) {
      if (p.action.kind === 'confirm' && p.action.label === ref.label && p.action.outcome === outcome) {
        throw new DispatchError(`Already proposed to ${person.name}: ${p.proposal_id}`);
      }
    }
    const words = outcome === 'removed' ? 'removed' : outcome === 'false_alarm' ? `a false alarm (${reason})` : 'not found on walk';
    const prop = this.createProposal(
      person.person_id,
      {
        kind: 'confirm',
        label: ref.label,
        outcome,
        turn_id: ref.turn_id,
        false_alarm_reason: outcome === 'false_alarm' ? reason : null,
        finding_status: f.status,
        text: `record ${ref.label} as ${words}`,
      },
      createdBy,
    );
    this.send(
      person.person_id,
      `Record ${ref.label} (${short(f.description, 60)}, ${report.gate} ${f.angle}) as ${words}, confirmed by you?${holdRemoved ? ` A new photo of ${f.angle} is taken first.` : ''}   [y / n]   (${prop.proposal_id})`,
      { kind: createdBy === 'agent' ? 'agent' : 'code', from: createdBy, proposalId: prop.proposal_id },
    );
    return prop;
  }

  // ------------------------------------------------------------------ timers and Escalation

  private onTimer(tm: TimerRow): void {
    const task = this.task(tm.task_id);
    if (!task || !ACTIVE.includes(task.status)) return;
    const tid = task.task_id;
    const waiting = task.status === 'assigned' || task.status === 'accepted';
    if (tm.kind === 'hold_unack_1' && task.status === 'assigned') {
      this.escalate(task, `not acknowledged after ${LADDER.hold_unacknowledged_s[0]} s`, 1, 'timer');
    } else if (tm.kind === 'hold_unack_2' && task.status === 'assigned') {
      this.escalate(task, `not acknowledged after ${LADDER.hold_unacknowledged_s[1]} s`, 2, 'timer');
    } else if (tm.kind === 'hold_pushback') {
      this.escalate(task, `HOLD still open with scheduled pushback under ${LADDER.hold_pushback_under_min} min`, 2, 'timer');
    } else if (tm.kind === 'no_report_ask' && waiting && task.assignee_id) {
      this.send(task.assignee_id, `Any update on ${tid} (${task.instruction})? Reply here, or type /done ${tid} or /cant ${tid} <reason>.`, {
        kind: 'timer',
        taskId: tid,
      });
      this.writeLog('timer', `${tid} has no Report after ${LADDER.no_report_ask_s} s. Asked ${this.name(task.assignee_id)}.`, {
        event: 'timer_fired',
        task,
        actor: 'timer',
        data: { task_id: tid, timer: tm.kind },
      });
    } else if (tm.kind === 'no_report_offer' && waiting) {
      const targets = this.owners(task, task.assignee_id);
      for (const p of targets) {
        this.send(
          p.person_id,
          `${tid} (${task.instruction}) has no Report from ${this.name(task.assignee_id)} after ${LADDER.no_report_offer_s} s. To move it: /reassign ${tid} <person>, or tell me who should take it.`,
          { kind: 'timer', taskId: tid },
        );
      }
      this.writeLog('timer', `${tid} still has no Report after ${LADDER.no_report_offer_s} s. Offered reassignment to ${targets.map((p) => p.name).join(', ') || 'Nobody'}.`, {
        event: 'timer_fired',
        task,
        actor: 'timer',
        data: { task_id: tid, timer: tm.kind },
      });
    }
  }

  /** Raise a Task one level (or to `level`) and tell the people that level names. Escalation only tells people. */
  private escalate(task: TaskRow, reason: string, level: number | null, by: 'timer' | 'code'): void {
    if (!ACTIVE.includes(task.status)) throw new DispatchError(`${task.task_id} is ${task.status}`);
    if (level === null && task.escalation_level >= MAX_LEVEL) {
      throw new DispatchError(`${task.task_id} is already at the top Escalation level; the supervisor has been told`);
    }
    const next = Math.max(task.escalation_level, Math.min(MAX_LEVEL, level ?? task.escalation_level + 1));
    task.escalation_level = next;
    const { task_id: tid, gate, finding_id: label, angle } = task;
    const turn = this.backend.turn(task.turn_id);
    const owner = this.name(task.assignee_id);
    const subject = task.type === 'ack_hold' ? `HOLD ${label} at ${gate} ${angle}` : `${tid} (${TYPE_LABEL[task.type]} at ${gate} ${label ?? angle ?? ''})`.replace(' )', ')');
    const told: string[] = [];
    const tell = (personId: string | null, text: string) => {
      if (personId && !told.includes(personId)) {
        this.send(personId, text, { kind: 'timer', taskId: tid });
        told.push(personId);
      }
    };
    const push = this.pushback(turn);
    if (next <= 1) {
      tell(
        task.assignee_id,
        `Second call: ${subject}: ${reason}. ${push} ${task.type === 'ack_hold' ? `Type /ack ${label} when someone is going to it.` : `Reply here or type /done ${tid}.`}`.replace(/ {2,}/g, ' '),
      );
    } else {
      for (const p of this.leads()) {
        tell(
          p.person_id,
          `Escalation level ${next}: ${subject}: ${reason}. Assigned to ${owner}. ${push} ${task.type === 'ack_hold' ? `Any Ramp Lead can take it: /ack ${label}.` : `To move it: /reassign ${tid} <person>.`}`.replace(/ {2,}/g, ' '),
        );
      }
    }
    for (const s of this.supervisors()) tell(s.person_id, `Escalation level ${next}: ${subject}, assigned to ${owner}: ${reason}. ${push}`.trim());
    this.writeLog(by === 'timer' ? 'timer' : 'code', `${tid} ${task.type === 'ack_hold' ? subject : ''}: ${reason}. Escalation level ${next}. Told: ${told.join(', ') || 'nobody on shift'}.`.replace(/ {2,}/g, ' '), {
      event: 'task_escalated',
      task,
      actor: by,
      data: { task_id: tid, level: next, reason, notified: told },
    });
  }

  /** A HOLD was recorded as removed but the new photo still shows the object. */
  private holdStillPresent(label: string): void {
    for (const t of this.tasks.filter((x) => x.finding_id === label && ACTIVE.includes(x.status))) {
      if ((t.type === 'remove' || t.type === 'walk_and_report') && t.status === 'reported') {
        t.status = 'assigned';
        this.startTimers(t, this.backend.turn(t.turn_id));
        if (t.assignee_id) {
          this.send(t.assignee_id, `The new photo of ${t.gate} ${t.angle} still shows the object for ${label}. ${t.task_id} is open again: please go back and report here.`, {
            taskId: t.task_id,
          });
        }
        this.writeLog('code', `${t.task_id} reopened: the new photo still shows the object for ${label}.`, {
          event: 'task_reopened',
          task: t,
          data: { task_id: t.task_id },
        });
      } else if (t.type === 'ack_hold') {
        try {
          this.escalate(t, 'the re-inspection still shows the object', null, 'code');
        } catch (err) {
          if (!(err instanceof DispatchError)) throw err;
        }
      }
    }
  }

  private announceIdle(): void {
    if (this.idleAnnounced || this.wakes.length > 0 || this.activeTasks().length > 0) return;
    this.idleAnnounced = true;
    this.writeLog('idle', `No open Tasks. Waiting for events. Agent session cost $${this.spend.usd.toFixed(4)}.`, { event: 'idle' });
  }

  // ------------------------------------------------------------------ the mock agent (no model)

  private endWake(trigger: string, tools: string[], note: string, turn: MockTurnInfo | null = null): void {
    // Illustrative figures at Haiku list prices; nothing was sent to a model.
    const tokensIn = 1900 + 350 * tools.length;
    const tokensOut = 90 + 60 * tools.length;
    const usd = Number(((tokensIn * 1 + tokensOut * 5) / 1_000_000).toFixed(6));
    this.spend = { usd: this.spend.usd + usd, wakes: this.spend.wakes + 1, tokens_in: this.spend.tokens_in + tokensIn, tokens_out: this.spend.tokens_out + tokensOut };
    if (note) this.writeLog('agent', short(note, 300), { event: 'agent_note', actor: 'agent', turn });
    this.writeLog('cost', `wake $${usd.toFixed(4)}   agent session $${this.spend.usd.toFixed(4)}   process $${this.spend.usd.toFixed(4)}`, {
      event: 'agent_wake',
      actor: 'agent',
      turn,
      data: { trigger, model: MOCK_MODEL, outcome: 'ok', tokens_in: tokensIn, tokens_out: tokensOut, est_cost_usd: usd, tool_calls: tools },
    });
  }

  private agentTool(name: string, argsLine: string, ok: boolean, result: string, gate: string | null): void {
    this.writeLog('agent', `${name}(${argsLine})  ${ok ? '[code: ok]' : `[code: refused. ${short(result, 160)}]`}`, {
      event: 'agent_tool',
      actor: 'agent',
      gate,
      data: { tool: name, ok, result: short(result, 400) },
    });
  }

  /** Free text from a person. Fixed patterns stand in for the model; none of them can record a Confirmation. */
  private runWake(w: Wake): void {
    const person = this.person(w.person_id);
    if (!person) return;
    this.writeLog('wake', `trigger=human_message  model=${MOCK_MODEL}`, { event: 'agent_wake_started', actor: 'agent', data: { trigger: 'human_message' } });
    const text = w.text.toLowerCase();
    const tools: string[] = [];
    const reply: string[] = [];
    const say = (toId: string, body: string, taskId: string | null = null) => {
      this.send(toId, body, { kind: 'agent', from: 'agent', taskId });
      tools.push('send_message');
    };
    const mine = this.activeTasks({ assigneeId: person.person_id });
    const removal = mine.filter((t) => (t.type === 'remove' || t.type === 'walk_and_report') && t.status !== 'reported');
    const notFound = /can'?t find|cannot find|could ?n'?t find|not there|nothing there|no sign of/.test(text);
    const blocked = !notFound && /\b(can'?t|cannot|unable|busy|blocked)\b/.test(text);
    const done = !notFound && !blocked && /\b(got|removed|picked|cleared|gone|done|binned|bin|collected|sorted)\b/.test(text);
    const named = this.people.find((p) => p.person_id !== person.person_id && new RegExp(`\\b${p.name.toLowerCase()}\\b`).test(text));

    if (person.role !== 'ramp_agent' && named && /\b(send|give|assign|ask|get|have|let)\b/.test(text)) {
      // "send kim, she's closest": a removal Task for the lead's open HOLD goes to the named person.
      const hold = mine.find((t) => t.type === 'ack_hold') ?? this.activeTasks().find((t) => t.type === 'ack_hold' && person.gates.includes(t.gate));
      if (hold?.finding_id) {
        try {
          const f = this.resolve(hold.finding_id).finding;
          const task = this.assign({
            type: 'remove',
            gate: hold.gate,
            label: hold.finding_id,
            angle: hold.angle,
            assigneeId: named.person_id,
            instruction: `Remove the object for HOLD ${hold.finding_id} at ${hold.gate} ${hold.angle} and report back: ${short(f.description, 80)}`,
            createdBy: 'agent',
          });
          tools.push('assign_task');
          reply.push(`${task.task_id} is with ${named.name}: remove the object for ${hold.finding_id} at ${hold.gate} ${hold.angle} and report back. ${hold.finding_id} stays open until you record it.`);
        } catch (err) {
          if (!(err instanceof DispatchError)) throw err;
          this.agentTool('assign_task', `remove ${hold.finding_id}, to=${named.person_id}`, false, err.message, hold.gate);
          reply.push(`I could not give that to ${named.name}: ${err.message}.`);
        }
      } else {
        reply.push(`There is no open HOLD at your Gates to send ${named.name} to. To move a Task: /reassign <task> ${named.person_id}.`);
      }
    } else if ((done || notFound) && person.role !== 'supervisor') {
      for (const t of removal) {
        const out = this.recordReport(t, person, done ? 'done' : 'not_found', w.text, 'agent');
        this.agentTool('record_task_report', `${t.task_id}, ${done ? 'done' : 'not_found'}`, true, out.lines.join(' '), t.gate);
        tools.push('record_task_report');
        if (out.proposalId) tools.push('propose_confirmation');
        reply.push(...out.lines);
        if (out.proposalId) reply.push(`I have asked you to confirm ${t.finding_id} below: only your own answer records it.`);
      }
      // A HOLD they hold no Task for: pass the Report to the Ramp Lead who holds it.
      const reported = new Set(removal.map((t) => t.finding_id));
      for (const hold of this.activeTasks().filter((t) => t.type === 'ack_hold' && person.gates.includes(t.gate) && !reported.has(t.finding_id))) {
        let f: Finding | null = null;
        try {
          f = hold.finding_id ? this.resolve(hold.finding_id).finding : null;
        } catch {
          f = null;
        }
        const word = f?.description.toLowerCase().split(/\W+/)[0] ?? '';
        if (!f || !word || !text.includes(word) || hold.assignee_id === person.person_id) continue;
        if (hold.assignee_id) {
          say(
            hold.assignee_id,
            done
              ? `${person.name} reports the object for HOLD ${hold.finding_id} at ${hold.gate} ${hold.angle} is removed: "${short(w.text, 120)}". That is a Report, not a Confirmation: only a Ramp Lead can record it. /removed ${hold.finding_id} takes a new photo of ${hold.angle}; the HOLD clears only if the new photo is clean.`
              : `${person.name} reports they could not find the object for HOLD ${hold.finding_id} at ${hold.gate} ${hold.angle}: "${short(w.text, 120)}". The HOLD stays open. /reinspect ${hold.gate} ${hold.angle} takes a new photo.`,
            hold.task_id,
          );
        }
        reply.push(`I have told ${this.name(hold.assignee_id)} what you said about ${hold.finding_id} (${word}). ${hold.finding_id} stays open: a Ramp Lead records HOLDs.`);
      }
      if (reply.length === 0) reply.push('I logged your message, but you have no open removal Task it could be a Report on. Nothing was recorded.');
    } else if (blocked && mine[0]) {
      const out = this.recordReport(mine[0], person, 'blocked', w.text, 'agent');
      this.agentTool('record_task_report', `${mine[0].task_id}, blocked`, true, out.lines.join(' '), mine[0].gate);
      tools.push('record_task_report');
      reply.push(...out.lines);
    } else {
      reply.push('I logged your message. (Mock agent: fixed replies, no model is called.) Use the buttons on a Task to report on it or to record a Confirmation; /help lists the commands.');
    }
    say(person.person_id, reply.join('\n'));
    this.endWake('human_message', tools, `Handled free text from ${person.name}: ${tools.join(', ')}.`);
  }

  // ------------------------------------------------------------------ commands (the only path to a Confirmation)

  private actor(person: PersonRow): { role: Role; name: string } {
    if (person.role === 'supervisor') {
      fail(403, 'role_not_allowed', 'A supervisor does not record Confirmations; a Ramp Agent or Ramp Lead does');
    }
    return { role: person.role, name: person.name };
  }

  private gateReport(gate: string | undefined): { gate: string; latest: Report } {
    const g = (gate ?? '').toUpperCase();
    if (!(GATES as readonly string[]).includes(g)) bad(`Name a Gate: one of ${GATES.join(', ')}`);
    const turn = this.backend.currentTurn(g);
    const latest = turn && turn.phase !== 'departed' ? this.backend.reportsForTurn(turn.turn_id).at(-1) : undefined;
    if (!latest) fail(404, 'not_found', `Gate ${g} has no Inspection in a Turn in progress`);
    return { gate: g, latest };
  }

  private findingByLabel(label: string | undefined): { ref: Ref; report: Report; finding: Finding } {
    if (!label || !/^[Ff]\d+$/.test(label)) bad('Name a Finding by its short ID, for example F1');
    try {
      return this.resolve(label);
    } catch (err) {
      if (!(err instanceof DispatchError)) throw err;
      fail(404, 'not_found', err.message);
    }
  }

  private confirm(
    person: PersonRow,
    labelArg: string | undefined,
    outcome: 'acknowledged' | 'removed' | 'false_alarm' | 'not_found_on_walk',
    o: { reason?: string | null; source?: string | null } = {},
  ): string[] {
    const by = this.actor(person);
    const { ref, report, finding: f } = this.findingByLabel(labelArg);
    const label = ref.label;
    const holdRemoved = f.severity === 'HOLD' && outcome === 'removed';
    const next = this.backend.confirmFinding(report.inspection_id, f.finding_id, {
      ...by,
      outcome,
      false_alarm_reason: (o.reason as FalseAlarmReason | null | undefined) ?? undefined,
      possible_source: o.source ?? undefined,
    });
    if (outcome === 'acknowledged') return [`Recorded: ${label} acknowledged by ${who(person)}.`];
    if (!holdRemoved) return [`Recorded: ${label} ${outcome.replace(/_/g, ' ')}, confirmed by ${who(person)}.`];
    const after = next.inspection_id !== report.inspection_id ? next.findings.find((x) => this.backend.itemKey(x.finding_id) === ref.key) : undefined;
    if (after && !isOpen(after)) return [`New photo of ${report.gate} ${f.angle} is clean. Recorded: ${label} removed, confirmed by ${who(person)}.`];
    this.advanceRefs(ref.turn_id);
    this.holdStillPresent(label);
    return [`The new photo of ${report.gate} ${f.angle} still shows the object. ${label} stays open (HOLD); nothing was recorded.`];
  }

  private reinspectCmd(person: PersonRow, args: string[]): string[] {
    const by = this.actor(person);
    const { gate, latest } = this.gateReport(args[0]);
    const angle = (args[1] ?? '').toUpperCase() as AngleName;
    if (!ANGLE_ORDER.includes(angle)) bad(`Name an Angle: one of ${ANGLE_ORDER.join(', ')}`);
    const next = this.backend.reinspectAngle(latest.inspection_id, angle, by);
    const entry = next.angles.find((a) => a.angle === angle);
    const still = openFindings(next).filter((f) => f.angle === angle);
    const state =
      entry?.status !== 'usable'
        ? `unusable (${entry?.unusable_reason})`
        : still.length > 0
          ? `${still.length} open Finding${plural(still.length)} on it`
          : 'nothing new seen on it';
    return [`New photo of ${gate} ${angle}: ${state}. A re-inspection never closes a Finding; open Findings stay open until a Confirmation is recorded.`];
  }

  private myTask(person: PersonRow, taskId: string | undefined): TaskRow {
    if (!taskId) bad('Name a Task, for example K-3');
    const t = this.task(taskId);
    if (!t) fail(404, 'not_found', `No Task ${taskId}`);
    if (!ACTIVE.includes(t.status)) fail(409, 'task_closed', `${t.task_id} is ${t.status}`);
    if (t.assignee_id !== person.person_id) fail(403, 'not_your_task', `${t.task_id} is with ${this.name(t.assignee_id)}`);
    return t;
  }

  private holdsOpenHold(person: PersonRow): TaskRow[] {
    return this.activeTasks({ assigneeId: person.person_id }).filter((t) => t.severity === 'HOLD');
  }

  private answer(person: PersonRow, yes: boolean, proposalId: string | undefined): string[] {
    let pending = this.pendingProposals(person.person_id);
    if (proposalId) pending = pending.filter((p) => p.proposal_id === proposalId.toUpperCase());
    const prop = pending[0];
    if (!prop) {
      fail(409, 'nothing_to_answer', 'There is no open question for you (it may have expired). Use a slash command instead: /help');
    }
    const action = prop.action;
    if (!yes) {
      this.setProposal(prop, 'declined');
      return [`Declined (${prop.proposal_id}): nothing was recorded.`];
    }
    let lines: string[];
    try {
      if (action.kind === 'confirm') {
        const { finding: f } = this.findingByLabel(action.label);
        if (!isOpen(f) || f.status !== action.finding_status) {
          this.setProposal(prop, 'void');
          fail(409, 'proposal_void', `${prop.proposal_id} is void: ${action.label} has changed since the question was asked. Nothing was recorded.`);
        }
        lines = this.confirm(person, action.label, action.outcome as 'removed', { reason: action.false_alarm_reason });
      } else if (action.kind === 'reinspect') {
        lines = this.reinspectCmd(person, [action.gate ?? '', action.angle ?? '']);
      } else {
        lines = this.takeHandover(person, action);
      }
    } catch (err) {
      if (prop.status === 'pending') this.setProposal(prop, 'void');
      throw err;
    }
    this.setProposal(prop, 'accepted');
    return lines;
  }

  private takeHandover(person: PersonRow, action: ProposalAction): string[] {
    const src = this.person(action.from_id);
    const moved: string[] = [];
    for (const t of this.activeTasks({ assigneeId: action.from_id })) {
      try {
        this.reassign(t.task_id, person.person_id, `Handover from ${src?.name}`, action.from_id ?? 'code');
        moved.push(t.task_id);
      } catch (err) {
        if (!(err instanceof DispatchError)) throw err;
      }
    }
    this.writeLog('code', `Handover: ${moved.join(', ') || 'no Tasks'} moved from ${src?.name} to ${who(person)}.`, {
      event: 'handover',
      actor: person.person_id,
      data: { from: action.from_id, to: person.person_id, tasks: moved },
    });
    return [`Handover accepted: ${moved.join(', ') || 'no Tasks'} are now yours.`];
  }

  private run(person: PersonRow, text: string): string[] {
    const parts = text.split(' ');
    const cmd = (parts[0] ?? '').toLowerCase();
    const args = parts.slice(1);
    if (cmd in ANSWERS) return this.answer(person, ANSWERS[cmd]!, args[0]);
    switch (cmd) {
      case '/help': {
        const lines = person.role === 'supervisor' ? [...HELP.supervisor] : [...HELP.ramp_agent];
        return person.role === 'ramp_lead' ? [...HELP.ramp_lead, ...lines] : lines;
      }
      case '/tasks': {
        const mine = person.role === 'supervisor' ? this.activeTasks() : this.activeTasks({ assigneeId: person.person_id });
        if (mine.length === 0) return ['No open Tasks.'];
        return mine.map(
          (t) =>
            `${t.task_id}  ${t.status.padEnd(9)} ${t.gate} ${(t.angle ?? '-').padEnd(5)} ${(t.finding_id ?? '-').padEnd(4)} ${(t.severity ?? '-').padEnd(8)} ${t.instruction}` +
            (t.escalation_level ? `  [Escalation level ${t.escalation_level}]` : '') +
            (person.role === 'supervisor' ? `  -> ${this.name(t.assignee_id)}` : ''),
        );
      }
      case '/who':
      case '/roster':
        return this.roster_().map((p) => {
          const v = this.view(p);
          return `${v.person_id.padEnd(10)} ${ROLE_LABEL[v.role].padEnd(11)} shift ${v.shift.padEnd(6)} ${(v.signed_in ? 'signed in' : 'not signed in').padEnd(14)} Gates ${v.gates.join(', ') || '-'}`;
        });
      case '/accept':
        return this.recordReport(this.myTask(person, args[0]), person, 'accepted', args.slice(1).join(' ') || null, 'command').lines;
      case '/done':
        return this.recordReport(this.myTask(person, args[0]), person, 'done', args.slice(1).join(' ') || null, 'command').lines;
      case '/cant':
        return this.recordReport(this.myTask(person, args[0]), person, 'blocked', args.slice(1).join(' ') || null, 'command').lines;
      case '/reassign': {
        if (person.role === 'ramp_agent') fail(403, 'role_not_allowed', 'Only a Ramp Lead or the supervisor can move a Task');
        if (args.length < 2) bad('Usage: /reassign K-3 <person>');
        const target = this.find(args[1]);
        if (!target) fail(404, 'not_found', `No such person: ${args[1]}`);
        const t = this.reassign(args[0], target.person_id, args.slice(2).join(' ') || `moved by ${person.name}`, person.person_id);
        return [`${t.task_id} is now with ${who(target)}.`];
      }
      case '/ack':
        return this.confirm(person, args[0], 'acknowledged');
      case '/removed':
        return this.confirm(person, args[0], 'removed', { source: args.slice(1).join(' ') || null });
      case '/false-alarm': {
        const reason = (args[1] ?? 'other').toLowerCase();
        if (!FALSE_ALARM_REASONS.includes(reason)) bad(`Reason must be one of ${FALSE_ALARM_REASONS.join(', ')}`);
        return this.confirm(person, args[0], 'false_alarm', { reason });
      }
      case '/not-found':
        return this.confirm(person, args[0], 'not_found_on_walk');
      case '/reported': {
        const { finding } = this.findingByLabel(args[0]);
        if (finding.zone_tier !== 'outside_boundary') {
          bad('/reported is for debris outside the gate safety envelope; use /removed, /false-alarm or /not-found');
        }
        return this.confirm(person, args[0], 'acknowledged');
      }
      case '/all-removed': {
        const by = this.actor(person);
        const { gate, latest } = this.gateReport(args[0]);
        const before = this.backend.events.length;
        const rep = this.backend.confirmAll(latest.inspection_id, by);
        const n = this.backend.events.slice(before).filter((e) => e.type === 'finding_confirmed').length;
        const holds = openFindings(rep).filter((x) => x.severity === 'HOLD');
        return [
          `Recorded: ${n} REMOVE / ADVISORY Finding${plural(n)} at ${gate} removed, confirmed by ${who(person)}.` +
            (holds.length > 0 ? ` ${holds.length} HOLD stays open: a HOLD is never part of this.` : ''),
        ];
      }
      case '/eye': {
        const by = this.actor(person);
        const { gate, latest } = this.gateReport(args[0]);
        const angle = (args[1] ?? '').toUpperCase() as AngleName;
        this.backend.checkedByEye(latest.inspection_id, angle, by);
        return [`Recorded: ${gate} ${angle} checked by eye by ${who(person)}. The Verdict stays INCOMPLETE: the cameras did not cover it.`];
      }
      case '/signoff': {
        const by = this.actor(person);
        const { gate, latest } = this.gateReport(args[0]);
        this.backend.signoff(latest.inspection_id, by);
        return [`Inspection signed off by ${who(person)}. ${gate} confirmed clear.`];
      }
      case '/reinspect':
        return this.reinspectCmd(person, args);
      case '/break': {
        const holds = this.holdsOpenHold(person);
        if (holds.length > 0) {
          fail(409, 'open_hold', `You hold an open HOLD Task (${holds.map((t) => t.task_id).join(', ')}). Hand it over first: /handover <person>`);
        }
        person.shift = 'break';
        const left = this.activeTasks({ assigneeId: person.person_id }).length;
        return [`You are on a break. No new Tasks will come to you. Type /back when you return.${left ? ` You still hold ${left} open Task${plural(left)}.` : ''}`];
      }
      case '/back':
        person.shift = 'on';
        this.resync();
        return ['You are back on shift.'];
      case '/handover': {
        const target = this.find(args[0]);
        if (!target || target.person_id === person.person_id) bad('Usage: /handover <person>');
        const tasks = this.activeTasks({ assigneeId: person.person_id });
        if (tasks.length === 0) fail(409, 'nothing_to_hand_over', 'You have no open Tasks to hand over');
        if (target.shift !== 'on') fail(409, 'refused', `${target.name} is not on shift (${target.shift})`);
        const blockedIds = tasks.filter((t) => !roleMayTake(target.role, t.type)).map((t) => t.task_id);
        if (blockedIds.length > 0) {
          fail(403, 'role_not_allowed', `${target.name} is a ${ROLE_LABEL[target.role]} and cannot take ${blockedIds.join(', ')} (a Ramp Lead is required)`);
        }
        const prop = this.createProposal(
          target.person_id,
          { kind: 'handover', from_id: person.person_id, text: `take over ${tasks.length} Task(s) from ${person.name}` },
          person.person_id,
        );
        const brief = tasks.map((t) => `${t.task_id} ${t.gate} ${t.finding_id ?? t.angle ?? ''} ${t.severity ?? ''}: ${t.instruction} (${t.status})`.replace(/ {2,}/g, ' '));
        this.send(target.person_id, `Handover from ${who(person)}:\n${brief.join('\n')}\nTake these over?   [y / n]   (${prop.proposal_id})`, {
          from: person.person_id,
          proposalId: prop.proposal_id,
        });
        return [`Asked ${who(target)} to take over ${tasks.length} Task${plural(tasks.length)}. They stay yours until they accept.`];
      }
      case '/shift': {
        if (person.role !== 'supervisor') fail(403, 'role_not_allowed', "Only the supervisor sets someone else's shift; use /break and /back");
        const target = this.find(args[0]);
        const status = (args[1] ?? '').toLowerCase();
        if (!target || args.length < 2) bad('Usage: /shift <person> on|break|off');
        if (status !== 'on' && status !== 'break' && status !== 'off') fail(422, 'invalid_request', 'shift must be one of on, break, off');
        if (status !== 'on' && this.holdsOpenHold(target).length > 0) {
          fail(409, 'open_hold', `${target.name} holds an open HOLD Task; move it first with /reassign`);
        }
        target.shift = status;
        this.resync();
        return [`${target.name} is now ${status}.`];
      }
      case '/msg': {
        if (person.role !== 'supervisor') fail(403, 'role_not_allowed', 'Only the supervisor uses /msg; type plain text to reach the agent');
        const target = this.find(args[0]);
        if (!target || args.length < 2) bad('Usage: /msg <person> <text>');
        this.send(target.person_id, args.slice(1).join(' '), { kind: 'person', from: person.person_id });
        return [`Sent to ${target.name}.`];
      }
      default:
        return bad(`Unknown command ${cmd}. Type /help.`);
    }
  }

  private resync(): void {
    for (const gate of GATES) {
      const turn = this.backend.currentTurn(gate);
      if (turn) this.syncTurn(turn.turn_id);
    }
  }

  /** `{ gate, angle }` when running this command now would take a new photo. */
  private peekReinspect(person: PersonRow, text: string): { gate: string; angle: string } | null {
    if (person.role === 'supervisor') return null;
    try {
      const parts = text.split(' ');
      const cmd = (parts[0] ?? '').toLowerCase();
      const holdRemoval = (label: string | undefined) => {
        const { report, finding: f } = this.resolve(label);
        return f.severity === 'HOLD' && f.status === 'acknowledged' && person.role === 'ramp_lead' ? { gate: report.gate, angle: f.angle } : null;
      };
      if (cmd === '/removed') return holdRemoval(parts[1]);
      if (cmd === '/reinspect') {
        const { gate, latest } = this.gateReport(parts[1]);
        const angle = (parts[2] ?? '').toUpperCase();
        return latest.status !== 'inspecting' && (ANGLE_ORDER as readonly string[]).includes(angle) ? { gate, angle } : null;
      }
      if (cmd in ANSWERS && ANSWERS[cmd]) {
        const pending = this.pendingProposals(person.person_id).filter((p) => !parts[1] || p.proposal_id === parts[1].toUpperCase());
        const a = pending[0]?.action;
        if (a?.kind === 'reinspect' && a.gate && a.angle) return { gate: a.gate, angle: a.angle };
        if (a?.kind === 'confirm' && a.outcome === 'removed') return holdRemoval(a.label);
      }
    } catch {
      return null;
    }
    return null;
  }

  // ------------------------------------------------------------------ the API (shapes as fodgate/api.py)

  roster(): RosterResponse {
    return { people: this.roster_().map((p) => this.view(p)) };
  }

  join(personId: string, pin: string): JoinResponse {
    const person = this.find(personId);
    if (!person || person.pin !== String(pin)) fail(401, 'bad_credentials', 'Unknown person or wrong PIN');
    const bytes = new Uint8Array(18);
    crypto.getRandomValues(bytes);
    const token = `mock-${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`;
    this.sessions.set(token, person.person_id);
    this.seen.set(person.person_id, Date.now());
    this.writeLog('code', `${who(person)} signed in.`, { event: 'signed_in', actor: person.person_id });
    return { token, person: this.view(person) };
  }

  inbox(token: string, after = 0): Inbox {
    const person = this.session(token);
    const pid = person.person_id;
    const messages = this.messages.filter((m) => (m.to === pid || m.from === pid) && m.message_id > after).slice(0, 500);
    const mine = person.role === 'supervisor' ? this.tasks : this.tasks.filter((t) => t.assignee_id === pid);
    const active = mine.filter((t) => ACTIVE.includes(t.status));
    const closed = mine.filter((t) => !ACTIVE.includes(t.status)).slice(-10);
    return {
      person: this.view(person),
      epoch: this.epoch,
      clock_t: Math.round(this.clock() * 10) / 10,
      cursor: messages.at(-1)?.message_id ?? after,
      messages: messages.map((m) => ({ ...m })),
      tasks: [...active, ...closed].sort((a, b) => a.seq - b.seq).map((t) => this.taskView(t)),
      pending_proposals: this.pendingProposals(pid).map((p) => this.proposalView(p)),
    };
  }

  /** First half of a command: check the session, put the command in the thread, announce a re-inspection. */
  beginCommand(token: string, raw: string): PendingCommand {
    const person = this.session(token);
    const text = (raw ?? '').split(/\s+/).filter(Boolean).join(' ');
    if (!isCommand(text)) bad('A command starts with / (or is y / n). Type /help.');
    this.send('code', text, { kind: 'command', from: person.person_id });
    const shot = this.peekReinspect(person, text);
    if (shot) this.send(person.person_id, `Re-inspecting ${shot.gate} ${shot.angle} ...`);
    return { person, text, reinspects: shot !== null };
  }

  /** Second half: run it as that person. A refusal goes into their thread and is thrown. */
  finishCommand(pending: PendingCommand): CommandResult {
    const { person, text } = pending;
    let lines: string[];
    try {
      lines = this.run(person, text);
    } catch (raised) {
      const err = raised instanceof DispatchError ? new ApiError('refused', raised.message, 409) : raised;
      if (!(err instanceof ApiError)) throw err;
      this.send(person.person_id, `Refused (${err.code}): ${err.message}`);
      this.writeLog('code', `Refused (${err.code}): ${err.message}`, {
        event: 'command_refused',
        actor: person.person_id,
        data: { command: text, error: err.code },
      });
      this.step();
      throw err;
    }
    this.send(person.person_id, lines.join('\n'));
    this.step();
    return { ok: true, lines };
  }

  command(token: string, text: string): CommandResult {
    return this.finishCommand(this.beginCommand(token, text));
  }

  /** Free text goes to the (mock) agent on the next `drainWakes`; a command is run as one. */
  say(token: string, raw: string): SayResult {
    const person = this.session(token);
    const text = (raw ?? '').split(/\s+/).filter(Boolean).join(' ');
    if (!text || text.length > 500) fail(422, 'invalid_request', 'text must be 1 to 500 characters');
    if (isCommand(text)) return { ...this.command(token, text), routed: 'command' };
    const id = this.send('agent', text, { kind: 'person', from: person.person_id });
    this.wakes.push({ person_id: person.person_id, message_id: id, text });
    this.idleAnnounced = false;
    return { ok: true, routed: 'agent', message_id: id };
  }

  cost(): AgentCost {
    return {
      agent_session_usd: Number(this.spend.usd.toFixed(6)),
      wakes: this.spend.wakes,
      tokens_in: this.spend.tokens_in,
      tokens_out: this.spend.tokens_out,
      model_requests: 0,
      process_usd: Number(this.spend.usd.toFixed(6)),
      cap_usd: null,
    };
  }

  activity(q: ActivityQuery = {}): ActivityResponse {
    const after = q.after ?? 0;
    const limit = Math.max(1, Math.min(q.limit ?? 500, 1000));
    const rows = this.log
      .filter((e) => e.id > after && (!q.gate || e.gate === q.gate) && (!q.turn_id || e.turn_id === q.turn_id))
      .slice(0, limit);
    return { epoch: this.epoch, cursor: rows.at(-1)?.id ?? after, entries: rows.map((e) => ({ ...e })), cost: this.cost() };
  }

  board(): Board {
    return {
      mode: 'mock',
      model: MOCK_MODEL,
      model_available: false,
      model_note: 'Mock mode: no model is called',
      clock_t: Math.round(this.clock() * 10) / 10,
      tasks: this.tasks.slice(-100).map((t) => ({ ...this.taskView(t), reports: t.reports.map((r) => ({ ...r })) })),
      roster: this.roster_().map((p) => ({ ...this.view(p), open_tasks: this.activeTasks({ assigneeId: p.person_id }).length })),
      timers: this.timers.filter((t) => !t.fired && !t.cancelled).map((t) => ({ task_id: t.task_id, kind: t.kind, fire_t: t.fire_t })),
      activity: this.log.slice(-60).map((e) => ({ ...e })),
      cost: this.cost(),
    };
  }
}
