/**
 * Types for the Turn record (GET /api/turns/{turn_id}/record), as defined in
 * app/CONTRACT.md. The record is read-only: it lists every Inspection, Task,
 * Report and Confirmation of one Turn in time order, with who did each and when,
 * and the cost of the Turn. A Report is what a person said; a Confirmation is
 * what was recorded. The two kinds are never merged.
 */

/** Clients must also accept kinds added later; show them by name. */
export type TurnRecordKind = 'inspection' | 'task' | 'report' | 'confirmation';

/** Who did it. Null for something done by code, a timer or the cameras. */
export type TurnRecordPerson = {
  person_id: string | null;
  name: string | null;
  /** `ramp_agent`, `ramp_lead`, `supervisor`, or a role added later. */
  role: string | null;
};

export type TurnRecordRefs = {
  inspection_id: string | null;
  task_id: string | null;
  finding_id: string | null;
  angle: string | null;
};

export type TurnRecordEntry = {
  /** 0..n-1 in the returned order. */
  seq: number;
  /** ISO time. Entries are sorted by `at`; ties keep a stable source order. */
  at: string;
  /** Demo seconds, when known. */
  t: number | null;
  kind: TurnRecordKind | (string & {});
  /**
   * inspection: started / completed / reinspected; task: assigned / accepted / reassigned /
   * escalated / reopened / closed / cancelled; report: done / cant / accept / not_found / ...;
   * confirmation: acknowledged / removed / false_alarm / not_found_on_walk / checked_by_eye /
   * signoff / reported.
   */
  event: string;
  person: TurnRecordPerson | null;
  /** One plain human-readable line. */
  text: string;
  refs: TurnRecordRefs;
  /** Source details: raw_text and via for a Report, via for a Confirmation, verdict and cost for an
   *  Inspection, level for an escalation. */
  data: Record<string, unknown>;
};

export type TurnRecordCost = {
  inspections_usd: number;
  agent_usd: number;
  total_usd: number;
  note: string | null;
};

export type TurnRecord = {
  turn_id: string;
  gate: string;
  flight: string | null;
  /** ISO time the record was built. */
  generated_at: string;
  cost: TurnRecordCost;
  entries: TurnRecordEntry[];
};
