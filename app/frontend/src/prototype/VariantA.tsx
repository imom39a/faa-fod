// PROTOTYPE (throwaway). Variant A, "Handheld, daylight": a phone or small tablet held in
// one gloved hand on the ramp in sunlight. Light high-contrast theme, one column, 56px targets,
// navigation in the thumb zone, and the home screen opens on what needs a person.
import { AdvisoryTag, ConfirmedTag } from '../components/bits';
import { ArrowRightIcon, CheckCircleIcon, ToneIcon, UserIcon } from '../components/icons';
import { queueRows, tileModel } from '../lib/gates';
import { PERSON_ROLE_LABEL, VERDICT_LABEL } from '../lib/labels';
import { plural } from '../lib/format';
import { CHAT_HREF, OVERVIEW_HREF, turnHref } from '../route';
import type { State } from '../api/types';
import { BrandMark, DemoTray, NAV_ITEMS, PRODUCT_NAME, myOpen, shortPush, type ShellProps } from './shared';

export function ShellA(p: ShellProps) {
  const mine = myOpen(p.person, p.tasks);
  return (
    <div className="a-app">
      <header className="a-top">
        <a className="brand-link" href={OVERVIEW_HREF}>
          <BrandMark /> {PRODUCT_NAME}
        </a>
        <span className="spacer" />
        <DemoTray demo={p.state?.demo ?? null} demoControls={p.demoControls} roleSwitch={p.roleSwitch} />
        <a className="a-who" href={CHAT_HREF} aria-label={p.person ? `Signed in as ${p.person.name}` : 'Sign in'}>
          <UserIcon className="vicon" />
          {p.person ? p.person.name : 'Sign in'}
        </a>
      </header>
      <main className="a-main">
        {p.banners}
        {p.route.name === 'overview' ? (
          p.state ? <HomeA state={p.state} mine={mine} personName={p.person ? `${p.person.name}, ${PERSON_ROLE_LABEL[p.person.role]}` : null} /> : <p className="muted">Loading Gates…</p>
        ) : (
          p.children
        )}
      </main>
      <nav className="a-tabs" aria-label="Pages">
        {NAV_ITEMS.map(({ key, short, href, Icon, on }) => (
          <a key={key} href={href} aria-current={on(p.route) ? 'page' : undefined}>
            <Icon />
            <span>{short}</span>
            {key === 'chat' && mine.open > 0 ? <b className={`a-badge${mine.holds ? ' hold' : ''}`}>{mine.open}</b> : null}
          </a>
        ))}
      </nav>
    </div>
  );
}

function HomeA({ state, mine, personName }: { state: State; mine: { open: number; holds: number }; personName: string | null }) {
  const rows = queueRows(state.queue);
  return (
    <div className="a-home">
      {mine.open > 0 ? (
        <a className={`a-mine${mine.holds ? ' hold' : ''}`} href={CHAT_HREF}>
          <span>
            <small>{personName}</small>
            <strong>
              {plural(mine.open, 'Task')} for you{mine.holds ? ` · ${mine.holds} HOLD` : ''}
            </strong>
          </span>
          <ArrowRightIcon />
        </a>
      ) : null}

      <section aria-label="Needs a person">
        <h2 className="a-h">{rows.length === 0 ? 'Nothing needs a person' : `${plural(rows.length, 'thing')} ${rows.length === 1 ? 'needs' : 'need'} a person`}</h2>
        {rows.length === 0 ? (
          <p className="a-calm">
            <CheckCircleIcon /> Every Inspection so far is confirmed or still running.
          </p>
        ) : (
          <ol className="a-acts">
            {rows.map((r) => (
              <li key={r.key}>
                <a className={`a-act tone-${r.tone}`} href={turnHref(r.turnId, r.inspectionId)}>
                  <span className="a-act-gate">{r.gate}</span>
                  <span className="a-act-body">
                    <span className="a-act-reason">
                      <ToneIcon tone={r.tone} /> {r.reasonLabel}
                    </span>
                    <span className="a-act-text">{r.text}</span>
                    {r.pushbackText ? <span className="a-act-push num">{r.pushbackText}</span> : null}
                  </span>
                  <ArrowRightIcon className="a-go" />
                </a>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-label="Gates">
        <h2 className="a-h minor">All Gates</h2>
        <ul className="a-gates">
          {state.gates.map((g) => {
            const m = tileModel(g);
            const push = shortPush(g);
            const body = (
              <>
                <span className="a-gate-id">{m.gate}</span>
                <span className="a-gate-body">
                  <span className="a-gate-status">
                    <ToneIcon tone={m.tone} /> {m.severity ? `${m.severity} open` : m.statusLabel}
                  </span>
                  <span className="a-gate-sub">
                    {m.flight ? `${m.flight} · ${m.aircraftType}` : 'No Turn'}
                    {m.verdict ? ` · ${VERDICT_LABEL[m.verdict]}` : ''} {m.verdict ? m.humanConfirmed ? <ConfirmedTag /> : <AdvisoryTag /> : null}
                  </span>
                </span>
                {push ? (
                  <span className={`a-gate-push num${push.overdue ? ' overdue' : ''}`}>
                    {push.n}
                    <small>{push.unit}</small>
                  </span>
                ) : (
                  <span />
                )}
              </>
            );
            return (
              <li key={g.gate}>
                {m.turnId ? (
                  <a className={`a-gate tone-${m.tone}`} href={turnHref(m.turnId)}>
                    {body}
                  </a>
                ) : (
                  <div className={`a-gate tone-${m.tone}`}>{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
