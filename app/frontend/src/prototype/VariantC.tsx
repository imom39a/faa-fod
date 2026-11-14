// PROTOTYPE (throwaway). Variant C, "Split view, night": a tablet in a tug or at the
// gate at night. Near-black monochrome theme where only severity carries colour, a Gate
// list that stays beside the open Turn (most urgent first), and one "next up" action.
import { AdvisoryTag, ConfirmedTag, SeverityBadge } from '../components/bits';
import { ArrowRightIcon, CheckCircleIcon, ToneIcon, UserIcon } from '../components/icons';
import { queueRows, tileModel, type QueueRowModel } from '../lib/gates';
import { PERSON_ROLE_LABEL, VERDICT_LABEL } from '../lib/labels';
import { CHAT_HREF, OVERVIEW_HREF, turnHref } from '../route';
import type { GateState, State } from '../api/types';
import { BrandMark, DemoTray, NAV_ITEMS, PRODUCT_NAME, PRODUCT_TAGLINE, myOpen, shortPush, type ShellProps } from './shared';

export function ShellC(p: ShellProps) {
  const mine = myOpen(p.person, p.tasks);
  const split = p.route.name === 'overview' || p.route.name === 'turn';
  const currentTurn = p.route.name === 'turn' ? p.route.turnId : null;
  return (
    <div className={`c-app${split ? ' split' : ''}${currentTurn ? ' has-detail' : ''}`}>
      <header className="c-top">
        <a className="brand-link" href={OVERVIEW_HREF}>
          <BrandMark /> {PRODUCT_NAME}
          <small>{PRODUCT_TAGLINE}</small>
        </a>
        <nav className="c-nav" aria-label="Pages">
          {NAV_ITEMS.map(({ key, label, href, Icon, on }) => (
            <a key={key} href={href} aria-current={on(p.route) ? 'page' : undefined}>
              <Icon className="vicon" /> {label}
              {key === 'chat' && mine.open > 0 ? <b className={`c-badge${mine.holds ? ' hold' : ''}`}>{mine.open}</b> : null}
            </a>
          ))}
        </nav>
        <span className="spacer" />
        <DemoTray demo={p.state?.demo ?? null} demoControls={p.demoControls} roleSwitch={p.roleSwitch} />
        <a className="c-who" href={CHAT_HREF}>
          <UserIcon className="vicon" />
          {p.person ? (
            <span>
              {p.person.name}
              <small>{PERSON_ROLE_LABEL[p.person.role]}</small>
            </span>
          ) : (
            'Sign in'
          )}
        </a>
      </header>
      <div className="c-body">
        {split ? <GateList state={p.state} currentTurn={currentTurn} /> : null}
        <main className="c-main">
          {p.banners}
          {p.route.name === 'overview' ? (
            p.state ? <HomeC state={p.state} /> : <p className="muted">Loading Gates…</p>
          ) : (
            <>
              {p.children}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

/** Most urgent first: the queue's own order, then time to pushback, then Gates with no Turn. */
function byUrgency(state: State): { g: GateState; q: QueueRowModel | null }[] {
  const rows = queueRows(state.queue);
  const rank = (g: GateState) => {
    const i = rows.findIndex((r) => r.gate === g.gate);
    if (i >= 0) return i;
    const m = g.turn?.minutes_to_pushback;
    return 1000 + (g.turn && typeof m === 'number' ? m : 100000);
  };
  return [...state.gates].sort((a, b) => rank(a) - rank(b)).map((g) => ({ g, q: rows.find((r) => r.gate === g.gate) ?? null }));
}

function GateList({ state, currentTurn }: { state: State | null; currentTurn: string | null }) {
  return (
    <aside className="c-list" aria-label="Gates, most urgent first">
      <h2 className="section-title">Gates · most urgent first</h2>
      <ul>
        {(state ? byUrgency(state) : []).map(({ g, q }) => {
          const m = tileModel(g);
          const push = shortPush(g);
          const body = (
            <>
              <span className="c-row-gate">{m.gate}</span>
              <span className="c-row-body">
                <span className="c-row-status">
                  <ToneIcon tone={q?.tone ?? m.tone} /> {q ? q.reasonLabel : m.statusLabel}
                </span>
                <span className="c-row-sub">
                  {m.flight ? `${m.flight} · ${m.aircraftType}` : 'No Turn'}
                  {m.verdict ? ` · ${VERDICT_LABEL[m.verdict]}` : ''}
                </span>
                <span className="c-row-tags">
                  {m.severity && q?.reasonLabel !== m.severity ? <SeverityBadge severity={m.severity} /> : null}
                  {m.verdict ? m.humanConfirmed ? <ConfirmedTag /> : <AdvisoryTag /> : null}
                </span>
              </span>
              {push ? (
                <span className={`c-row-push num${push.overdue ? ' overdue' : ''}`}>
                  {push.n}
                  <small>{push.unit}</small>
                </span>
              ) : (
                <span />
              )}
            </>
          );
          const cls = `c-row tone-${q?.tone ?? m.tone}${q ? ' needs' : ''}`;
          return (
            <li key={g.gate}>
              {m.turnId ? (
                <a className={cls} href={turnHref(m.turnId)} aria-current={m.turnId === currentTurn ? 'true' : undefined}>
                  {body}
                </a>
              ) : (
                <div className={cls}>{body}</div>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}

function HomeC({ state }: { state: State }) {
  const rows = queueRows(state.queue);
  const [next, ...rest] = rows;
  if (!next) {
    const clear = state.gates.filter((g) => g.status === 'confirmed_clear').length;
    return (
      <div className="c-home">
        <div className="c-hero calm">
          <CheckCircleIcon />
          <h2>Nothing is waiting for a person</h2>
          <p className="muted">
            {clear} of {state.gates.length} Gates confirmed clear. New Findings appear here the moment an Inspection reports them.
          </p>
        </div>
      </div>
    );
  }
  return (
    <div className="c-home">
      <section className={`c-hero tone-${next.tone}`} aria-label="Next up">
        <span className="c-hero-label">Next up</span>
        <div className="c-hero-main">
          <span className="c-hero-gate">{next.gate}</span>
          <div>
            <h2>
              <ToneIcon tone={next.tone} /> {next.reasonLabel}
            </h2>
            <p>{next.text}</p>
            {next.pushbackText ? <p className="c-hero-push num">{next.pushbackText}</p> : null}
          </div>
        </div>
        <a className="btn primary c-hero-go" href={turnHref(next.turnId, next.inspectionId)}>
          Open Gate {next.gate} <ArrowRightIcon className="vicon" />
        </a>
      </section>
      {rest.length > 0 ? (
        <section aria-label="Also waiting">
          <h2 className="section-title">Also waiting ({rest.length})</h2>
          <ol className="c-rest">
            {rest.map((r) => (
              <li key={r.key}>
                <a className={`c-rest-item tone-${r.tone}`} href={turnHref(r.turnId, r.inspectionId)}>
                  <b className="c-rest-gate">{r.gate}</b>
                  <span className="c-rest-reason">
                    <ToneIcon tone={r.tone} /> {r.reasonLabel}
                  </span>
                  <span className="c-rest-text">{r.text}</span>
                  {r.pushbackText ? <span className="num small nowrap">{r.pushbackText}</span> : null}
                </a>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}
