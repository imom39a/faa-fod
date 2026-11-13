import type { Attribution, Severity, Verdict } from '../api/types';
import type { Tone } from '../lib/gates';
import { SEVERITY_MEANING, VERDICT_LABEL } from '../lib/labels';
import { CheckCircleIcon, SeverityIcon, ToneIcon } from './icons';

export function SeverityBadge({ severity, big }: { severity: Severity; big?: boolean }) {
  return (
    <span className={`sev sev-${severity}${big ? ' big' : ''}`} title={SEVERITY_MEANING[severity]}>
      <SeverityIcon severity={severity} />
      {severity}
    </span>
  );
}

/** Marks anything that comes from the system alone, not yet confirmed by a person. */
export function AdvisoryTag() {
  return (
    <span className="advisory-tag" title="From the system alone. Not yet confirmed by a person.">
      advisory
    </span>
  );
}

export function ConfirmedTag() {
  return (
    <span className="confirmed-tag" title="Signed off by a person.">
      <CheckCircleIcon />
      confirmed by a person
    </span>
  );
}

export function verdictTone(verdict: Verdict | null, severity: Severity | null = null): Tone {
  if (severity === 'HOLD') return 'hold';
  if (severity === 'REMOVE') return 'remove';
  if (severity === 'ADVISORY') return 'advisory';
  if (verdict === 'INCOMPLETE') return 'incomplete';
  if (verdict === 'ALL_CLEAR') return 'clear';
  if (verdict === 'FINDINGS') return 'await';
  return 'busy';
}

/** The Verdict word with its icon; advisory unless a person signed the Inspection off. */
export function VerdictMark({ verdict, confirmed }: { verdict: Verdict; confirmed: boolean }) {
  const tone: Tone = verdict === 'INCOMPLETE' ? 'incomplete' : verdict === 'ALL_CLEAR' ? 'clear' : 'remove';
  return (
    <>
      <span className={`verdict-word tone-${tone}`} style={{ color: 'var(--tone)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <ToneIcon tone={tone} className="vicon" />
        {VERDICT_LABEL[verdict]}
      </span>
      {confirmed ? <ConfirmedTag /> : <AdvisoryTag />}
    </>
  );
}

/** Photo credit. Shown for every photograph. */
export function Credit({ attribution, compact }: { attribution: Attribution | null; compact?: boolean }) {
  if (!attribution) return <span className={compact ? 'thumb-credit' : 'credit'}>No attribution recorded</span>;
  const { title, url, author, licence, derived } = attribution;
  if (compact) {
    return (
      <span className="thumb-credit" title={`${title}, ${author}, ${licence} (${derived})`}>
        Photo: {author} · {licence}
      </span>
    );
  }
  return (
    <p className="credit">
      Photo: {url ? <a href={url} target="_blank" rel="noreferrer">{title}</a> : title} by {author}, {licence}
      {derived ? ` (${derived})` : ''}
    </p>
  );
}
