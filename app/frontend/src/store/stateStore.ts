import { useSyncExternalStore } from 'react';
import type { Api } from '../api/client';
import type { State } from '../api/types';

export type StateSnapshot = {
  state: State | null;
  /** Set while the last poll failed; the previous state stays on screen. */
  error: unknown;
  loadedAt: number | null;
};

export type StateStore = {
  subscribe(listener: () => void): () => void;
  getSnapshot(): StateSnapshot;
  /** Use a State returned by a demo-control call straight away. */
  set(state: State): void;
  refresh(): Promise<void>;
  start(): void;
  stop(): void;
};

/** Polls GET /api/state (every second, per the contract) and shares the result. */
export function createStateStore(api: Pick<Api, 'getState'>, intervalMs = 1000): StateStore {
  let snapshot: StateSnapshot = { state: null, error: null, loadedAt: null };
  const listeners = new Set<() => void>();
  let timer: ReturnType<typeof setInterval> | null = null;
  let inFlight = false;
  let generation = 0;

  const publish = (next: StateSnapshot) => {
    snapshot = next;
    listeners.forEach((l) => l());
  };

  async function refresh(): Promise<void> {
    if (inFlight) return;
    inFlight = true;
    const started = generation;
    try {
      const state = await api.getState();
      // A demo-control response that arrived meanwhile is newer than this poll.
      if (started === generation) publish({ state, error: null, loadedAt: Date.now() });
    } catch (error) {
      if (started === generation) publish({ ...snapshot, error });
    } finally {
      inFlight = false;
    }
  }

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getSnapshot: () => snapshot,
    set(state) {
      generation += 1;
      publish({ state, error: null, loadedAt: Date.now() });
    },
    refresh,
    start() {
      if (timer) return;
      void refresh();
      timer = setInterval(() => void refresh(), intervalMs);
    },
    stop() {
      if (timer) clearInterval(timer);
      timer = null;
    },
  };
}

export function useStateStore(store: StateStore): StateSnapshot {
  return useSyncExternalStore(store.subscribe, store.getSnapshot);
}
