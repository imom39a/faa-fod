import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Board } from '../api/agentTypes';
import { createBoardStore } from './boardStore';

const board = (clock_t: number) => ({ clock_t }) as Board;

describe('board store', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('polls about once a second and never overlaps requests', async () => {
    let inFlight = 0;
    let maxInFlight = 0;
    let calls = 0;
    const agent = {
      board: () => {
        calls += 1;
        inFlight += 1;
        maxInFlight = Math.max(maxInFlight, inFlight);
        return new Promise<Board>((resolve) =>
          setTimeout(() => {
            inFlight -= 1;
            resolve(board(calls));
          }, 1500),
        );
      },
    };
    const store = createBoardStore(agent);
    store.start();
    await vi.advanceTimersByTimeAsync(5000);
    expect(maxInFlight).toBe(1);
    // A 1.5 s request means a poll every 1.5 s, never two at once.
    expect(calls).toBe(4);
    store.stop();
  });

  it('starts polls one interval apart when the service is quick', async () => {
    const agent = { board: vi.fn(async () => board(1)) };
    const store = createBoardStore(agent);
    store.start();
    await vi.advanceTimersByTimeAsync(3050);
    expect(agent.board).toHaveBeenCalledTimes(4);
    store.stop();
  });

  it('keeps the last good Board on an error and backs off', async () => {
    let fail = false;
    const agent = {
      board: vi.fn(async () => {
        if (fail) throw new Error('down');
        return board(7);
      }),
    };
    const store = createBoardStore(agent, { intervalMs: 1000, maxBackoffMs: 4000 });
    store.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(store.getSnapshot().board?.clock_t).toBe(7);

    fail = true;
    await vi.advanceTimersByTimeAsync(1000); // fails: next wait 2 s
    expect(store.getSnapshot().error).toBeInstanceOf(Error);
    expect(store.getSnapshot().board?.clock_t).toBe(7);
    const afterFirstFailure = agent.board.mock.calls.length;
    await vi.advanceTimersByTimeAsync(1900);
    expect(agent.board.mock.calls.length).toBe(afterFirstFailure);
    await vi.advanceTimersByTimeAsync(100); // fails again: next wait 4 s (the cap)
    expect(agent.board.mock.calls.length).toBe(afterFirstFailure + 1);

    fail = false;
    await vi.advanceTimersByTimeAsync(4000);
    expect(store.getSnapshot().error).toBeNull();
    store.stop();
  });

  it('stops polling and drops a late answer after stop()', async () => {
    let resolve: (b: Board) => void = () => undefined;
    const agent = { board: vi.fn(() => new Promise<Board>((r) => (resolve = r))) };
    const store = createBoardStore(agent);
    const seen = vi.fn();
    store.subscribe(seen);
    store.start();
    store.stop();
    resolve(board(1));
    await vi.advanceTimersByTimeAsync(5000);
    expect(agent.board).toHaveBeenCalledTimes(1);
    expect(seen).not.toHaveBeenCalled();
    expect(store.getSnapshot().board).toBeNull();
  });
});
