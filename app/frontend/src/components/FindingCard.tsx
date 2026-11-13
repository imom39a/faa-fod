import { useState } from 'react';
import type { Attribution, ConfirmBody, Finding, Person, Proposal, RuleSet } from '../api/types';
import { severityTone } from '../lib/gates';
import {
  AIRPORT_ROUTE,
  DETECTED_BY_LABEL,
  FALSE_ALARM_REASONS,
  ZONE_TIER_LABEL,
  categoryLabel,
  falseAlarmReasonLabel,
  humanise,
  outcomeLabel,
} from '../lib/labels';
import { formatTime } from '../lib/format';
import { isFindingOpen, isOutsideBoundary, personLabel } from '../lib/report';
import { SeverityBadge } from './bits';
import { CheckCircleIcon } from './icons';

export type ConfirmRequest = Omit<ConfirmBody, 'role' | 'name'>;

type Props = {
  finding: Finding;
  number: number;
  rules: RuleSet | null;
  person: Person;
  /** False for a superseded, running or signed-off Inspection: the card is a record only. */
  actionable: boolean;
  busy: boolean;
  selected: boolean;
  hot: boolean;
  attribution: Attribution | null;
  onSelect: () => void;
  onHover: (hot: boolean) => void;
  onConfirm: (request: ConfirmRequest) => void;
  /** Proposals made about this Finding (any status). Optional: older Reports have none. */
  proposals?: Proposal[];
  /** "I can't find it": records nothing, creates a Proposal (issue #4). */
  onNotFound?: () => void;
  onAnswer?: (proposal: Proposal, accept: boolean) => void;
};

/** Whether a Proposal is addressed to this person. `to.name` null means any person with that role. */
export function isAddressedTo(p: Proposal, person: Person): boolean {
  return p.to.role === person.role && (p.to.name === null || p.to.name === person.name);
}

export function FindingCard(props: Props) {
  const { finding: f, number, rules, person, actionable, busy, selected, hot, attribution, onSelect, onHover, onConfirm } = props;
  const { proposals = [], onNotFound, onAnswer } = props;
  const pendingProposals = proposals.filter((p) => p.status === 'pending');
  const [pickingReason, setPickingReason] = useState(false);
  const [source, setSource] = useState('');
  const open = isFindingOpen(f);
  const outside = isOutsideBoundary(f);
  const isHold = f.severity === 'HOLD';
  const cls = ['fcard', `tone-${severityTone(f.severity)}`, open ? '' : 'closed', selected ? 'selected' : '', hot ? 'hot' : ''].join(' ');

  return (
    <li
      className={cls}
      data-finding={f.finding_id}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
    >
      <div
        className="fcard-head"
        role="button"
        tabIndex={0}
        aria-pressed={selected}
        aria-label={`Finding ${number}, ${f.severity}, ${f.angle}: show on image`}
        onClick={onSelect}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSelect();
          }
        }}
      >
        <span className="fnum">{number}</span>
        <SeverityBadge severity={f.severity} />
        <span className="tag">{open ? (f.status === 'acknowledged' ? 'Acknowledged' : 'Open') : 'Confirmed'}</span>
        <span className="where">{f.angle}</span>
      </div>

      <p className="fdesc">{f.description}</p>
      <div className="fmeta">
        <span>
          <b>Where:</b> {f.location_text} ({ZONE_TIER_LABEL[f.zone_tier] ?? f.zone_tier})
        </span>
        <span>
          <b>Rule:</b> <span className="mono">{f.rule?.id ?? f.rule_id}</span> · <b>Confidence:</b> {f.confidence}
          {outside ? (
            <>
              {' '}
              · <b>Report to {AIRPORT_ROUTE}</b>
            </>
          ) : null}
        </span>
      </div>
      {!selected && (
        <button type="button" className="compact quiet" style={{ marginTop: 8 }} onClick={onSelect}>
          Show crops, rule and details
        </button>
      )}

      {selected && (
        <>
          <div className="fmeta">
            <span>
              <b>Category:</b> {categoryLabel(f, rules)} · <b>Object class:</b> {f.object_class}
              {f.confidence !== 'high' ? ` · ${humanise(f.confidence)} confidence never lowers severity` : ''}
            </span>
            <span>
              <b>Detected by:</b> {DETECTED_BY_LABEL[f.detected_by] ?? humanise(f.detected_by)} · <b>Decided by:</b>{' '}
              {f.decided_by.model}
              {f.decided_by.escalated ? ' (escalated)' : ''} · <b>Size:</b> {f.size}
            </span>
            <span>
              <b>Responsible party:</b> {f.responsible_party === 'airport' ? `airport: report to ${AIRPORT_ROUTE}` : 'airline: ramp crew removes'}
            </span>
          </div>

          <div className="frule">
            <b className="mono">{f.rule?.id ?? f.rule_id}</b> {f.rule?.text}
            {f.rule?.basis ? <div className="basis">Basis: {f.rule.basis}</div> : null}
          </div>

          <div className="crops">
            <figure>
              {f.crop_url ? <img src={f.crop_url} alt={`Current crop of Finding ${number}`} loading="lazy" /> : <div className="nocrop">No crop</div>}
              <figcaption>Current</figcaption>
            </figure>
            <figure>
              {f.reference_crop_url ? (
                <img src={f.reference_crop_url} alt={`Reference crop for Finding ${number}`} loading="lazy" />
              ) : (
                <div className="nocrop">No reference frame for this Angle</div>
              )}
              <figcaption>Reference</figcaption>
            </figure>
          </div>
          <p className="credit">
            Crops of the {f.angle} frame.{' '}
            {attribution ? `Photo: ${attribution.author}, ${attribution.licence}${attribution.derived ? ` (${attribution.derived})` : ''}` : ''}
          </p>
        </>
      )}

      {f.confirmation ? (
        <div className="record">
          <CheckCircleIcon />
          <span>
            <b>{outcomeLabel(f, f.confirmation.outcome)}</b>
            {f.confirmation.outcome === 'false_alarm' && f.confirmation.false_alarm_reason
              ? ` (${falseAlarmReasonLabel(f.confirmation.false_alarm_reason)})`
              : ''}{' '}
            by {personLabel(f.confirmation.confirmed_by)} at {formatTime(f.confirmation.confirmed_at)}
            {f.confirmation.after_photo_ref ? '. Re-inspection found the spot clear.' : ''}
            {f.confirmation.possible_source ? ` Note: ${f.confirmation.possible_source}` : ''}
          </span>
        </div>
      ) : !open ? (
        <div className="record">
          <CheckCircleIcon />
          <span>
            <b>Acknowledged:</b> reported to {AIRPORT_ROUTE}.
          </span>
        </div>
      ) : null}

      {(f.still_there_count ?? 0) > 0 && open && (
        <p className="lead-note" role="status">
          Still there: recorded as removed {f.still_there_count} time{f.still_there_count === 1 ? '' : 's'}, but the re-inspection still
          shows it. The HOLD stays open.
        </p>
      )}

      {open && actionable && pendingProposals.map((p) =>
        isAddressedTo(p, person) ? (
          <div className="route-note" key={p.proposal_id} role="group" aria-label="Proposal">
            <p>{p.text}</p>
            <div className="factions">
              <button type="button" className="primary" disabled={busy} onClick={() => onAnswer?.(p, true)}>
                {p.kind === 'reinspect_angle' ? `Yes, re-inspect ${p.angle}` : 'Yes, record not found'}
              </button>
              <button type="button" disabled={busy} onClick={() => onAnswer?.(p, false)}>
                {p.kind === 'reinspect_angle' ? 'Not now' : 'No, keep it open'}
              </button>
            </div>
          </div>
        ) : (
          <p className="lead-note" key={p.proposal_id} role="status">
            {p.kind === 'reinspect_angle'
              ? `Reported to the Ramp Lead: ${p.reported_by.name} could not find it. Nothing is recorded; the HOLD stays open.`
              : `Waiting for ${p.to.name ?? 'the addressed person'} to answer.`}
          </p>
        ),
      )}

      {open && actionable && outside && (
        <>
          <div className="route-note">
            <b>Do not remove.</b> This is outside the gate safety envelope, so it is not the ramp crew's to remove. Report to{' '}
            {AIRPORT_ROUTE}.
            <input
              type="text"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="Optional: who was told, possible source"
              aria-label="Who was told, or possible source"
            />
          </div>
          <div className="factions">
            <button
              type="button"
              className="primary"
              disabled={busy}
              onClick={() => onConfirm({ outcome: 'removed', possible_source: source.trim() || undefined })}
            >
              Reported to {AIRPORT_ROUTE}
            </button>
            <button type="button" disabled={busy} onClick={() => setPickingReason(true)}>
              False alarm
            </button>
          </div>
        </>
      )}

      {open && actionable && !outside && isHold && (
        <>
          <div className="steps" aria-label="HOLD Confirmation steps">
            <span className={`step ${f.status === 'acknowledged' ? 'done' : 'now'}`}>1 Acknowledge</span>
            <span aria-hidden="true">→</span>
            <span className={`step ${f.status === 'acknowledged' ? 'now' : ''}`}>2 Removed + re-inspection of {f.angle}</span>
          </div>
          {person.role !== 'ramp_lead' && <p className="lead-note">Only a Ramp Lead can confirm a HOLD. You are signed in as Ramp Agent.</p>}
          <div className="factions">
            {f.status === 'open' ? (
              <button type="button" className="primary" disabled={busy} onClick={() => onConfirm({ outcome: 'acknowledged' })}>
                Acknowledge: going to it
              </button>
            ) : null}
            <button
              type="button"
              className={f.status === 'acknowledged' ? 'good' : ''}
              disabled={busy || f.status !== 'acknowledged'}
              title={f.status !== 'acknowledged' ? 'Acknowledge the HOLD first' : `Re-inspects ${f.angle}; the HOLD clears only if the new image is clean`}
              onClick={() => onConfirm({ outcome: 'removed' })}
            >
              Removed: re-inspect {f.angle}
            </button>
            <button type="button" disabled={busy} onClick={() => setPickingReason(true)}>
              False alarm
            </button>
            {onNotFound && !pendingProposals.some((p) => p.kind === 'reinspect_angle') && (
              <button type="button" disabled={busy} title="Records nothing: the Ramp Lead is told and decides" onClick={onNotFound}>
                Can't find it
              </button>
            )}
          </div>
        </>
      )}

      {open && actionable && !outside && !isHold && (
        <div className="factions">
          <button type="button" className="good" disabled={busy} onClick={() => onConfirm({ outcome: 'removed' })}>
            Removed
          </button>
          <button type="button" disabled={busy} onClick={() => setPickingReason(true)}>
            False alarm
          </button>
          {onNotFound && !pendingProposals.some((p) => p.kind === 'record_not_found_on_walk') && (
            <button type="button" disabled={busy} title="Records nothing until you accept the proposal" onClick={onNotFound}>
              Can't find it
            </button>
          )}
        </div>
      )}

      {open && actionable && pickingReason && (
        <div className="reason-picker" role="group" aria-label="False alarm reason">
          <b>Why is it a false alarm?</b>
          <div className="factions">
            {FALSE_ALARM_REASONS.map((r) => (
              <button
                key={r.value}
                type="button"
                disabled={busy}
                onClick={() => {
                  setPickingReason(false);
                  onConfirm({ outcome: 'false_alarm', false_alarm_reason: r.value });
                }}
              >
                {r.label}
              </button>
            ))}
            <button type="button" className="quiet" onClick={() => setPickingReason(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
