import { useEffect, useMemo, useState } from 'react';
import type { Api } from './api/client';
import { describeError } from './api/errors';
import type { RuleSet } from './api/types';
import { AppShell } from './components/AppShell';
import { ActivityPage } from './components/ActivityPage';
import { ChatPage } from './components/chat/ChatPage';
import { CrewTasksPage } from './components/CrewTasksPage';
import { DemoControls, RoleSwitch } from './components/Header';
import { SpinnerIcon } from './components/icons';
import { Overview } from './components/Overview';
import { SettingsPage } from './components/SettingsPage';
import { TurnView } from './components/TurnView';
import { useRoute } from './route';
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
    <AppShell
      route={route}
      state={state}
      person={session?.person ?? null}
      tasks={inbox.tasks}
      demoControls={
        <DemoControls
          api={api}
          demo={state?.demo ?? null}
          onState={(s) => {
            setDemoError(null);
            store.set(s);
          }}
          onError={setDemoError}
        />
      }
      roleSwitch={<RoleSwitch identity={identity} setRole={setRole} setName={setName} />}
    >
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
      ) : route.name === 'settings' ? (
        <SettingsPage />
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
    </AppShell>
  );
}
