import { useSyncExternalStore } from 'react';
import type { RosterPerson } from '../api/agentTypes';

/**
 * Who is signed in to the chat page in this tab. sessionStorage is per tab, so
 * two tabs can be two different people; tokens are kept per person, so going
 * back to someone already signed in on this tab needs no PIN.
 */
export type Session = { token: string; person: RosterPerson };

const CURRENT_KEY = 'fodgate.agent.current';
const tokenKey = (personId: string) => `fodgate.agent.token.${personId}`;
const personKey = (personId: string) => `fodgate.agent.person.${personId}`;

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export type SessionStore = {
  subscribe(listener: () => void): () => void;
  getSnapshot(): Session | null;
  signIn(session: Session): void;
  /** Forget this tab's session for the current person. */
  signOut(): void;
  /** Keep the stored name, role and Shift in step with what the server says. */
  updatePerson(person: RosterPerson): void;
  /** A token kept from an earlier sign-in on this tab, if any. */
  savedToken(personId: string): string | null;
};

function tabStorage(): StorageLike | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null; // Storage blocked: the session lasts for this page only.
  }
}

export function createSessionStore(storage: StorageLike | null = tabStorage()): SessionStore {
  const read = (key: string): string | null => {
    try {
      return storage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  };
  const write = (key: string, value: string | null) => {
    try {
      if (value === null) storage?.removeItem(key);
      else storage?.setItem(key, value);
    } catch {
      // Storage unavailable: keep going with the in-memory session.
    }
  };

  function load(): Session | null {
    const id = read(CURRENT_KEY);
    const token = id ? read(tokenKey(id)) : null;
    const raw = id ? read(personKey(id)) : null;
    if (!id || !token || !raw) return null;
    try {
      const person = JSON.parse(raw) as RosterPerson;
      return person && person.person_id === id ? { token, person } : null;
    } catch {
      return null;
    }
  }

  let current = load();
  const listeners = new Set<() => void>();
  const publish = (next: Session | null) => {
    current = next;
    listeners.forEach((l) => l());
  };

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getSnapshot: () => current,
    signIn(session) {
      const id = session.person.person_id;
      write(tokenKey(id), session.token);
      write(personKey(id), JSON.stringify(session.person));
      write(CURRENT_KEY, id);
      publish(session);
    },
    signOut() {
      if (current) {
        write(tokenKey(current.person.person_id), null);
        write(personKey(current.person.person_id), null);
      }
      write(CURRENT_KEY, null);
      publish(null);
    },
    updatePerson(person) {
      if (!current || current.person.person_id !== person.person_id) return;
      const a = current.person;
      if (a.name === person.name && a.role === person.role && a.shift === person.shift && a.gates.join() === person.gates.join()) return;
      write(personKey(person.person_id), JSON.stringify(person));
      publish({ token: current.token, person });
    },
    savedToken: (personId) => read(tokenKey(personId)),
  };
}

export function useSession(store: SessionStore): Session | null {
  return useSyncExternalStore(store.subscribe, store.getSnapshot);
}
