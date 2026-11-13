import type { RosterPerson, Task } from '../api/agentTypes';
import { PERSON_ROLE_LABEL } from '../lib/labels';
import { isActiveTask } from '../lib/taskActions';
import { CHAT_HREF, OVERVIEW_HREF, activityHref, type Route } from '../route';
import { ChatIcon, GridIcon, ListIcon, UserIcon } from './icons';

type Props = {
  route: Route;
  /** Who is signed in to the chat on this tab, if anyone. */
  person: RosterPerson | null;
  tasks: Task[];
};

/** Page links and the "signed in as" indicator. */
export function Nav({ route, person, tasks }: Props) {
  const open = tasks.filter((t) => isActiveTask(t) && t.assignee_id === person?.person_id);
  const holds = open.filter((t) => t.severity === 'HOLD').length;
  const here = (name: Route['name'] | 'turn') => (route.name === name ? 'page' : undefined);
  return (
    <>
      <nav className="nav" aria-label="Pages">
        <a href={OVERVIEW_HREF} aria-current={route.name === 'overview' || route.name === 'turn' ? 'page' : undefined}>
          <GridIcon className="vicon" /> Gates
        </a>
        <a href={CHAT_HREF} aria-current={here('chat')}>
          <ChatIcon className="vicon" /> Chat
          {person && open.length > 0 ? (
            <span className={`nav-count${holds > 0 ? ' has-hold' : ''}`}>
              {open.length}
              <span className="sr-only"> open {open.length === 1 ? 'Task' : 'Tasks'}</span>
              {holds > 0 ? ' · HOLD' : ''}
            </span>
          ) : null}
        </a>
        <a href={activityHref()} aria-current={here('activity')}>
          <ListIcon className="vicon" /> Activity
        </a>
      </nav>
      <a className={`who-chip${person ? '' : ' nobody'}`} href={CHAT_HREF} title="Chat sign-in for this browser tab">
        <UserIcon className="vicon" />
        {person ? (
          <span>
            <small>Signed in as</small>
            {person.name} · {PERSON_ROLE_LABEL[person.role]}
          </span>
        ) : (
          <span>
            <small>Chat</small>
            Not signed in
          </span>
        )}
      </a>
    </>
  );
}
