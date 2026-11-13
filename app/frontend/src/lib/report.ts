import type {
  AngleName,
  Finding,
  InspectionKind,
  Person,
  Report,
  ReportAngle,
  RunMetadata,
  Severity,
  Turn,
} from '../api/types';
import { iou } from './boxes';
import { ROLE_LABEL, falseAlarmReasonLabel, outcomeLabel, unusableReasonLabel } from './labels';

const SEVERITY_RANK: Record<Severity, number> = { HOLD: 3, REMOVE: 2, ADVISORY: 1 };

export function severityRank(s: Severity | null): number {
  return s ? SEVERITY_RANK[s] : 0;
}

export function isOutsideBoundary(f: Pick<Finding, 'zone_tier' | 'responsible_party'>): boolean {
  return f.zone_tier === 'outside_boundary' || f.responsible_party === 'airport';
}

/**
 * A Finding still needs a person. Per the contract, an airport-routed
 * (outside-boundary) Finding counts as closed once it is acknowledged/reported.
 */
export function isFindingOpen(f: Finding): boolean {
  if (f.status === 'confirmed') return false;
  if (f.status === 'acknowledged' && isOutsideBoundary(f)) return false;
  return true;
}

export function openFindings(report: Report): Finding[] {
  return report.findings.filter(isFindingOpen);
}

export function highestOpenSeverity(report: Report): Severity | null {
  let best: Severity | null = null;
  for (const f of openFindings(report)) {
    if (severityRank(f.severity) > severityRank(best)) best = f.severity;
  }
  return best;
}

/** Open REMOVE/ADVISORY Findings: what "Confirm all removed" will mark. */
export function confirmAllTargets(report: Report): Finding[] {
  return report.findings.filter((f) => f.status === 'open' && f.severity !== 'HOLD');
}

/** An unusable Angle nobody has cleared by eye. Blocks sign-off (FOD-R6). */
export function isAngleUnresolved(a: ReportAngle): boolean {
  return a.status === 'unusable' && !a.checked_by_eye;
}

export type SignoffBlockers = { openFindings: Finding[]; unusableAngles: ReportAngle[] };

export function signoffBlockers(report: Report): SignoffBlockers {
  return { openFindings: openFindings(report), unusableAngles: report.angles.filter(isAngleUnresolved) };
}

export function canSignOff(report: Report): boolean {
  const b = signoffBlockers(report);
  return report.status === 'awaiting_confirmation' && b.openFindings.length === 0 && b.unusableAngles.length === 0;
}

/** Inspections that a later on-demand Inspection replaced. */
export function supersededIds(inspections: readonly Report[]): Set<string> {
  const ids = new Set<string>();
  for (const r of inspections) {
    if (r.parent_inspection_id) ids.add(r.parent_inspection_id);
  }
  return ids;
}

/** Kind of the scheduled Inspection an on-demand Inspection descends from. */
export function rootKind(report: Report, byId: ReadonlyMap<string, Report>): InspectionKind {
  let cur = report;
  const seen = new Set<string>();
  while (cur.parent_inspection_id && !seen.has(cur.inspection_id)) {
    seen.add(cur.inspection_id);
    const parent = byId.get(cur.parent_inspection_id);
    if (!parent) break;
    cur = parent;
  }
  return cur.kind;
}

export type TimelineEntry =
  | { type: 'milestone'; key: string; label: string; done: boolean }
  | { type: 'inspection'; key: string; report: Report; superseded: boolean }
  | { type: 'scheduled'; key: string; kind: InspectionKind };

const MILESTONE_LABEL: Record<string, string> = {
  stand_prep: 'Stand preparation',
  block_in: 'Block-in',
  scheduled_pushback: 'Scheduled pushback',
};

/**
 * The Turn in time order: stand preparation, the pre-arrival Inspection and its
 * on-demand re-inspections, block-in, the pre-departure Inspection and its
 * re-inspections, scheduled pushback. Scheduled Inspections that have not run
 * yet appear as placeholders.
 */
export function buildTimeline(turn: Turn, demoT: number | null): TimelineEntry[] {
  const byId = new Map(turn.inspections.map((r) => [r.inspection_id, r]));
  const superseded = supersededIds(turn.inspections);
  const before: Report[] = [];
  const after: Report[] = [];
  for (const r of turn.inspections) {
    (rootKind(r, byId) === 'pre_arrival' ? before : after).push(r);
  }
  const hasKind = (kind: InspectionKind) => turn.inspections.some((r) => r.kind === kind);
  const event = (type: string) => turn.events.find((e) => e.type === type);
  const scheduled = (kind: InspectionKind) =>
    turn.events.some((e) => e.type === 'inspection' && e.kind === kind) && !hasKind(kind);
  const done = (type: string, fallback: boolean) => {
    const e = event(type);
    if (e && demoT !== null) return e.t <= demoT;
    return fallback;
  };
  const inspection = (r: Report): TimelineEntry => ({
    type: 'inspection',
    key: r.inspection_id,
    report: r,
    superseded: superseded.has(r.inspection_id),
  });
  const milestone = (type: string, isDone: boolean): TimelineEntry => ({
    type: 'milestone',
    key: type,
    label: MILESTONE_LABEL[type] ?? type,
    done: isDone,
  });

  const out: TimelineEntry[] = [];
  if (event('stand_prep')) out.push(milestone('stand_prep', done('stand_prep', true)));
  out.push(...before.map(inspection));
  if (scheduled('pre_arrival')) out.push({ type: 'scheduled', key: 'sched-pre_arrival', kind: 'pre_arrival' });
  if (event('block_in')) out.push(milestone('block_in', done('block_in', after.length > 0)));
  out.push(...after.map(inspection));
  if (scheduled('pre_departure')) out.push({ type: 'scheduled', key: 'sched-pre_departure', kind: 'pre_departure' });
  if (event('scheduled_pushback')) out.push(milestone('scheduled_pushback', done('scheduled_pushback', false)));
  return out;
}

export function personLabel(p: Person): string {
  return `${p.name || 'Unnamed'} (${ROLE_LABEL[p.role] ?? p.role})`;
}

export type InspectionRecord = { key: string; at: string; who: string; text: string };

function notBefore(at: string, start: string): boolean {
  const a = Date.parse(at);
  const s = Date.parse(start);
  if (Number.isNaN(a) || Number.isNaN(s)) return true;
  return a >= s;
}

/**
 * What people recorded on this Inspection, oldest first: each Finding
 * Confirmation, each checked-by-eye and the sign-off. Records inherited from an
 * earlier Inspection are left to that Inspection's entry.
 */
export function inspectionRecords(report: Report): InspectionRecord[] {
  const out: InspectionRecord[] = [];
  report.findings.forEach((f, i) => {
    const c = f.confirmation;
    if (!c || !notBefore(c.confirmed_at, report.captured_at)) return;
    const reason = c.outcome === 'false_alarm' && c.false_alarm_reason ? ` (${falseAlarmReasonLabel(c.false_alarm_reason)})` : '';
    out.push({
      key: `f-${f.finding_id}`,
      at: c.confirmed_at,
      who: personLabel(c.confirmed_by),
      text: `Finding ${i + 1} (${f.severity}, ${f.angle}): ${outcomeLabel(f, c.outcome)}${reason}`,
    });
  });
  for (const a of report.angles) {
    if (a.checked_by_eye && notBefore(a.checked_by_eye.at, report.captured_at)) {
      out.push({
        key: `eye-${a.angle}`,
        at: a.checked_by_eye.at,
        who: personLabel(a.checked_by_eye.by),
        text: `${a.angle} checked by eye (${unusableReasonLabel(a.unusable_reason).toLowerCase()})`,
      });
    }
  }
  if (report.inspection_signoff) {
    out.push({
      key: 'signoff',
      at: report.inspection_signoff.at,
      who: personLabel(report.inspection_signoff.by),
      text: 'Inspection signed off',
    });
  }
  return out.sort((a, b) => (Date.parse(a.at) || 0) - (Date.parse(b.at) || 0));
}

export type HoldRemovalOutcome = 'cleared' | 'still_there';

/**
 * Result of "Removed" on a HOLD. The backend re-inspects the Angle and records
 * the Confirmation only if the new frame has no matching Finding; otherwise the
 * returned Report still carries an open Finding at that spot.
 */
export function holdRemovalOutcome(previous: Finding, result: Report): HoldRemovalOutcome {
  const same = result.findings.find((f) => f.finding_id === previous.finding_id);
  if (same) return same.status === 'confirmed' ? 'cleared' : 'still_there';
  const match = result.findings.some(
    (f) => f.angle === previous.angle && f.status !== 'confirmed' && iou(f.bbox, previous.bbox) > 0.1,
  );
  return match ? 'still_there' : 'cleared';
}

export type ReinspectOutcome = { angle: AngleName; usable: boolean; reason: string | null; openCount: number };

export function reinspectOutcome(angle: AngleName, result: Report): ReinspectOutcome {
  const a = result.angles.find((x) => x.angle === angle);
  return {
    angle,
    usable: a ? a.status === 'usable' : false,
    reason: a?.unusable_reason ?? null,
    openCount: result.findings.filter((f) => f.angle === angle && isFindingOpen(f)).length,
  };
}

export type CostSummary = { calls: number; tokensIn: number; tokensOut: number; costUsd: number };

export function costSummary(meta: RunMetadata): CostSummary {
  return meta.llm_calls.reduce<CostSummary>(
    (acc, c) => ({
      calls: acc.calls + 1,
      tokensIn: acc.tokensIn + (c.tokens_in || 0),
      tokensOut: acc.tokensOut + (c.tokens_out || 0),
      costUsd: acc.costUsd + (c.est_cost_usd || 0),
    }),
    { calls: 0, tokensIn: 0, tokensOut: 0, costUsd: 0 },
  );
}

/**
 * Records per Inspection for a whole Turn. A Confirmation carried into a later
 * on-demand Inspection is listed once, on the first Inspection that holds it.
 */
export function turnRecords(inspections: readonly Report[]): Map<string, InspectionRecord[]> {
  const seen = new Set<string>();
  const out = new Map<string, InspectionRecord[]>();
  for (const r of inspections) {
    const fresh = inspectionRecords(r).filter((rec) => {
      const id = rec.key === 'signoff' ? `${r.inspection_id}|signoff` : `${rec.key}|${rec.at}`;
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });
    out.set(r.inspection_id, fresh);
  }
  return out;
}
