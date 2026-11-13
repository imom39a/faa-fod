import { useEffect, useRef } from 'react';
import type { Person, Report } from '../api/types';
import { plural } from '../lib/format';
import { KIND_LABEL, VERDICT_LABEL, unusableReasonLabel } from '../lib/labels';
import { personLabel, signoffBlockers } from '../lib/report';
import { AngleFrame, type NumberedFinding } from './AngleFrame';
import { Credit } from './bits';
import { CheckIcon, CrossIcon } from './icons';

type Props = {
  report: Report;
  numbered: NumberedFinding[];
  person: Person;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
};

/** Explicit sign-off. Shows all 6 Angle thumbnails; opening each is not required. */
export function SignoffDialog({ report, numbered, person, busy, error, onConfirm, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const blockers = signoffBlockers(report);
  const blocked = blockers.openFindings.length > 0 || blockers.unusableAngles.length > 0;
  const byEye = report.angles.filter((a) => a.checked_by_eye);

  useEffect(() => {
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="signoff-title" tabIndex={-1} ref={ref}>
        <h2 id="signoff-title">Sign off Inspection: Gate {report.gate}</h2>
        <p className="muted">
          {KIND_LABEL[report.kind]} · Verdict {report.verdict ? VERDICT_LABEL[report.verdict] : 'pending'} (advisory until you sign). Your
          sign-off is the Confirmation that clears the Gate, and it is kept as a record.
        </p>

        <div className="grid6">
          {report.angles.map((a) => (
            <div key={a.angle} className="thumb-btn" style={{ cursor: 'default' }}>
              <AngleFrame angle={a} findings={numbered.filter((n) => n.finding.angle === a.angle)} variant="thumb" />
              <span className="thumb-label">{a.angle}</span>
              <Credit attribution={a.attribution} compact />
            </div>
          ))}
        </div>

        <ul className="checklist">
          <li>
            {blockers.openFindings.length === 0 ? <CheckIcon className="ok" /> : <CrossIcon className="no" />}
            <span>
              {blockers.openFindings.length === 0
                ? report.findings.length === 0
                  ? 'No Findings.'
                  : `All ${plural(report.findings.length, 'Finding')} confirmed.`
                : `${plural(blockers.openFindings.length, 'Finding')} still open (${blockers.openFindings.map((f) => `${f.severity} in ${f.angle}`).join(', ')}). Confirm each one first.`}
            </span>
          </li>
          <li>
            {blockers.unusableAngles.length === 0 ? <CheckIcon className="ok" /> : <CrossIcon className="no" />}
            <span>
              {blockers.unusableAngles.length === 0
                ? byEye.length > 0
                  ? `All Angles covered. Checked by eye: ${byEye.map((a) => `${a.angle} (${a.checked_by_eye?.by.name})`).join(', ')}.`
                  : 'All 6 Angles usable.'
                : `Unusable: ${blockers.unusableAngles.map((a) => `${a.angle} (${unusableReasonLabel(a.unusable_reason).toLowerCase()})`).join(', ')}. Re-inspect, or a Ramp Lead records checked by eye.`}
            </span>
          </li>
        </ul>

        {error ? (
          <div className="banner error" role="alert" style={{ marginTop: 12, marginBottom: 0 }}>
            <span className="grow">{error}</span>
          </div>
        ) : null}

        <div className="dialog-actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="good" disabled={busy || blocked} onClick={onConfirm}>
            {blocked ? 'Sign-off blocked' : `Sign off as ${personLabel(person)}`}
          </button>
        </div>
      </div>
    </div>
  );
}
