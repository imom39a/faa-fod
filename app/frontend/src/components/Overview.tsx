import type { State } from '../api/types';
import { isAbnormal, overviewCounts, queueRows, shortPushback, tileModel } from '../lib/gates';
import { VERDICT_LABEL } from '../lib/labels';
import { turnHref } from '../route';
import { AdvisoryTag, ConfirmedTag, SeverityBadge } from './bits';
import { ToneIcon } from './icons';

/** The Gates page: counters, one table row per Gate, and the "Needs a human" queue in priority order. */
export function Overview({ state }: { state: State }) {
  return (
    <div className="home">
      <div className="kpis" aria-label="Waiting on a person, by reason">
        {overviewCounts(state.gates, state.queue).map((c) => (
          <div key={c.key} className={`kpi tone-${c.tone}${c.n > 0 && !c.calm ? ' is-on' : ''}${c.calm ? ' is-calm' : ''}`}>
            <b className="num">{c.n}</b>
            <span>{c.label}</span>
          </div>
        ))}
      </div>
      <section className="home-gates" aria-label="Gates">
        <h2 className="section-title">Gates</h2>
        <div className="gate-table" role="table">
          <div className="gt-row gt-head" role="row">
            <span role="columnheader">Gate</span>
            <span role="columnheader">Flight</span>
            <span role="columnheader">Status</span>
            <span role="columnheader">Verdict</span>
            <span role="columnheader">Open severity</span>
            <span role="columnheader" className="r">
              Pushback
            </span>
          </div>
          {state.gates.map((g) => (
            <GateRow key={g.gate} model={tileModel(g)} push={shortPushback(g)} />
          ))}
        </div>
      </section>
      <Queue state={state} />
    </div>
  );
}

function GateRow({ model: m, push }: { model: ReturnType<typeof tileModel>; push: ReturnType<typeof shortPushback> }) {
  const cells = (
    <>
      <span role="cell" className="gt-gate">
        {m.gate}
      </span>
      <span role="cell">
        {m.flight ? (
          <>
            <b>{m.flight}</b> <span className="muted">{m.aircraftType}</span>
          </>
        ) : (
          <span className="muted">No Turn</span>
        )}
      </span>
      <span role="cell" className="gt-status">
        <ToneIcon tone={m.tone} /> {m.statusLabel}
      </span>
      <span role="cell" className="gt-verdict">
        {m.verdict ? (
          <>
            <b>{VERDICT_LABEL[m.verdict]}</b>
            {m.humanConfirmed ? <ConfirmedTag /> : <AdvisoryTag />}
          </>
        ) : m.advisory ? (
          <>
            <span className="muted">Pending</span>
            <AdvisoryTag />
          </>
        ) : (
          <span className="muted">–</span>
        )}
      </span>
      <span role="cell">{m.severity ? <SeverityBadge severity={m.severity} /> : <span className="muted">–</span>}</span>
      <span role="cell" className={`r num${push?.overdue ? ' overdue' : ''}`} title={m.pushbackText ?? undefined}>
        {push ? push.text : '–'}
      </span>
    </>
  );
  const cls = `gt-row tone-${m.tone}${isAbnormal(m.tone) ? ' is-abnormal' : ''}`;
  const label = `Gate ${m.gate}: ${m.statusLabel}${m.verdictLabel ? `, Verdict ${m.verdictLabel}` : ''}${m.advisory ? ' (advisory)' : ''}${m.severity ? `, highest open severity ${m.severity}` : ''}`;
  return m.turnId ? (
    <a className={cls} role="row" href={turnHref(m.turnId)} aria-label={label} data-gate={m.gate} data-status={m.statusLabel}>
      {cells}
    </a>
  ) : (
    <div className={cls} role="row" aria-label={label} data-gate={m.gate} data-status={m.statusLabel}>
      {cells}
    </div>
  );
}

function Queue({ state }: { state: State }) {
  const rows = queueRows(state.queue);
  return (
    <aside className="queue" aria-label="Needs a human">
      <h2 className="section-title">Needs a human, in priority order ({rows.length})</h2>
      {rows.length === 0 ? (
        <p className="empty">Nothing is waiting for a person.</p>
      ) : (
        <ol>
          {rows.map((r, i) => (
            <li key={r.key}>
              <a className={`q-item tone-${r.tone}`} href={turnHref(r.turnId, r.inspectionId)}>
                <span className="q-n num">{i + 1}</span>
                <span className="q-gate">{r.gate}</span>
                <span className="q-body">
                  <span className="q-reason">
                    <ToneIcon tone={r.tone} />
                    {r.reasonLabel}
                  </span>
                  <span className="q-text">{r.text}</span>
                </span>
                {r.pushbackText ? <span className="small num nowrap">{r.pushbackText}</span> : null}
              </a>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
