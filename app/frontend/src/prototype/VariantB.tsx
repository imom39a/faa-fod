// PROTOTYPE (throwaway). Variant B, "Ops console": a Ramp Lead's landscape tablet or a
// control-room screen. Follows high-performance HMI practice: a calm grey display where
// colour appears only when something is abnormal, a Gate strip that stays on every page,
// and a dense table instead of tiles.
import { AdvisoryTag, ConfirmedTag, SeverityBadge } from '../components/bits';
import { ToneIcon, UserIcon } from '../components/icons';
import { queueRows, tileModel } from '../lib/gates';
import { PERSON_ROLE_LABEL, VERDICT_LABEL } from '../lib/labels';
import { CHAT_HREF, OVERVIEW_HREF, turnHref } from '../route';
import type { GateState, State } from '../api/types';
import { ABNORMAL, BrandMark, DemoTray, NAV_ITEMS, PRODUCT_NAME, myOpen, shortPush, type ShellProps } from './shared';

export function ShellB(p: ShellProps) {
  const mine = myOpen(p.person, p.tasks);
  const currentTurn = p.route.name === 'turn' ? p.route.turnId : null;
  return (
    <div className="b-app">
      <nav className="b-rail" aria-label="Pages">
        <a className="b-brand" href={OVERVIEW_HREF} title={PRODUCT_NAME}>
          <BrandMark />
          <span>{PRODUCT_NAME}</span>
        </a>
        {NAV_ITEMS.map(({ key, short, href, Icon, on }) => (
          <a key={key} className="b-nav" href={href} aria-current={on(p.route) ? 'page' : undefined}>
            <Icon />
            <span>{short}</span>
            {key === 'chat' && mine.open > 0 ? <b className={`b-badge${mine.holds ? ' hold' : ''}`}>{mine.open}</b> : null}
          </a>
        ))}
        <span className="spacer" />
        <a className="b-nav b-who" href={CHAT_HREF}>
          <UserIcon />
          <span>{p.person ? p.person.name : 'Sign in'}</span>
          {p.person ? <small>{PERSON_ROLE_LABEL[p.person.role]}</small> : null}
        </a>
      </nav>
      <div className="b-col">
        <header className="b-strip" aria-label="Gate status">
          {(p.state?.gates ?? []).map((g) => (
            <StripCell key={g.gate} g={g} current={g.turn?.turn_id === currentTurn && currentTurn !== null} />
          ))}
          <DemoTray demo={p.state?.demo ?? null} demoControls={p.demoControls} roleSwitch={p.roleSwitch} />
        </header>
        <main className="b-main">
          {p.banners}
          {p.route.name === 'overview' ? p.state ? <HomeB state={p.state} /> : <p className="muted">Loading Gates…</p> : p.children}
        </main>
      </div>
    </div>
  );
}

function StripCell({ g, current }: { g: GateState; current: boolean }) {
  const m = tileModel(g);
  const push = shortPush(g);
  const cls = `b-cell tone-${m.tone}${ABNORMAL.has(m.tone) ? ' abn' : ''}${current ? ' current' : ''}`;
  const body = (
    <>
      <span className="b-cell-top">
        <b>{m.gate}</b>
        <span>{m.flight ?? 'No Turn'}</span>
        {push ? (
          <span className={`b-cell-push num${push.overdue ? ' overdue' : ''}`}>
            {push.n} {push.unit}
          </span>
        ) : null}
      </span>
      <span className="b-cell-status">
        <ToneIcon tone={m.tone} /> {m.severity ? `${m.severity} open` : m.verdict && !m.humanConfirmed ? `${VERDICT_LABEL[m.verdict]}, unconfirmed` : m.statusLabel}
      </span>
    </>
  );
  return m.turnId ? (
    <a className={cls} href={turnHref(m.turnId)}>
      {body}
    </a>
  ) : (
    <div className={cls}>{body}</div>
  );
}

function HomeB({ state }: { state: State }) {
  const rows = queueRows(state.queue);
  const count = (reason: string) => state.queue.filter((q) => q.reason === reason).length;
  const kpis = [
    { label: 'HOLD', n: count('hold'), tone: 'hold' },
    { label: 'Findings to confirm', n: count('findings'), tone: 'remove' },
    { label: 'INCOMPLETE', n: count('incomplete'), tone: 'incomplete' },
    { label: 'Ready for sign-off', n: count('signoff'), tone: 'await' },
    { label: 'Confirmed clear', n: state.gates.filter((g) => g.status === 'confirmed_clear').length, tone: 'confirmed', calm: true },
  ];
  return (
    <div className="b-home">
      <div className="b-kpis">
        {kpis.map((k) => (
          <div key={k.label} className={`b-kpi tone-${k.tone}${k.n > 0 && !k.calm ? ' on' : ''}`}>
            <b className="num">{k.n}</b>
            <span>{k.label}</span>
          </div>
        ))}
      </div>
      <section className="b-board" aria-label="Gates">
        <h2 className="section-title">Gates</h2>
        <div className="b-table" role="table">
          <div className="b-tr b-th" role="row">
            <span>Gate</span>
            <span>Flight</span>
            <span>Status</span>
            <span>Verdict</span>
            <span>Open severity</span>
            <span className="r">Pushback</span>
          </div>
          {state.gates.map((g) => {
            const m = tileModel(g);
            const push = shortPush(g);
            const cells = (
              <>
                <span className="b-gate">{m.gate}</span>
                <span>
                  {m.flight ? (
                    <>
                      <b>{m.flight}</b> <span className="muted">{m.aircraftType}</span>
                    </>
                  ) : (
                    <span className="muted">No Turn</span>
                  )}
                </span>
                <span className="b-status">
                  <ToneIcon tone={m.tone} /> {m.statusLabel}
                </span>
                <span className="b-verdict">
                  {m.verdict ? (
                    <>
                      <b>{VERDICT_LABEL[m.verdict]}</b> {m.humanConfirmed ? <ConfirmedTag /> : <AdvisoryTag />}
                    </>
                  ) : (
                    <span className="muted">–</span>
                  )}
                </span>
                <span>{m.severity ? <SeverityBadge severity={m.severity} /> : <span className="muted">–</span>}</span>
                <span className={`r num${push?.overdue ? ' overdue' : ''}`}>{push ? `${push.n} ${push.unit}` : '–'}</span>
              </>
            );
            const cls = `b-tr tone-${m.tone}${ABNORMAL.has(m.tone) ? ' abn' : ''}`;
            return m.turnId ? (
              <a key={g.gate} className={cls} role="row" href={turnHref(m.turnId)}>
                {cells}
              </a>
            ) : (
              <div key={g.gate} className={cls} role="row">
                {cells}
              </div>
            );
          })}
        </div>
      </section>
      <aside className="b-queue" aria-label="Needs a person">
        <h2 className="section-title">Needs a person, in priority order ({rows.length})</h2>
        {rows.length === 0 ? (
          <p className="empty">Nothing is waiting for a person.</p>
        ) : (
          <ol>
            {rows.map((r, i) => (
              <li key={r.key}>
                <a className={`b-q tone-${r.tone}`} href={turnHref(r.turnId, r.inspectionId)}>
                  <span className="b-q-n num">{i + 1}</span>
                  <span className="b-q-gate">{r.gate}</span>
                  <span className="b-q-body">
                    <b>
                      <ToneIcon tone={r.tone} /> {r.reasonLabel}
                    </b>
                    <span>{r.text}</span>
                  </span>
                  {r.pushbackText ? <span className="b-q-push num small">{r.pushbackText}</span> : null}
                </a>
              </li>
            ))}
          </ol>
        )}
      </aside>
    </div>
  );
}
