import type { PersonRole, ShiftStatus } from '../api/agentTypes';
import type {
  ConfirmedOutcome,
  FalseAlarmReason,
  Finding,
  GateStatus,
  InspectionKind,
  Role,
  RuleSet,
  Severity,
  UnusableReason,
  Verdict,
  ZoneTier,
} from '../api/types';

export const ROLE_LABEL: Record<Role, string> = { ramp_agent: 'Ramp Agent', ramp_lead: 'Ramp Lead' };

/** Roster roles of the always-on agent. A supervisor routes work and records no Confirmations. */
export const PERSON_ROLE_LABEL: Record<PersonRole, string> = { ramp_agent: 'Ramp Agent', ramp_lead: 'Ramp Lead', supervisor: 'Supervisor' };
export const SHIFT_LABEL: Record<ShiftStatus, string> = { on: 'On shift', break: 'On a break', off: 'Off shift' };

export const GATE_STATUS_LABEL: Record<GateStatus, string> = {
  idle: 'Idle',
  awaiting_pre_arrival: 'Awaiting pre-arrival',
  inspecting: 'Inspecting',
  awaiting_confirmation: 'Awaiting Confirmation',
  confirmed_clear: 'Confirmed clear',
  on_stand: 'Aircraft on stand',
  departed: 'Departed',
};

export const VERDICT_LABEL: Record<Verdict, string> = {
  ALL_CLEAR: 'ALL CLEAR',
  FINDINGS: 'FINDINGS',
  INCOMPLETE: 'INCOMPLETE',
};

export const KIND_LABEL: Record<InspectionKind, string> = {
  pre_arrival: 'Pre-arrival Inspection',
  pre_departure: 'Pre-departure Inspection',
  on_demand: 'On-demand Inspection',
};

export const SEVERITY_MEANING: Record<Severity, string> = {
  HOLD: 'Immediate hazard. No pushback, engine start or aircraft movement until removed.',
  REMOVE: 'Must be removed before departure.',
  ADVISORY: 'Logged and picked up in normal cleaning.',
};

export const ZONE_TIER_LABEL: Record<ZoneTier, string> = {
  critical: 'Critical zone',
  service: 'Service zone',
  general: 'General zone',
  outside_boundary: 'Outside the gate safety envelope',
};

export const UNUSABLE_REASON_LABEL: Record<UnusableReason, string> = {
  missing: 'Image missing',
  glare: 'Glare',
  blur: 'Blur',
  blocked: 'View blocked',
  low_light: 'Low light',
};

export const FALSE_ALARM_REASONS: { value: FalseAlarmReason; label: string }[] = [
  { value: 'shadow', label: 'Shadow or stain' },
  { value: 'marking', label: 'Painted marking' },
  { value: 'equipment_in_place', label: 'Equipment in its place' },
  { value: 'other', label: 'Other' },
];

export const OUTCOME_LABEL: Record<ConfirmedOutcome, string> = {
  removed: 'Removed',
  false_alarm: 'False alarm',
  not_found_on_walk: 'Not found on walk',
};

export const DETECTED_BY_LABEL: Record<string, string> = {
  local_proposer: 'local model (Candidate)',
  safety_net: 'tiled safety net',
  claude: 'Claude (no reference frame)',
};

export const ANALYSIS_LABEL: Record<string, string> = {
  change_detection: 'Change detection vs reference',
  'change_detection+dino': 'Change detection + DINOv2',
  claude_tiled: 'Tiled Claude pass (no reference frame)',
};

export const AIRPORT_ROUTE = 'Ramp 1 control / Airport Operations';

export function unusableReasonLabel(reason: UnusableReason | string | null): string {
  if (!reason) return 'Unusable';
  return (UNUSABLE_REASON_LABEL as Record<string, string>)[reason] ?? humanise(reason);
}

export function falseAlarmReasonLabel(reason: string | null): string {
  return FALSE_ALARM_REASONS.find((r) => r.value === reason)?.label ?? (reason ? humanise(reason) : '');
}

/** "fasteners_hardware" → the rule set's label, or a readable fallback. */
export function categoryLabel(finding: Pick<Finding, 'category' | 'finding_type'>, rules: RuleSet | null): string {
  if (finding.finding_type === 'equipment_staging') return 'Equipment staging (GSE)';
  if (!finding.category) return 'Uncategorised';
  return rules?.categories[finding.category]?.label ?? humanise(finding.category);
}

/** Outside-boundary Findings are reported, not removed, so "removed" reads "Reported". */
export function outcomeLabel(finding: Pick<Finding, 'zone_tier'>, outcome: ConfirmedOutcome): string {
  if (finding.zone_tier === 'outside_boundary' && outcome === 'removed') {
    return `Reported to ${AIRPORT_ROUTE}`;
  }
  return OUTCOME_LABEL[outcome] ?? humanise(outcome);
}

export function humanise(s: string): string {
  const t = s.replace(/[_-]+/g, ' ').trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
}
