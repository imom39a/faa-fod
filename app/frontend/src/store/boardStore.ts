import { useEffect, useMemo, useSyncExternalStore } from 'react';
import type { AgentApi, Board } from '../api/agentTypes';

export type BoardSnapshot = {
  /** The last Board received. Kept on screen while a later poll fails. */
  board: Board | null;
  /** When `board` arrived (ms since the epoch); 0 before the first answer. */
  receivedAt: number;
  /** Set while the last poll failed. */
  error: unknown;
};

export type BoardStore = {
  subscribe(listener: () => void): () => void;
  getSnapshot(): BoardSnapshot;
  start(): void;
  stop(): void;
};

export type BoardStoreOptions = {
  /** Poll interval while the service answers. */
  intervalMs?: number;
  /** Longest wait between polls while the service fails. */
  maxBackoffMs?: number;
  now?: () => number;
};

const EMPTY: BoardSnapshot = { board: null, receivedAt: 0, error: null };

/**
 * Polls GET /api/agent/board about once a second, for the Crew and Tasks view.
 * One request at a time: the next poll is scheduled only after the last one
 * answers. On an error the wait doubles (up to `maxBackoffMs`) and the last
 * good Board stays. Each Board replaces the previous one whole, so a demo
 * Reset shows on the next poll (the Board carries no epoch to watch).
 */
export function createBoardStore(agent: Pick<AgentApi, 'board'>, options: BoardStoreOptions = {}): BoardStore {
  const intervalMs = options.intervalMs ?? 1000;
  const maxBackoffMs = options.maxBackoffMs ?? 8000;
  const now = options.now ?? Date.now;
  let snapshot = EMPTY;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let running = false;
  let inFlight = false;
  let failures = 0;
  /** Bumped by stop(), so an answer that arrives after it is dropped. */
  let generation = 0;
  const listeners = new Set<() => void>();

  const publish = (next: BoardSnapshot) => {
    snapshot = next;
    listeners.forEach((l) => l());
  };

  /** Polls start `intervalMs` apart (the request's own time counts), or further apart after failures. */
  const schedule = (startedAt: number) => {
    if (!running) return;
    const period = failures === 0 ? intervalMs : Math.min(maxBackoffMs, intervalMs * 2 ** failures);
    timer = setTimeout(() => void poll(), Math.max(0, period - (now() - startedAt)));
  };

  async function poll(): Promise<void> {
    timer = null;
    if (!running || inFlight) return;
    inFlight = true;
    const asked = generation;
    const startedAt = now();
    try {
      const board = await agent.board();
      if (asked !== generation) return;
      failures = 0;
      publish({ board, receivedAt: now(), error: null });
    } catch (error) {
      if (asked !== generation) return;
      failures += 1;
      publish({ ...snapshot, error });
    } finally {
      if (asked === generation) {
        inFlight = false;
        schedule(startedAt);
      }
    }
  }

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getSnapshot: () => snapshot,
    start() {
      if (running) return;
      running = true;
      failures = 0;
      void poll();
    },
    stop() {
      running = false;
      generation += 1;
      inFlight = false;
      if (timer) clearTimeout(timer);
      timer = null;
    },
  };
}

/** The live Board while the calling component is mounted. */
export function useBoard(agent: Pick<AgentApi, 'board'>): BoardSnapshot {
  const store = useMemo(() => createBoardStore(agent), [agent]);
  useEffect(() => {
    store.start();
    return () => store.stop();
  }, [store]);
  return useSyncExternalStore(store.subscribe, store.getSnapshot);
}
