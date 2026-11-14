import { useEffect, useMemo, useState } from 'react';
import type { Api } from './api/client';
import { describeError } from './api/errors';
import { MOCK_MODE } from './api';
import type { RuleSet } from './api/types';
import { ActivityPage } from './components/ActivityPage';
import { ChatPage } from './components/chat/ChatPage';
import { CrewTasksPage } from './components/CrewTasksPage';
import { DemoControls, RoleSwitch } from './components/Header';
import { Nav } from './components/Nav';
import { SpinnerIcon } from './components/icons';
import { Overview } from './components/Overview';
import { TurnView } from './components/TurnView';
import { OVERVIEW_HREF, useRoute } from './route';
import { useIdentity } from './store/identity';
import { createInboxStore, useInboxStore } from './store/inboxStore';
import { createSessionStore, useSession } from './store/session';
import { useStateStore, type StateStore } from './store/stateStore';

export function App({ api, store }: { api: Api; store: StateStore }) {
  const { state, error } = useStateStore(store);
  const route = useRoute();
  const { identity, person, setRole, setName } = useIdentity();
  const [rules, setRules] = useState<RuleSet | null>(null);
  const [demoError, setDemoError] = useState<string | null>(null);
  const connected = state !== null;
  // Chat sign-in for this tab, and that person's inbox (polled on every page).
  const sessionStore = useMemo(() => createSessionStore(), []);
  const inboxStore = useMemo(() => createInboxStore(api.agent, sessionStore), [api, sessionStore]);
  const session = useSession(sessionStore);
  const inbox = useInboxStore(inboxStore);

  useEffect(() => {
    inboxStore.start();
    return () => inboxStore.stop();
  }, [inboxStore]);

  useEffect(() => {
    store.start();
    return () => store.stop();
  }, [store]);

  // The rule set gives category labels; load it once the service answers.
  useEffect(() => {
    if (!connected || rules) return;
    let cancelled = false;
    api
      .getRules()
      .then((r) => {
        if (!cancelled) setRules(r);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [api, connected, rules]);

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <h1>
            <a href={OVERVIEW_HREF}>Gate FOD Inspection</a>
          </h1>
          {MOCK_MODE && (
            <span className="mock-tag" title="Fixture data served in the browser. No backend, no model calls.">
              MOCK DATA
            </span>
          )}
        </div>
        <Nav route={route} person={session?.person ?? null} tasks={inbox.tasks} />
        <DemoControls
          api={api}
          demo={state?.demo ?? null}
          onState={(s) => {
            setDemoError(null);
            store.set(s);
          }}
          onError={setDemoError}
        />
        <RoleSwitch identity={identity} setRole={setRole} setName={setName} />
      </header>
      <main>
        {error ? (
          <div className="banner error" role="alert">
            <span className="grow">
              <strong>Not connected</strong>
              {describeError(error, 'load')}
              {state ? ' Showing the last state received.' : ''}
            </span>
          </div>
        ) : null}
        {demoError ? (
          <div className="banner error" role="alert">
            <span className="grow">
              <strong>Demo control failed</strong>
              {demoError}
            </span>
            <button type="button" className="compact quiet" onClick={() => setDemoError(null)}>
              Dismiss
            </button>
          </div>
        ) : null}
        {route.name === 'chat' ? (
          <ChatPage agent={api.agent} sessionStore={sessionStore} inboxStore={inboxStore} />
        ) : route.name === 'crew' ? (
          <CrewTasksPage agent={api.agent} />
        ) : route.name === 'activity' ? (
          <ActivityPage agent={api.agent} filter={route.filter} />
        ) : route.name === 'turn' ? (
          <TurnView
            api={api}
            turnId={route.turnId}
            pinnedInspectionId={route.inspectionId}
            focusFindingId={route.finding}
            state={state}
            person={person}
            rules={rules}
            refreshState={() => void store.refresh()}
          />
        ) : state ? (
          <Overview state={state} />
        ) : !error ? (
          <p className="muted row">
            <SpinnerIcon className="vicon" /> Loading Gates…
          </p>
        ) : null}
      </main>
    </>
  );
}
