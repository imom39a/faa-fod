/**
 * The Turn record on the client: a tolerant normaliser for
 * GET /api/turns/{turn_id}/record, time ordering, labels and the JSON download.
 * Nothing here writes: the record is read-only.
 */
import type {
  TurnRecord,
  TurnRecordCost,
  TurnRecordEntry,
  TurnRecordPerson,
  TurnRecordRefs,
} from '../api/turnRecordTypes';
import { humanise } from './labels';

type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

function timeOf(at: string): number {
  const ms = Date.parse(at);
  return Number.isNaN(ms) ? Number.POSITIVE_INFINITY : ms;
}

/**
 * Time order by `at`. Entries at the same time keep the order they arrived in,
 * which is the server's stable source order. Returns a new array.
 */
export function orderEntries<T extends Pick<TurnRecordEntry, 'at'>>(entries: readonly T[]): T[] {
  return entries
    .map((entry, i) => ({ entry, i, ms: timeOf(entry.at) }))
    .sort((a, b) => (a.ms === b.ms ? a.i - b.i : a.ms < b.ms ? -1 : 1))
    .map((x) => x.entry);
}

function normalisePerson(v: unknown): TurnRecordPerson | null {
  if (!isObj(v)) return null;
  const person = { person_id: str(v.person_id), name: str(v.name), role: str(v.role) };
  return person.person_id === null && person.name === null && person.role === null ? null : person;
}

function normaliseRefs(v: unknown): TurnRecordRefs {
  const r = isObj(v) ? v : {};
  return { inspection_id: str(r.inspection_id), task_id: str(r.task_id), finding_id: str(r.finding_id), angle: str(r.angle) };
}

/** One entry, or null when it is malformed (no kind, or no readable time). */
export function normaliseEntry(v: unknown, index: number): TurnRecordEntry | null {
  if (!isObj(v)) return null;
  const kind = str(v.kind)?.trim();
  const at = str(v.at);
  if (!kind || !at || Number.isNaN(Date.parse(at))) return null;
  return {
    seq: num(v.seq) ?? index,
    at,
    t: num(v.t),
    kind,
    event: str(v.event) ?? '',
    person: normalisePerson(v.person),
    text: str(v.text) ?? '',
    refs: normaliseRefs(v.refs),
    data: isObj(v.data) ? v.data : {},
  };
}

function normaliseCost(v: unknown): TurnRecordCost {
  const c = isObj(v) ? v : {};
  const inspections = num(c.inspections_usd) ?? 0;
  const agent = num(c.agent_usd) ?? 0;
  return { inspections_usd: inspections, agent_usd: agent, total_usd: num(c.total_usd) ?? inspections + agent, note: str(c.note) };
}

/**
 * Accept whatever the server sent and return a usable record. Missing arrays
 * become [], malformed entries are dropped, unknown kinds pass through, and the
 * entries come back in time order with `seq` 0..n-1. Never throws.
 */
export function normaliseTurnRecord(raw: unknown, turnId = ''): TurnRecord {
  const r = isObj(raw) ? raw : {};
  const list = Array.isArray(r.entries) ? r.entries : [];
  const entries = orderEntries(list.map(normaliseEntry).filter((e): e is TurnRecordEntry => e !== null)).map((e, seq) => ({ ...e, seq }));
  return {
    turn_id: str(r.turn_id) ?? turnId,
    gate: str(r.gate) ?? '',
    flight: str(r.flight),
    generated_at: str(r.generated_at) ?? '',
    cost: normaliseCost(r.cost),
    entries,
  };
}

const KIND_LABEL: Record<string, string> = {
  inspection: 'Inspection',
  task: 'Task',
  report: 'Report',
  confirmation: 'Confirmation',
};

/** "Report", "Confirmation", ...; a kind added later shows its own name. */
export function entryKindLabel(kind: string): string {
  return KIND_LABEL[kind] ?? (kind.trim() ? humanise(kind) : 'Entry');
}

const EVENT_LABEL: Record<string, string> = {
  accept: 'Accepted',
  accepted: 'Accepted',
  cant: 'Cannot do it',
  blocked: 'Cannot do it',
  not_found: 'Not found',
  not_found_on_walk: 'Not found on walk',
  signoff: 'Signed off',
  checked_by_eye: 'Checked by eye',
  false_alarm: 'False alarm',
};

export function entryEventLabel(event: string): string {
  return EVENT_LABEL[event] ?? (event.trim() ? humanise(event) : '');
}

/** The JSON file a viewer downloads: the whole record, entries in time order. */
export function buildRecordDownload(record: TurnRecord): { filename: string; text: string } {
  const id = (record.turn_id || 'unknown').replace(/[^A-Za-z0-9._-]+/g, '-');
  const entries = orderEntries(record.entries).map((e, seq) => ({ ...e, seq }));
  return { filename: `turn-${id}-record.json`, text: JSON.stringify({ ...record, entries }, null, 2) };
}
