import { useState, type ReactNode } from 'react';
import { MOCK_MODE } from '../api';
import type { RosterPerson, Task } from '../api/agentTypes';
import type { DemoState, GateState, State } from '../api/types';
import { PRODUCT_NAME } from '../lib/brand';
import { formatClock } from '../lib/format';
import { isAbnormal, shortPushback, stripLabel, tileModel } from '../lib/gates';
import { PERSON_ROLE_LABEL } from '../lib/labels';
import { isActiveTask } from '../lib/taskActions';
import { CHAT_HREF, CREW_HREF, OVERVIEW_HREF, activityHref, turnHref, type Route } from '../route';
import { BrandMark, ChatIcon, GridIcon, ListIcon, TaskIcon, ToneIcon, UserIcon } from './icons';

type Props = {
  route: Route;
  state: State | null;
  /** Who is signed in to the chat on this tab, if anyone. */
  person: RosterPerson | null;
  tasks: Task[];
  /** Demo clock controls and the role switch: demo scaffolding, kept in a tray off the product chrome. */
  demoControls: ReactNode;
  roleSwitch: ReactNode;
  children: ReactNode;
};

const PAGES = [
  { key: 'gates', label: 'Gates', href: OVERVIEW_HREF, Icon: GridIcon, on: (r: Route) => r.name === 'overview' || r.name === 'turn' },
  { key: 'chat', label: 'Chat', href: CHAT_HREF, Icon: ChatIcon, on: (r: Route) => r.name === 'chat' },
  { key: 'crew', label: 'Crew and Tasks', href: CREW_HREF, Icon: TaskIcon, on: (r: Route) => r.name === 'crew' },
  { key: 'activity', label: 'Activity', href: activityHref(), Icon: ListIcon, on: (r: Route) => r.name === 'activity' },
] as const;

/**
 * The frame every page sits in (spec/design-system.md, "Layout"): the page rail on the
 * left, the Gate strip across the top of every page, and the page below it.
 */
export function AppShell({ route, state, person, tasks, demoControls, roleSwitch, children }: Props) {
  const open = tasks.filter((t) => isActiveTask(t) && t.assignee_id === person?.person_id);
  const holds = open.filter((t) => t.severity === 'HOLD').length;
  const currentTurn = route.name === 'turn' ? route.turnId : null;
  return (
    <div className="shell">
      <nav className="rail" aria-label="Pages">
        <a className="rail-brand" href={OVERVIEW_HREF}>
          <BrandMark />
          <span>{PRODUCT_NAME}</span>
        </a>
        {PAGES.map(({ key, label, href, Icon, on }) => (
          <a key={key} className="rail-link" href={href} aria-current={on(route) ? 'page' : undefined}>
            <Icon />
            <span>{label}</span>
            {key === 'chat' && person && open.length > 0 ? (
              <b className={`rail-count${holds > 0 ? ' has-hold' : ''}`}>
                {open.length}
                <span className="sr-only">
                  {' '}
                  open {open.length === 1 ? 'Task' : 'Tasks'}
                  {holds > 0 ? ', HOLD' : ''}
                </span>
              </b>
            ) : null}
          </a>
        ))}
        <span className="spacer" />
        <a className="rail-link rail-who" href={CHAT_HREF} title="Chat sign-in for this browser tab">
          <UserIcon />
          {person ? (
            <>
              <span>{person.name}</span>
              <small>{PERSON_ROLE_LABEL[person.role]}</small>
            </>
          ) : (
            <span>Not signed in</span>
          )}
        </a>
      </nav>
      <div className="shell-col">
        <header className="strip">
          <div className="strip-gates" role="list" aria-label="Gate status">
            {(state?.gates ?? []).map((g) => (
              <StripCell key={g.gate} gate={g} current={currentTurn !== null && g.turn?.turn_id === currentTurn} />
            ))}
          </div>
          <DemoTray demo={state?.demo ?? null} demoControls={demoControls} roleSwitch={roleSwitch} />
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}

/** One Gate in the strip. Grey while normal; filled with the severity colour only when abnormal. */
function StripCell({ gate, current }: { gate: GateState; current: boolean }) {
  const m = tileModel(gate);
  const push = shortPushback(gate);
  const label = stripLabel(m);
  const cls = `strip-cell tone-${m.tone}${isAbnormal(m.tone) ? ' is-abnormal' : ''}`;
  const body = (
    <>
      <span className="strip-top">
        <b>{m.gate}</b>
        <span>{m.flight ?? 'No Turn'}</span>
        {push ? <span className={`strip-push num${push.overdue ? ' overdue' : ''}`}>{push.text}</span> : null}
      </span>
      <span className="strip-status">
        <ToneIcon tone={m.tone} /> {label}
      </span>
    </>
  );
  return m.turnId ? (
    <a className={cls} role="listitem" href={turnHref(m.turnId)} aria-current={current ? 'true' : undefined} aria-label={`Gate ${m.gate}: ${label}`}>
      {body}
    </a>
  ) : (
    <div className={cls} role="listitem" aria-label={`Gate ${m.gate}: ${label}`}>
      {body}
    </div>
  );
}

function DemoTray({ demo, demoControls, roleSwitch }: { demo: DemoState | null; demoControls: ReactNode; roleSwitch: ReactNode }) {
  const [open, setOpen] = useState(false);
  const finished = demo ? demo.t >= demo.duration : false;
  return (
    <div className="demo-tray">
      <button type="button" className="demo-tray-btn" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="num" aria-label="Demo clock">
          {demo ? formatClock(demo.t) : '-:--'}
        </span>
        <small>{!demo ? 'demo clock' : finished ? 'demo finished' : demo.playing ? `demo ${demo.speed}x` : 'demo paused'}</small>
      </button>
      {open ? (
        <div className="demo-tray-panel">
          <p className="small muted">
            Demo controls, and the role switch that stands in for sign-in.
            {MOCK_MODE ? (
              <>
                {' '}
                <span className="mock-tag" title="Fixture data served in the browser. No backend, no model calls.">
                  MOCK DATA
                </span>
              </>
            ) : null}
          </p>
          {demoControls}
          {roleSwitch}
        </div>
      ) : null}
    </div>
  );
}
