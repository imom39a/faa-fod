/**
 * In-memory mock of the backend rules in app/CONTRACT.md section 2: role
 * checks, HOLD acknowledge → removed → re-inspection, sign-off preconditions,
 * Gate status, the "Needs a human" queue and the demo clock.
 *
 * It has no timers of its own: the caller advances the clock, so tests are
 * deterministic. `mockApi.ts` wraps it with real-time ticking and latency.
 */
import rulesJson from '../../../data/rules/fod-rules.json';
import { ApiError } from '../api/client';
import {
  ANGLE_ORDER,
  type AngleName,
  type AssistantResponse,
  type ConfirmBody,
  type DemoSpeed,
  type Finding,
  type GateState,
  type GateStatus,
  type InspectBody,
  type InspectionKind,
  type Person,
  type QueueItem,
  type Report,
  type ReportAngle,
  type RuleSet,
  type Severity,
  type State,
  type Turn,
  type TurnPhase,
} from '../api/types';
import {
  DEMO_DURATION,
  DEMO_PRELUDE,
  GATES,
  IMAGE_SIZE,
  SCENES,
  TURNS,
  attributionFor,
  imageUrl,
  type FindingSeed,
  type FrameDef,
  type MockEvent,
  type SceneDef,
  type TurnDef,
} from './fixtures';

export const RULES = rulesJson as unknown as RuleSet;

/** Demo seconds an Inspection spends in `inspecting` before its Verdict appears. */
export const ANALYSIS_SECONDS = 4;
/** One demo second stands for this many seconds of gate time (a 6-minute demo ≈ a 36-minute window). */
export const GATE_TIME_SCALE = 6;
const BASE_TIME = Date.UTC(2026, 10, 13, 14, 0, 0);
const SCRIPTED_LEAD: Person = { role: 'ramp_lead', name: 'T. Alvarez (scripted)' };
const SEVERITY_RANK: Record<Severity, number> = { HOLD: 3, REMOVE: 2, ADVISORY: 1 };

/** The frame an Angle currently shows, plus what a re-inspection needs to know. */
type AngleFrame = { frame: FrameDef; reference: string | null; analysis: string };
type Frames = Record<AngleName, AngleFrame>;

type TurnRuntime = {
  def: TurnDef;
  phase: TurnPhase | null;
  ended: boolean;
  fired: Set<number>;
  delayed: Set<number>;
  reports: Report[];
};

export type MockFixtures = { scenes: SceneDef[]; turns: TurnDef[]; duration: number; prelude: number };

const DEFAULT_FIXTURES: MockFixtures = { scenes: SCENES, turns: TURNS, duration: DEMO_DURATION, prelude: DEMO_PRELUDE };

function fail(status: number, code: string, message: string): never {
  throw new ApiError(code, message, status);
}

function ruleRef(id: string) {
  const r = RULES.rules.find((x) => x.id === id);
  return { id, text: r?.text ?? '', basis: r?.basis ?? '' };
}

function ruleIdFor(seed: FindingSeed, angle: AngleName): string {
  if (seed.finding_type === 'equipment_staging') return RULES.rule_for.equipment_staging ?? 'FOD-R9';
  if (seed.zone_tier === 'outside_boundary') return RULES.rule_for.outside_boundary ?? 'FOD-R10';
  if (seed.zone_tier === 'critical') {
    return (angle === 'NOSE' ? RULES.rule_for.critical_nose : RULES.rule_for.critical_engine) ?? 'FOD-R1';
  }
  return (seed.zone_tier === 'service' ? RULES.rule_for.service : RULES.rule_for.general) ?? 'FOD-R4';
}

function severityFor(seed: FindingSeed): Severity {
  if (seed.finding_type === 'equipment_staging') return 'REMOVE';
  return RULES.severity_matrix[seed.object_class][seed.zone_tier];
}

export function isOpen(f: Finding): boolean {
  if (f.status === 'confirmed') return false;
  return !(f.status === 'acknowledged' && f.zone_tier === 'outside_boundary');
}

/** What the real store records as an event; the mock dispatcher (dispatch.ts) reads these in order. */
export type MockStoreEvent = {
  id: number;
  /** Demo seconds at which it happened (negative for the prelude before the demo starts). */
  t: number;
  type: 'inspection_completed' | 'finding_acknowledged' | 'finding_confirmed' | 'angle_checked_by_eye' | 'inspection_signed_off' | 'departed';
  gate: string;
  turn_id: string;
  data: { inspection_id?: string; finding_id?: string; outcome?: string; angle?: string; by?: Person };
};

/** A Turn as the mock dispatcher needs it. `pushback_t` is in demo seconds. */
export type MockTurnInfo = {
  turn_id: string;
  gate: string;
  flight: string;
  phase: TurnPhase;
  minutes_to_pushback: number | null;
  pushback_t: number | null;
};

export class MockBackend {
  /** Bumped by reset(), so cursors held elsewhere start again. */
  epoch = 0;
  /** Every state change, oldest first. Cleared by reset(). */
  events: MockStoreEvent[] = [];
  private t = 0;
  private playing = false;
  private speed: DemoSpeed = 1;
  private seq = 0;
  /** Time used for timestamps while a scripted event is being applied. */
  private stamp = 0;
  private turns: TurnRuntime[] = [];
  private pending: { inspectionId: string; readyAt: number }[] = [];
  private frames = new Map<string, Frames>();
  private seedKeys = new Map<string, string>();
  private readonly fx: MockFixtures;
  private readonly startAt: number;

  constructor(options: { fixtures?: MockFixtures; startAt?: number } = {}) {
    this.fx = options.fixtures ?? DEFAULT_FIXTURES;
    this.startAt = options.startAt ?? 0;
    this.reset();
  }

  // ---------------------------------------------------------------- demo clock

  reset(): State {
    this.playing = false;
    this.seq = 0;
    this.epoch += 1;
    this.events = [];
    this.pending = [];
    this.frames.clear();
    this.seedKeys.clear();
    this.turns = this.fx.turns.map((def) => ({
      def,
      phase: null,
      ended: false,
      fired: new Set(),
      delayed: new Set(),
      reports: [],
    }));
    this.t = this.fx.prelude;
    this.advanceTo(Math.min(Math.max(this.startAt, 0), this.fx.duration));
    return this.getState();
  }

  play(): State {
    if (this.t < this.fx.duration) this.playing = true;
    return this.getState();
  }

  pause(): State {
    this.playing = false;
    return this.getState();
  }

  setSpeed(speed: number): State {
    if (speed !== 1 && speed !== 2 && speed !== 5 && speed !== 10) {
      fail(422, 'invalid_speed', 'Speed must be 1, 2, 5 or 10.');
    }
    this.speed = speed;
    return this.getState();
  }

  /** Advance by wall-clock seconds; the demo clock moves only while playing. */
  tick(realSeconds: number): void {
    if (!this.playing) return;
    this.advanceTo(this.t + realSeconds * this.speed);
  }

  advanceTo(t: number): void {
    this.t = Math.min(Math.max(t, this.t), this.fx.duration);
    this.processDue();
    if (this.t >= this.fx.duration) this.playing = false;
  }

  /** Apply every scripted event and analysis completion that is due, in time order. */
  private processDue(): void {
    for (;;) {
      let best: { time: number; run: () => void } | null = null;
      const offer = (time: number, run: () => void) => {
        if (!best || time < best.time) best = { time, run };
      };
      for (const turn of this.turns) {
        // Events of one Turn fire strictly in order; a blocked one holds back the rest.
        const i = turn.def.events.findIndex((_, idx) => !turn.fired.has(idx));
        const e = i >= 0 ? turn.def.events[i] : undefined;
        if (!e || e.t > this.t) continue;
        if (!this.canFire(turn, e)) {
          turn.delayed.add(i);
          continue;
        }
        const time = turn.delayed.has(i) ? this.t : e.t;
        offer(time, () => {
          turn.fired.add(i);
          this.applyEvent(turn, e);
        });
      }
      for (const p of this.pending) {
        if (p.readyAt <= this.t) offer(p.readyAt, () => this.completeInspection(p.inspectionId));
      }
      if (!best) break;
      const { time, run } = best as { time: number; run: () => void };
      this.stamp = time;
      run();
    }
    this.stamp = this.t;
  }

  private canFire(turn: TurnRuntime, e: MockEvent): boolean {
    if (e.type === 'scheduled_pushback') {
      // No pushback until a person has signed off the pre-departure Inspection.
      const latest = turn.reports.at(-1);
      return turn.phase === 'pre_departure' && latest?.status === 'confirmed';
    }
    return true;
  }

  private applyEvent(turn: TurnRuntime, e: MockEvent): void {
    switch (e.type) {
      case 'stand_prep':
        turn.phase = 'stand_prep';
        break;
      case 'block_in':
        turn.phase = 'on_stand';
        break;
      case 'inspection': {
        const kind = e.kind ?? 'on_demand';
        if (kind === 'pre_arrival') turn.phase = 'pre_arrival';
        if (kind === 'pre_departure') turn.phase = 'pre_departure';
        const report = this.startInspection(turn, kind, this.framesForScene(e.scene_id));
        this.pending.push({ inspectionId: report.inspection_id, readyAt: this.stamp + ANALYSIS_SECONDS });
        break;
      }
      case 'auto_signoff': {
        const latest = turn.reports.at(-1);
        if (latest && latest.status === 'awaiting_confirmation' && this.blockers(latest) === null) {
          latest.inspection_signoff = { by: SCRIPTED_LEAD, at: this.iso() };
          latest.status = 'confirmed';
          this.emit('inspection_signed_off', latest, { by: SCRIPTED_LEAD });
        }
        break;
      }
      case 'scheduled_pushback':
        turn.phase = 'departed';
        this.events.push({ id: this.events.length + 1, t: this.stamp, type: 'departed', gate: turn.def.gate, turn_id: turn.def.turn_id, data: {} });
        break;
      case 'turn_end':
        turn.ended = true;
        break;
    }
  }

  // ------------------------------------------------------------------- queries

  getState(): State {
    const gates = GATES.map((g) => this.gateState(g));
    return {
      demo: { playing: this.playing, speed: this.speed, t: Math.max(0, this.t), duration: this.fx.duration },
      gates,
      queue: this.queue(),
    };
  }

  getTurn(turnId: string): Turn {
    const turn = this.turns.find((x) => x.def.turn_id === turnId && x.phase !== null);
    if (!turn) fail(404, 'not_found', `Turn ${turnId} not found.`);
    return {
      turn_id: turn.def.turn_id,
      gate: turn.def.gate,
      flight: turn.def.flight,
      aircraft_type: turn.def.aircraft_type,
      inspections: turn.reports,
      events: turn.def.events
        .filter((e) => e.type !== 'auto_signoff' && e.type !== 'turn_end')
        .map((e) => ({ ...e })),
    };
  }

  getInspection(id: string): Report {
    return this.find(id).report;
  }

  getRules(): RuleSet {
    return RULES;
  }

  // ------------------------------------------------- read access for the mock dispatcher

  /** Demo seconds. */
  clock(): number {
    return this.t;
  }

  finished(): boolean {
    return this.t >= this.fx.duration;
  }

  demoSpeed(): number {
    return this.speed;
  }

  private turnInfo(turn: TurnRuntime): MockTurnInfo {
    const push = turn.def.events.find((e) => e.type === 'scheduled_pushback');
    return {
      turn_id: turn.def.turn_id,
      gate: turn.def.gate,
      flight: turn.def.flight,
      phase: turn.phase ?? 'stand_prep',
      minutes_to_pushback: this.minutesToPushback(turn),
      pushback_t: push ? push.t : null,
    };
  }

  /** The Turn in progress at a Gate, if any. */
  currentTurn(gate: string): MockTurnInfo | null {
    const turn = this.activeTurn(gate);
    return turn ? this.turnInfo(turn) : null;
  }

  turn(turnId: string): MockTurnInfo | null {
    const turn = this.turns.find((x) => x.def.turn_id === turnId && x.phase !== null);
    return turn ? this.turnInfo(turn) : null;
  }

  /** The Turn's Inspections, oldest first (live objects: read only). */
  reportsForTurn(turnId: string): Report[] {
    return this.turns.find((x) => x.def.turn_id === turnId)?.reports ?? [];
  }

  /** Identity of the physical item behind a Finding: the same across re-inspections. */
  itemKey(findingId: string): string | null {
    return this.seedKeys.get(findingId) ?? null;
  }

  private emit(type: MockStoreEvent['type'], report: Report, data: MockStoreEvent['data'] = {}): void {
    this.events.push({
      id: this.events.length + 1,
      t: this.stamp,
      type,
      gate: report.gate,
      turn_id: report.turn_id,
      data: { inspection_id: report.inspection_id, ...data },
    });
  }

  private activeTurn(gate: string): TurnRuntime | undefined {
    return this.turns.find((x) => x.def.gate === gate && x.phase !== null && !x.ended);
  }

  private minutesToPushback(turn: TurnRuntime): number | null {
    if (turn.phase === 'departed') return null;
    const push = turn.def.events.find((e) => e.type === 'scheduled_pushback');
    if (!push) return null;
    return Math.round(((push.t - this.t) * GATE_TIME_SCALE) / 60);
  }

  private gateState(gate: string): GateState {
    const turn = this.activeTurn(gate);
    if (!turn) return { gate, status: 'idle', verdict: null, highest_open_severity: null, turn: null };
    const latest = turn.reports.at(-1);
    let status: GateStatus;
    if (turn.phase === 'departed') status = 'departed';
    else if (!latest) status = turn.phase === 'on_stand' ? 'on_stand' : 'awaiting_pre_arrival';
    else if (latest.status === 'inspecting') status = 'inspecting';
    else if (latest.status === 'awaiting_confirmation') status = 'awaiting_confirmation';
    else status = turn.phase === 'on_stand' ? 'on_stand' : 'confirmed_clear';
    const showVerdict = status === 'awaiting_confirmation' || status === 'confirmed_clear';
    return {
      gate,
      status,
      verdict: showVerdict && latest ? latest.verdict : null,
      highest_open_severity: status === 'awaiting_confirmation' && latest ? latest.highest_open_severity : null,
      turn: {
        turn_id: turn.def.turn_id,
        flight: turn.def.flight,
        aircraft_type: turn.def.aircraft_type,
        phase: turn.phase ?? 'stand_prep',
        minutes_to_pushback: this.minutesToPushback(turn),
        latest_inspection_id: latest?.inspection_id ?? null,
      },
    };
  }

  /** "Needs a human": HOLDs first, then by minutes to pushback ascending. */
  private queue(): QueueItem[] {
    const items: QueueItem[] = [];
    for (const gate of GATES) {
      const turn = this.activeTurn(gate);
      const latest = turn?.reports.at(-1);
      if (!turn || !latest || latest.status !== 'awaiting_confirmation') continue;
      const open = latest.findings.filter(isOpen);
      const unusable = latest.angles.filter((a) => a.status === 'unusable' && !a.checked_by_eye);
      const base = {
        gate,
        turn_id: turn.def.turn_id,
        inspection_id: latest.inspection_id,
        minutes_to_pushback: this.minutesToPushback(turn),
      };
      const holds = open.filter((f) => f.severity === 'HOLD');
      if (holds.length > 0) {
        const first = holds[0]!;
        const more = holds.length > 1 ? ` (+${holds.length - 1} more HOLD)` : '';
        items.push({ ...base, reason: 'hold', severity: 'HOLD', text: `${first.description}${more}` });
      } else if (open.length > 0) {
        items.push({
          ...base,
          reason: 'findings',
          severity: latest.highest_open_severity,
          text: `${open.length} open ${open.length === 1 ? 'Finding' : 'Findings'} to confirm (${[...new Set(open.map((f) => f.angle))].join(', ')})`,
        });
      } else if (unusable.length > 0) {
        items.push({
          ...base,
          reason: 'incomplete',
          severity: null,
          text: `${unusable.map((a) => a.angle).join(', ')} unusable: re-inspect, or a Ramp Lead checks by eye`,
        });
      } else {
        items.push({
          ...base,
          reason: 'signoff',
          severity: null,
          text: `${latest.verdict === 'ALL_CLEAR' ? 'ALL CLEAR (advisory)' : 'All Findings confirmed'}: sign off the Inspection`,
        });
      }
    }
    const far = Number.POSITIVE_INFINITY;
    return items.sort(
      (a, b) =>
        Number(b.reason === 'hold') - Number(a.reason === 'hold') ||
        (a.minutes_to_pushback ?? far) - (b.minutes_to_pushback ?? far),
    );
  }

  // ------------------------------------------------------------------ actions

  confirmFinding(inspectionId: string, findingId: string, body: ConfirmBody): Report {
    const { turn, report } = this.findActionable(inspectionId);
    const finding = report.findings.find((f) => f.finding_id === findingId);
    if (!finding) fail(404, 'not_found', `Finding ${findingId} not found.`);
    if (finding.status === 'confirmed') fail(409, 'already_confirmed', 'This Finding already has a Confirmation.');
    const who = this.person(body);
    if (finding.severity === 'HOLD' && who.role !== 'ramp_lead') {
      fail(403, 'role_not_allowed', 'Only a Ramp Lead can confirm a HOLD Finding.');
    }

    if (body.outcome === 'acknowledged') {
      finding.status = 'acknowledged';
      this.emit('finding_acknowledged', report, { finding_id: finding.finding_id, by: who });
      return this.touch(report);
    }
    if (body.outcome === 'false_alarm' && !body.false_alarm_reason) {
      fail(422, 'false_alarm_reason_required', 'Pick a reason for the false alarm.');
    }
    const confirmation = {
      outcome: body.outcome,
      false_alarm_reason: body.outcome === 'false_alarm' ? (body.false_alarm_reason ?? null) : null,
      confirmed_by: who,
      confirmed_at: this.iso(),
      after_photo_ref: null as string | null,
      possible_source: body.possible_source?.trim() || null,
    };

    if (finding.severity === 'HOLD' && body.outcome === 'removed') {
      if (finding.status !== 'acknowledged') {
        fail(409, 'hold_needs_acknowledge', 'A HOLD must be acknowledged before it is recorded as removed.');
      }
      // "Removed" on a HOLD re-inspects the Angle; the Confirmation is recorded
      // only if the item is gone from the new frame.
      const next = this.reinspect(turn, report, finding.angle);
      const key = this.seedKeys.get(finding.finding_id);
      const stillThere = next.findings.some((f) => f.angle === finding.angle && this.seedKeys.get(f.finding_id) === key);
      if (!stillThere) {
        const angle = next.angles.find((a) => a.angle === finding.angle);
        next.findings.push({
          ...structuredClone(finding),
          status: 'confirmed',
          carried_from_inspection_id: finding.carried_from_inspection_id ?? report.inspection_id,
          confirmation: { ...confirmation, after_photo_ref: angle?.image_ref ?? null },
        });
        this.sortFindings(next);
        this.emit('finding_confirmed', next, { finding_id: finding.finding_id, outcome: 'removed', by: who });
      }
      return this.touch(next);
    }

    finding.status = 'confirmed';
    finding.confirmation = confirmation;
    this.emit('finding_confirmed', report, { finding_id: finding.finding_id, outcome: body.outcome, by: who });
    return this.touch(report);
  }

  confirmAll(inspectionId: string, body: Person): Report {
    const { report } = this.findActionable(inspectionId);
    const who = this.person(body);
    for (const f of report.findings) {
      if (f.status !== 'open' || f.severity === 'HOLD') continue;
      f.status = 'confirmed';
      f.confirmation = {
        outcome: 'removed',
        false_alarm_reason: null,
        confirmed_by: who,
        confirmed_at: this.iso(),
        after_photo_ref: null,
        possible_source: null,
      };
      this.emit('finding_confirmed', report, { finding_id: f.finding_id, outcome: 'removed', by: who });
    }
    return this.touch(report);
  }

  reinspectAngle(inspectionId: string, angle: AngleName, body: Person): Report {
    const { turn, report } = this.findActionable(inspectionId);
    this.person(body);
    if (!ANGLE_ORDER.includes(angle)) fail(404, 'not_found', `Angle ${angle} not found.`);
    return this.touch(this.reinspect(turn, report, angle));
  }

  checkedByEye(inspectionId: string, angle: AngleName, body: Person): Report {
    const { report } = this.findActionable(inspectionId);
    const who = this.person(body);
    if (who.role !== 'ramp_lead') {
      fail(403, 'role_not_allowed', 'Only a Ramp Lead can record an Angle as checked by eye.');
    }
    const a = report.angles.find((x) => x.angle === angle);
    if (!a) fail(404, 'not_found', `Angle ${angle} not found.`);
    if (a.status !== 'unusable') fail(409, 'angle_usable', `${angle} is usable; there is nothing to check by eye.`);
    a.checked_by_eye = { by: who, at: this.iso() };
    this.emit('angle_checked_by_eye', report, { angle, by: who });
    return this.touch(report);
  }

  signoff(inspectionId: string, body: Person): Report {
    const { report } = this.findActionable(inspectionId);
    const who = this.person(body);
    const blocked = this.blockers(report);
    if (blocked === 'open_findings') {
      fail(409, 'open_findings', 'Sign-off needs every Finding confirmed first.');
    }
    if (blocked === 'unusable_angles') {
      fail(409, 'unusable_angles', 'Every unusable Angle must be re-inspected or checked by eye first.');
    }
    report.inspection_signoff = { by: who, at: this.iso() };
    report.status = 'confirmed';
    this.emit('inspection_signed_off', report, { by: who });
    return this.touch(report);
  }

  /** Manual trigger. The Report stays `inspecting` until `completeInspection` is called. */
  inspectGate(gate: string, body: InspectBody): Report {
    const turn = this.activeTurn(gate);
    if (!turn || turn.phase === 'departed') fail(409, 'no_active_turn', `Gate ${gate} has no Turn to inspect.`);
    const latest = turn.reports.at(-1);
    if (latest?.status === 'inspecting') fail(409, 'inspection_running', 'An Inspection is already running at this Gate.');
    const latestFrames = latest ? this.frames.get(latest.inspection_id) : undefined;
    const frames = body.scene_id || !latestFrames ? this.framesForScene(body.scene_id) : latestFrames;
    const report = this.startInspection(turn, body.kind, frames, latest ?? null);
    return structuredClone(report);
  }

  completeInspection(inspectionId: string): void {
    this.pending = this.pending.filter((p) => p.inspectionId !== inspectionId);
    const found = this.turns.flatMap((x) => x.reports).find((r) => r.inspection_id === inspectionId);
    if (!found || found.status !== 'inspecting') return;
    const turn = this.turns.find((x) => x.reports.includes(found))!;
    const frames = this.frames.get(inspectionId)!;
    const done = this.buildReport(turn, found.kind, frames, {
      id: inspectionId,
      capturedAt: found.captured_at,
      parentId: found.parent_inspection_id,
    });
    Object.assign(found, done);
    this.emit('inspection_completed', found);
  }

  assistant(inspectionId: string, message: string): AssistantResponse {
    const { report } = this.find(inspectionId);
    const open = report.findings.filter(isOpen);
    const unusable = report.angles.filter((a) => a.status === 'unusable' && !a.checked_by_eye);
    const lowConfidence = open.filter((f) => f.confidence === 'low');
    const suggested = [...new Set([...unusable.map((a) => a.angle), ...lowConfidence.map((f) => f.angle)])];
    const outside = report.findings.filter((f) => f.zone_tier === 'outside_boundary');
    const lines = [
      `Mock assistant reply (no model was called). Gate ${report.gate}, ${report.kind.replace('_', '-')} Inspection: Verdict ${report.verdict?.replace('_', ' ') ?? 'pending'} (advisory until a person confirms).`,
    ];
    if (open.length > 0) {
      lines.push(
        `Open Findings: ${open.map((f) => `${f.severity} in ${f.angle} under ${f.rule_id} (${f.description.replace(/\.$/, '')})`).join('; ')}.`,
      );
    } else {
      lines.push('There are no open Findings.');
    }
    if (unusable.length > 0) {
      lines.push(
        `${unusable.map((a) => `${a.angle} is unusable (${a.unusable_reason})`).join('; ')}. Re-inspect, or a Ramp Lead records it as checked by eye.`,
      );
    }
    if (lowConfidence.length > 0) {
      lines.push('Low-confidence Findings keep their severity; a re-inspection or a walk settles them.');
    }
    const wantsReport = /report|draft|airport|ops|ramp 1/i.test(message);
    const draft =
      wantsReport || outside.length > 0
        ? [
            `FOD REPORT - Gate ${report.gate}, Turn ${report.turn_id}`,
            `Inspection ${report.inspection_id} (${report.kind}), captured ${report.captured_at}`,
            `To: ${outside.length > 0 ? 'Ramp 1 control / Airport Operations' : 'Ramp Lead'}`,
            '',
            ...(outside.length > 0 ? outside : report.findings).map(
              (f, i) => `${i + 1}. ${f.severity} ${f.rule_id}: ${f.description} Location: ${f.location_text}. Confidence: ${f.confidence}.`,
            ),
            ...(report.findings.length === 0 ? ['No Findings.'] : []),
            '',
            'Raised by the gate FOD Inspection system. Advisory until confirmed by a person.',
          ].join('\n')
        : null;
    return { reply: lines.join(' '), suggested_reinspect_angles: suggested, draft_report: draft };
  }

  // ---------------------------------------------------------------- internals

  private person(body: Partial<Person>): Person {
    if (body.role !== 'ramp_agent' && body.role !== 'ramp_lead') {
      fail(422, 'invalid_role', 'role must be ramp_agent or ramp_lead.');
    }
    const name = (body.name ?? '').trim();
    if (!name) fail(422, 'name_required', 'Enter your name before confirming.');
    return { role: body.role, name };
  }

  private find(inspectionId: string): { turn: TurnRuntime; report: Report } {
    for (const turn of this.turns) {
      const report = turn.reports.find((r) => r.inspection_id === inspectionId);
      if (report) return { turn, report };
    }
    fail(404, 'not_found', `Inspection ${inspectionId} not found.`);
  }

  /** Actions apply to the latest Inspection of a Turn, once analysed and before sign-off. */
  private findActionable(inspectionId: string): { turn: TurnRuntime; report: Report } {
    const found = this.find(inspectionId);
    if (found.report.status === 'inspecting') fail(409, 'inspection_running', 'This Inspection is still running.');
    if (found.turn.reports.at(-1) !== found.report) {
      fail(409, 'superseded', 'A later Inspection has replaced this one. Open the latest Inspection.');
    }
    if (found.report.status === 'confirmed') fail(409, 'already_signed_off', 'This Inspection is already signed off.');
    return found;
  }

  private blockers(report: Report): 'open_findings' | 'unusable_angles' | null {
    if (report.findings.some(isOpen)) return 'open_findings';
    if (report.angles.some((a) => a.status === 'unusable' && !a.checked_by_eye)) return 'unusable_angles';
    return null;
  }

  /** Recompute derived fields, run any scripted step this unblocked, return a copy. */
  private touch(report: Report): Report {
    let best: Severity | null = null;
    for (const f of report.findings) {
      if (isOpen(f) && (!best || SEVERITY_RANK[f.severity] > SEVERITY_RANK[best])) best = f.severity;
    }
    report.highest_open_severity = best;
    this.processDue();
    return structuredClone(report);
  }

  private iso(offsetSeconds = 0): string {
    return new Date(BASE_TIME + (this.stamp + offsetSeconds) * GATE_TIME_SCALE * 1000).toISOString();
  }

  private framesForScene(sceneId: string | undefined): Frames {
    const scene = this.fx.scenes.find((s) => s.scene_id === sceneId);
    if (!scene) fail(404, 'not_found', `Scene ${sceneId ?? '(none)'} not found.`);
    const frames = {} as Frames;
    for (const a of ANGLE_ORDER) {
      const { reference, analysis, ...frame } = scene.angles[a];
      frames[a] = { frame, reference, analysis };
    }
    return frames;
  }

  private startInspection(turn: TurnRuntime, kind: InspectionKind, frames: Frames, parent: Report | null = null): Report {
    const id = `insp-${String(++this.seq).padStart(3, '0')}`;
    this.frames.set(id, frames);
    const report: Report = {
      schema_version: '0.1',
      rule_set_version: RULES.version,
      inspection_id: id,
      gate: turn.def.gate,
      turn_id: turn.def.turn_id,
      kind,
      parent_inspection_id: kind === 'on_demand' ? (parent?.inspection_id ?? null) : null,
      captured_at: this.iso(),
      analysed_at: null,
      verdict: null,
      highest_open_severity: null,
      missing_angles: [],
      angles: ANGLE_ORDER.map((a) => this.angleEntry(a, frames[a], id)),
      findings: [],
      dismissed_candidates: [],
      observations: [],
      inspection_signoff: null,
      run_metadata: { local_models: [], llm_calls: [], timings_ms: {} },
      status: 'inspecting',
    };
    turn.reports.push(report);
    return report;
  }

  /** A full, analysed Report for a fresh capture of all six Angles. */
  private buildReport(
    turn: TurnRuntime,
    kind: InspectionKind,
    frames: Frames,
    meta: { id: string; capturedAt: string; parentId: string | null },
  ): Report {
    const findings: Finding[] = [];
    for (const a of ANGLE_ORDER) {
      if (!frames[a].frame.usable) continue;
      for (const seed of frames[a].frame.findings) findings.push(this.newFinding(seed, a, frames[a], null));
    }
    return this.assemble(turn, kind, frames, meta, ANGLE_ORDER.map((a) => this.angleEntry(a, frames[a], meta.id)), findings, 6);
  }

  /**
   * On-demand re-inspection of one Angle. The other Angles, their Findings and
   * Confirmations are inherited from the parent Inspection.
   */
  private reinspect(turn: TurnRuntime, parent: Report, angle: AngleName): Report {
    const parentFrames = this.frames.get(parent.inspection_id)!;
    const current = parentFrames[angle];
    const nextFrame: AngleFrame = { ...current, frame: current.frame.after ?? current.frame };
    const frames: Frames = { ...parentFrames, [angle]: nextFrame };
    const id = `insp-${String(++this.seq).padStart(3, '0')}`;
    this.frames.set(id, frames);

    const angles = parent.angles.map((a) => (a.angle === angle ? this.angleEntry(angle, nextFrame, id) : structuredClone(a)));
    const findings: Finding[] = [];
    for (const f of parent.findings) {
      if (f.angle === angle) continue;
      findings.push({ ...structuredClone(f), carried_from_inspection_id: f.carried_from_inspection_id ?? parent.inspection_id });
    }
    const seeds = nextFrame.frame.usable ? nextFrame.frame.findings : [];
    const previous = parent.findings.filter((f) => f.angle === angle);
    for (const seed of seeds) {
      const prev = previous.find((f) => this.seedKeys.get(f.finding_id) === seed.key);
      if (prev?.confirmation?.outcome === 'false_alarm') {
        // Already judged a false alarm by a person: keep that Confirmation.
        findings.push({ ...structuredClone(prev), carried_from_inspection_id: prev.carried_from_inspection_id ?? parent.inspection_id });
      } else {
        findings.push(this.newFinding(seed, angle, nextFrame, prev ? parent.inspection_id : null));
      }
    }
    for (const prev of previous) {
      // Keep the record of items confirmed earlier that are no longer in view.
      const key = this.seedKeys.get(prev.finding_id);
      if (prev.status === 'confirmed' && !seeds.some((s) => s.key === key)) {
        findings.push({ ...structuredClone(prev), carried_from_inspection_id: prev.carried_from_inspection_id ?? parent.inspection_id });
      }
    }
    const report = this.assemble(
      turn,
      'on_demand',
      frames,
      { id, capturedAt: this.iso(), parentId: parent.inspection_id },
      angles,
      findings,
      1,
    );
    this.sortFindings(report);
    turn.reports.push(report);
    this.emit('inspection_completed', report);
    return report;
  }

  private assemble(
    _turn: TurnRuntime,
    kind: InspectionKind,
    frames: Frames,
    meta: { id: string; capturedAt: string; parentId: string | null },
    angles: ReportAngle[],
    findings: Finding[],
    anglesAnalysed: number,
  ): Report {
    const unusable = angles.filter((a) => a.status === 'unusable').map((a) => a.angle);
    const candidates = findings.length + ANGLE_ORDER.reduce((n, a) => n + (frames[a].frame.dismissed?.length ?? 0), 0);
    const tokensIn = 1400 * anglesAnalysed + 900 * candidates;
    const tokensOut = 120 * anglesAnalysed + 140 * candidates;
    const netIn = 2600 * Math.min(anglesAnalysed, 3);
    const cost = (tin: number, tout: number) => Number(((tin * 1 + tout * 5) / 1_000_000).toFixed(5));
    const local = 350 * anglesAnalysed;
    const haiku = 1500 * anglesAnalysed + 600 * candidates;
    return {
      schema_version: '0.1',
      rule_set_version: RULES.version,
      inspection_id: meta.id,
      gate: _turn.def.gate,
      turn_id: _turn.def.turn_id,
      kind,
      parent_inspection_id: meta.parentId,
      captured_at: meta.capturedAt,
      analysed_at: this.iso(),
      verdict: findings.length > 0 ? 'FINDINGS' : unusable.length > 0 ? 'INCOMPLETE' : 'ALL_CLEAR',
      highest_open_severity: findings.filter(isOpen).reduce<Severity | null>(
        (best, f) => (!best || SEVERITY_RANK[f.severity] > SEVERITY_RANK[best] ? f.severity : best),
        null,
      ),
      missing_angles: unusable,
      angles,
      findings,
      dismissed_candidates: ANGLE_ORDER.flatMap((a) =>
        (frames[a].frame.dismissed ?? []).map((d) => ({ angle: a, bbox: d.bbox, reason: d.reason })),
      ),
      observations: ANGLE_ORDER.flatMap((a) => (frames[a].frame.observations ?? []).map((o) => ({ angle: a, ...o }))),
      inspection_signoff: null,
      run_metadata: {
        local_models: [
          { name: 'change-detection', version: 'mock-fixture' },
          { name: 'usability-check', version: 'mock-fixture' },
        ],
        llm_calls: [
          { model: 'claude-haiku-5-5 (mock)', purpose: 'safety_net', tokens_in: netIn, tokens_out: 90, est_cost_usd: cost(netIn, 90) },
          { model: 'claude-haiku-5-5 (mock)', purpose: 'decide', tokens_in: tokensIn, tokens_out: tokensOut, est_cost_usd: cost(tokensIn, tokensOut) },
        ],
        timings_ms: { local, haiku, sonnet: 0, total: local + haiku + 250 },
        notes: ['Mock mode: fixture data, no model was called. Figures are illustrative.'],
      },
      status: 'awaiting_confirmation',
    };
  }

  private angleEntry(angle: AngleName, af: AngleFrame, inspectionId: string): ReportAngle {
    const { frame } = af;
    return {
      angle,
      image_ref: frame.image ? `${frame.image}.jpg` : null,
      camera_id: `mock-cam-${angle.toLowerCase()}`,
      crop: null,
      status: frame.usable ? 'usable' : 'unusable',
      unusable_reason: frame.usable ? null : frame.unusable_reason,
      assessed_by: 'local_check',
      source_inspection_id: inspectionId,
      image_url: frame.image ? imageUrl(frame.image) : null,
      reference_url: af.reference ? imageUrl(af.reference) : null,
      width: IMAGE_SIZE.width,
      height: IMAGE_SIZE.height,
      checked_by_eye: null,
      attribution: frame.image ? attributionFor(frame.image) : null,
      analysis: af.analysis,
    };
  }

  private newFinding(seed: FindingSeed, angle: AngleName, af: AngleFrame, carriedFrom: string | null): Finding {
    const id = `f-${String(++this.seq).padStart(3, '0')}`;
    this.seedKeys.set(id, seed.key);
    const ruleId = ruleIdFor(seed, angle);
    return {
      finding_id: id,
      angle,
      image_ref: af.frame.image ? `${af.frame.image}.jpg` : null,
      bbox: seed.bbox,
      location_text: seed.location_text,
      zone_tier: seed.zone_tier,
      finding_type: seed.finding_type,
      responsible_party: seed.zone_tier === 'outside_boundary' ? 'airport' : 'airline',
      category: seed.category,
      object_class: seed.object_class,
      size: seed.size,
      severity: severityFor(seed),
      rule_id: ruleId,
      confidence: seed.confidence,
      description: seed.description,
      detected_by: seed.detected_by,
      decided_by: { model: 'haiku', escalated: false },
      carried_from_inspection_id: carriedFrom,
      confirmation: null,
      status: 'open',
      rule: ruleRef(ruleId),
      crop_url: imageUrl(`crops/${seed.crop}`),
      reference_crop_url: seed.refCrop ? imageUrl(`crops/${seed.refCrop}`) : null,
    };
  }

  private sortFindings(report: Report): void {
    report.findings.sort((a, b) => ANGLE_ORDER.indexOf(a.angle) - ANGLE_ORDER.indexOf(b.angle));
  }
}
