import type { GateState, QueueItem, QueueReason, Severity, Verdict } from '../api/types';
import { GATE_STATUS_LABEL, VERDICT_LABEL } from './labels';

/** Visual tone of a tile or queue row. Always paired with a text label and icon. */
export type Tone = 'idle' | 'waiting' | 'busy' | 'onstand' | 'hold' | 'remove' | 'advisory' | 'incomplete' | 'clear' | 'await' | 'confirmed';

export type TileModel = {
  gate: string;
  statusLabel: string;
  /** Verdict of the latest Inspection, shown beneath the status. */
  verdict: Verdict | null;
  verdictLabel: string | null;
  /** True when what is shown comes from the system alone (no human Confirmation yet). */
  advisory: boolean;
  /** True only when a person has signed the Inspection off. */
  humanConfirmed: boolean;
  severity: Severity | null;
  tone: Tone;
  flight: string | null;
  aircraftType: string | null;
  pushbackText: string | null;
  pushbackOverdue: boolean;
  turnId: string | null;
  inspectionId: string | null;
};

const SEVERITY_TONE: Record<Severity, Tone> = { HOLD: 'hold', REMOVE: 'remove', ADVISORY: 'advisory' };

export function severityTone(severity: Severity): Tone {
  return SEVERITY_TONE[severity];
}

/** "34 min to pushback", "Pushback due", "5 min past scheduled pushback". */
export function formatPushback(minutes: number | null | undefined): string | null {
  if (minutes === null || minutes === undefined || !Number.isFinite(minutes)) return null;
  const m = Math.round(minutes);
  if (m > 0) return `${m} min to pushback`;
  if (m === 0) return 'Pushback due';
  return `${-m} min past scheduled pushback`;
}

/** Everything a Gate tile shows, derived from one GateState. */
export function tileModel(g: GateState): TileModel {
  const showsVerdict = g.verdict !== null && (g.status === 'awaiting_confirmation' || g.status === 'confirmed_clear');
  const humanConfirmed = g.status === 'confirmed_clear';
  // A Verdict, or an analysis in progress, is the system's alone until a person confirms it.
  const advisory = !humanConfirmed && (g.status === 'awaiting_confirmation' || g.status === 'inspecting');
  const minutes = g.turn?.minutes_to_pushback ?? null;
  const pushbackRelevant = g.status !== 'departed' && g.status !== 'idle';

  return {
    gate: g.gate,
    statusLabel: GATE_STATUS_LABEL[g.status] ?? g.status,
    verdict: showsVerdict ? g.verdict : null,
    verdictLabel: showsVerdict && g.verdict ? VERDICT_LABEL[g.verdict] : null,
    advisory,
    humanConfirmed,
    severity: g.highest_open_severity,
    tone: tileTone(g),
    flight: g.turn?.flight ?? null,
    aircraftType: g.turn?.aircraft_type ?? null,
    pushbackText: pushbackRelevant ? formatPushback(minutes) : null,
    pushbackOverdue: pushbackRelevant && minutes !== null && minutes <= 0,
    turnId: g.turn?.turn_id ?? null,
    inspectionId: g.turn?.latest_inspection_id ?? null,
  };
}

/** A HOLD (or any open severity) outranks the Verdict: it shows even when INCOMPLETE. */
export function tileTone(g: GateState): Tone {
  if (g.highest_open_severity) return SEVERITY_TONE[g.highest_open_severity];
  switch (g.status) {
    case 'inspecting':
      return 'busy';
    case 'awaiting_pre_arrival':
      return 'waiting';
    case 'on_stand':
      return 'onstand';
    case 'confirmed_clear':
      return 'confirmed';
    case 'awaiting_confirmation':
      if (g.verdict === 'INCOMPLETE') return 'incomplete';
      if (g.verdict === 'ALL_CLEAR') return 'clear';
      return 'await';
    default:
      return 'idle';
  }
}

export type QueueRowModel = {
  key: string;
  gate: string;
  reasonLabel: string;
  tone: Tone;
  severity: Severity | null;
  text: string;
  pushbackText: string | null;
  turnId: string;
  inspectionId: string;
};

const QUEUE_REASON_LABEL: Record<QueueReason, string> = {
  hold: 'HOLD',
  findings: 'Findings to confirm',
  incomplete: 'INCOMPLETE',
  signoff: 'Ready for sign-off',
};

const QUEUE_REASON_TONE: Record<QueueReason, Tone> = {
  hold: 'hold',
  findings: 'remove',
  incomplete: 'incomplete',
  signoff: 'await',
};

/** Queue rows, in exactly the order the API gives (HOLDs first, then time to pushback). */
export function queueRows(queue: readonly QueueItem[]): QueueRowModel[] {
  return queue.map((q) => ({
    key: `${q.inspection_id}:${q.reason}`,
    gate: q.gate,
    reasonLabel: QUEUE_REASON_LABEL[q.reason] ?? q.reason,
    tone:
      q.reason === 'findings' && q.severity ? SEVERITY_TONE[q.severity] : (QUEUE_REASON_TONE[q.reason] ?? 'await'),
    severity: q.severity,
    text: q.text,
    pushbackText: formatPushback(q.minutes_to_pushback),
    turnId: q.turn_id,
    inspectionId: q.inspection_id,
  }));
}
