import type { State } from '../api/types';
import { queueRows, tileModel } from '../lib/gates';
import { AdvisoryTag, ConfirmedTag, SeverityBadge } from './bits';
import { ToneIcon } from './icons';
import { VERDICT_LABEL } from '../lib/labels';
import { turnHref } from '../route';

export function Overview({ state }: { state: State }) {
  return (
    <div className="overview">
      <section aria-label="Gates">
        <h2 className="section-title">Gates</h2>
        <div className="tiles">
          {state.gates.map((g) => (
            <GateTile key={g.gate} model={tileModel(g)} />
          ))}
        </div>
      </section>
      <Queue state={state} />
    </div>
  );
}

function GateTile({ model: m }: { model: ReturnType<typeof tileModel> }) {
  const cls = [
    'tile',
    `tone-${m.tone}`,
    m.humanConfirmed ? 'is-confirmed' : '',
    m.advisory && m.verdict === 'ALL_CLEAR' ? 'unconfirmed-clear' : '',
  ].join(' ');
  const body = (
    <>
      <div className="tile-head">
        <span className="tile-gate">{m.gate}</span>
        {m.flight ? (
          <span className="tile-flight">
            {m.flight}
            <small>{m.aircraftType}</small>
          </span>
        ) : (
          <span className="muted">No Turn</span>
        )}
      </div>
      <div className="status-line">
        <ToneIcon tone={m.tone} />
        <span>{m.statusLabel}</span>
      </div>
      <div className="tile-verdict">
        {m.verdict ? (
          <>
            <span className="muted small">Verdict</span>
            <span className="verdict-word">{VERDICT_LABEL[m.verdict]}</span>
            {m.humanConfirmed ? <ConfirmedTag /> : <AdvisoryTag />}
          </>
        ) : m.advisory ? (
          <>
            <span className="muted small">Verdict pending</span>
            <AdvisoryTag />
          </>
        ) : null}
      </div>
      <div className="tile-sev">
        {m.severity ? (
          <>
            <SeverityBadge severity={m.severity} big />
            <span>highest open severity</span>
          </>
        ) : m.verdict && !m.humanConfirmed ? (
          <span>No open Findings</span>
        ) : null}
      </div>
      <div className="tile-foot">
        {m.pushbackText ? <span className={`push num${m.pushbackOverdue ? ' overdue' : ''}`}>{m.pushbackText}</span> : <span />}
        {m.turnId ? <span className="small">Open Turn ›</span> : null}
      </div>
    </>
  );
  const label = `Gate ${m.gate}: ${m.statusLabel}${m.verdictLabel ? `, Verdict ${m.verdictLabel}` : ''}${m.advisory ? ' (advisory)' : ''}${m.severity ? `, highest open severity ${m.severity}` : ''}`;
  return m.turnId ? (
    <a className={cls} href={turnHref(m.turnId)} aria-label={label} data-gate={m.gate} data-status={m.statusLabel}>
      {body}
    </a>
  ) : (
    <div className={cls} aria-label={label} data-gate={m.gate} data-status={m.statusLabel}>
      {body}
    </div>
  );
}

function Queue({ state }: { state: State }) {
  const rows = queueRows(state.queue);
  return (
    <aside className="queue" aria-label="Needs a human">
      <h2 className="section-title">Needs a human ({rows.length})</h2>
      {rows.length === 0 ? (
        <p className="empty">Nothing is waiting for a person.</p>
      ) : (
        <ol>
          {rows.map((r) => (
            <li key={r.key}>
              <a className={`q-item tone-${r.tone}`} href={turnHref(r.turnId, r.inspectionId)}>
                <span className="q-gate">{r.gate}</span>
                <span className="q-top">
                  <span className="q-reason">
                    <ToneIcon tone={r.tone} />
                    {r.reasonLabel}
                  </span>
                  {r.pushbackText ? <span className="small num nowrap">{r.pushbackText}</span> : null}
                </span>
                <span className="q-text">{r.text}</span>
              </a>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
