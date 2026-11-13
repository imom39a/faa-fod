/**
 * Types for the backend API, as defined in app/CONTRACT.md section 2 and
 * spec/inspection-report-schema.md. Glossary terms are used exactly.
 */

export type Role = 'ramp_agent' | 'ramp_lead';
export type Person = { role: Role; name: string };

export type Severity = 'HOLD' | 'REMOVE' | 'ADVISORY';
export type Verdict = 'ALL_CLEAR' | 'FINDINGS' | 'INCOMPLETE';
export type AngleName = 'NOSE' | 'ENG-L' | 'ENG-R' | 'CARGO' | 'AFT' | 'WIDE';
export const ANGLE_ORDER: readonly AngleName[] = ['NOSE', 'ENG-L', 'ENG-R', 'CARGO', 'AFT', 'WIDE'];

export type InspectionKind = 'pre_arrival' | 'pre_departure' | 'on_demand';
export type InspectionStatus = 'inspecting' | 'awaiting_confirmation' | 'confirmed';
export type UnusableReason = 'missing' | 'glare' | 'blur' | 'blocked' | 'low_light';
export type ZoneTier = 'critical' | 'service' | 'general' | 'outside_boundary';
export type FindingType = 'fod' | 'equipment_staging';
export type ObjectClass = 'hard' | 'light' | 'unidentified' | 'natural';
export type Confidence = 'high' | 'medium' | 'low';
export type FindingStatus = 'open' | 'acknowledged' | 'confirmed';
export type ConfirmedOutcome = 'removed' | 'false_alarm' | 'not_found_on_walk';
/** `outcome` accepted by POST .../findings/{id}/confirm. */
export type ConfirmOutcome = 'acknowledged' | ConfirmedOutcome;
export type FalseAlarmReason = 'shadow' | 'marking' | 'equipment_in_place' | 'other';
/** Pixels in the original image: [x1, y1, x2, y2]. */
export type BBox = [number, number, number, number];

export type Attribution = {
  title: string;
  url: string;
  author: string;
  licence: string;
  derived: string;
};

export type ReportAngle = {
  angle: AngleName;
  image_ref: string | null;
  camera_id: string | null;
  crop: unknown;
  status: 'usable' | 'unusable';
  unusable_reason: UnusableReason | null;
  assessed_by: 'local_check' | 'claude';
  source_inspection_id: string;
  /** Contract additions. `image_url` is null when the Angle is missing. */
  image_url: string | null;
  reference_url: string | null;
  width: number;
  height: number;
  checked_by_eye: { by: Person; at: string } | null;
  attribution: Attribution | null;
  analysis: string | null;
};

export type FindingConfirmation = {
  outcome: ConfirmedOutcome;
  false_alarm_reason: FalseAlarmReason | null;
  confirmed_by: Person;
  confirmed_at: string;
  after_photo_ref: string | null;
  possible_source: string | null;
};

export type RuleRef = { id: string; text: string; basis: string };

export type Finding = {
  finding_id: string;
  angle: AngleName;
  image_ref: string | null;
  bbox: BBox;
  location_text: string;
  zone_tier: ZoneTier;
  finding_type: FindingType;
  responsible_party: 'airline' | 'airport';
  /** Null for equipment-staging Findings. */
  category: string | null;
  object_class: ObjectClass;
  size: 'S' | 'M' | 'L';
  severity: Severity;
  rule_id: string;
  confidence: Confidence;
  description: string;
  detected_by: 'local_proposer' | 'safety_net' | 'claude';
  decided_by: { model: string; escalated: boolean };
  carried_from_inspection_id: string | null;
  confirmation: FindingConfirmation | null;
  /** Contract additions. */
  status: FindingStatus;
  rule: RuleRef;
  crop_url: string | null;
  reference_crop_url: string | null;
};

export type DismissedCandidate = { angle: AngleName; bbox: BBox | []; reason: string };
export type Observation = { angle: AngleName; bbox: BBox | []; kind: string; text: string };

export type LlmCall = {
  model: string;
  purpose: string;
  tokens_in: number;
  tokens_out: number;
  est_cost_usd: number;
};

export type RunMetadata = {
  local_models: { name: string; version: string }[];
  llm_calls: LlmCall[];
  timings_ms: Record<string, number>;
  /** Free-text notes, e.g. "DINOv2 step skipped". Optional in practice. */
  notes?: string[] | string;
};

/** One Inspection report. */
export type Report = {
  schema_version: string;
  rule_set_version: string;
  inspection_id: string;
  gate: string;
  turn_id: string;
  kind: InspectionKind;
  parent_inspection_id: string | null;
  captured_at: string;
  analysed_at: string | null;
  verdict: Verdict | null;
  highest_open_severity: Severity | null;
  missing_angles: AngleName[];
  angles: ReportAngle[];
  findings: Finding[];
  dismissed_candidates: DismissedCandidate[];
  observations: Observation[];
  inspection_signoff: { by: Person; at: string } | null;
  run_metadata: RunMetadata;
  status: InspectionStatus;
};

export type GateStatus =
  | 'idle'
  | 'awaiting_pre_arrival'
  | 'inspecting'
  | 'awaiting_confirmation'
  | 'confirmed_clear'
  | 'on_stand'
  | 'departed';

export type TurnPhase = 'stand_prep' | 'pre_arrival' | 'on_stand' | 'pre_departure' | 'departed';

export type GateTurn = {
  turn_id: string;
  flight: string;
  aircraft_type: string;
  phase: TurnPhase;
  minutes_to_pushback: number | null;
  latest_inspection_id: string | null;
};

export type GateState = {
  gate: string;
  status: GateStatus;
  verdict: Verdict | null;
  highest_open_severity: Severity | null;
  turn: GateTurn | null;
};

export type QueueReason = 'hold' | 'findings' | 'incomplete' | 'signoff';

export type QueueItem = {
  gate: string;
  turn_id: string;
  inspection_id: string;
  reason: QueueReason;
  severity: Severity | null;
  minutes_to_pushback: number | null;
  text: string;
};

export type DemoState = { playing: boolean; speed: number; t: number; duration: number };

export type State = {
  demo: DemoState;
  /** Always 5, in order T1, T2, T4, T5, T8. */
  gates: GateState[];
  /** "Needs a human": shown in the order the API gives. */
  queue: QueueItem[];
};

/** Scripted Turn event from demo/timeline.json (t = demo seconds from start). */
export type TurnEvent = {
  t: number;
  type: 'stand_prep' | 'inspection' | 'block_in' | 'scheduled_pushback' | (string & {});
  kind?: InspectionKind;
  scene_id?: string;
};

/**
 * GET /turns/{turn_id}. The contract fixes `inspections` (oldest first) and
 * `events`; the remaining fields follow demo/timeline.json and may be absent.
 */
export type Turn = {
  turn_id: string;
  gate: string;
  flight?: string;
  aircraft_type?: string;
  inspections: Report[];
  events: TurnEvent[];
};

export type ConfirmBody = Person & {
  outcome: ConfirmOutcome;
  false_alarm_reason?: FalseAlarmReason;
  possible_source?: string;
};

export type InspectBody = { kind: InspectionKind; scene_id?: string };
export type DemoSpeed = 1 | 2 | 5 | 10;
export const DEMO_SPEEDS: readonly DemoSpeed[] = [1, 2, 5, 10];

export type AssistantRequest = { inspection_id: string; message: string };
export type AssistantResponse = {
  reply: string;
  suggested_reinspect_angles: string[];
  draft_report: string | null;
};

/** GET /rules: contents of app/data/rules/fod-rules.json. */
export type RuleSet = {
  version: string;
  severities: Severity[];
  angle_zone_tier: Record<string, ZoneTier>;
  categories: Record<string, { label: string; default_class: ObjectClass; note?: string }>;
  severity_matrix: Record<ObjectClass, Record<ZoneTier, Severity>>;
  rules: { id: string; text: string; basis: string; severity?: string; finding_type?: string }[];
  rule_for: Record<string, string>;
  roles: Record<Role, Severity[]>;
};

/** Error codes the contract names, plus client-side ones. */
export type ApiErrorCode =
  | 'role_not_allowed'
  | 'hold_needs_acknowledge'
  | 'open_findings'
  | 'unusable_angles'
  | 'not_found'
  | 'network'
  | (string & {});
