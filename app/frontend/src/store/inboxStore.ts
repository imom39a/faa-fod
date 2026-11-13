import { useSyncExternalStore } from 'react';
import type { AgentApi, ChatMessage, Proposal, Task } from '../api/agentTypes';
import { ApiError } from '../api/client';
import { EMPTY_THREAD, applyInbox, type ThreadState } from '../lib/inbox';
import type { SessionStore } from './session';

export type InboxSnapshot = {
  /** The person this thread belongs to; null when nobody is signed in. */
  personId: string | null;
  /** False until the first poll for this person has answered. */
  loaded: boolean;
  messages: ChatMessage[];
  tasks: Task[];
  proposals: Proposal[];
  /** Set while the last poll failed; what was loaded stays on screen. */
  error: unknown;
  /** Why the session ended, when the server no longer knows the token. */
  signedOutNote: string | null;
};

export type InboxStore = {
  subscribe(listener: () => void): () => void;
  getSnapshot(): InboxSnapshot;
  /** Poll now (after an action, so its result shows without waiting for the next tick). */
  refresh(): Promise<void>;
  start(): void;
  stop(): void;
  clearNote(): void;
};

const EMPTY: InboxSnapshot = { personId: null, loaded: false, messages: [], tasks: [], proposals: [], error: null, signedOutNote: null };

/**
 * Polls GET /api/agent/inbox about once a second with the message cursor, for
 * whoever is signed in on this tab. It runs on every page, so the header can
 * show open Tasks and the server keeps seeing the person as signed in.
 */
export function createInboxStore(agent: Pick<AgentApi, 'inbox'>, session: SessionStore, intervalMs = 1000): InboxStore {
  let snapshot = EMPTY;
  let thread: ThreadState = EMPTY_THREAD;
  let token: string | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let inFlight = false;
  const listeners = new Set<() => void>();

  const publish = (next: InboxSnapshot) => {
    snapshot = next;
    listeners.forEach((l) => l());
  };

  /** Start a fresh thread when the signed-in person changes. */
  function sync(): string | null {
    const s = session.getSnapshot();
    if ((s?.token ?? null) !== token) {
      token = s?.token ?? null;
      thread = EMPTY_THREAD;
      publish({ ...EMPTY, personId: s?.person.person_id ?? null, signedOutNote: s ? null : snapshot.signedOutNote });
    }
    return token;
  }

  async function refresh(): Promise<void> {
    const asked = sync();
    if (!asked || inFlight) return;
    inFlight = true;
    try {
      const inbox = await agent.inbox(asked, thread.cursor);
      if (asked !== token) return; // Signed out or switched person meanwhile.
      const restarted = thread.epoch !== null && inbox.epoch !== thread.epoch;
      thread = applyInbox(thread, inbox);
      session.updatePerson(inbox.person);
      publish({
        personId: inbox.person.person_id,
        loaded: true,
        messages: thread.messages,
        tasks: inbox.tasks,
        proposals: inbox.pending_proposals,
        error: null,
        signedOutNote: null,
      });
      if (restarted) {
        // The demo was reset: the thread starts again from the first message.
        inFlight = false;
        await refresh();
      }
    } catch (error) {
      if (asked !== token) return;
      if (error instanceof ApiError && (error.code === 'not_signed_in' || error.status === 401)) {
        session.signOut();
        token = null;
        thread = EMPTY_THREAD;
        publish({ ...EMPTY, signedOutNote: 'Your sign-in is no longer valid (the service may have been restarted). Sign in again.' });
      } else {
        publish({ ...snapshot, error });
      }
    } finally {
      inFlight = false;
    }
  }

  let unsubscribe: (() => void) | null = null;

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getSnapshot: () => snapshot,
    refresh,
    start() {
      if (timer) return;
      unsubscribe = session.subscribe(() => void refresh());
      void refresh();
      timer = setInterval(() => void refresh(), intervalMs);
    },
    stop() {
      if (timer) clearInterval(timer);
      timer = null;
      unsubscribe?.();
      unsubscribe = null;
    },
    clearNote() {
      if (snapshot.signedOutNote) publish({ ...snapshot, signedOutNote: null });
    },
  };
}

export function useInboxStore(store: InboxStore): InboxSnapshot {
  return useSyncExternalStore(store.subscribe, store.getSnapshot);
}
