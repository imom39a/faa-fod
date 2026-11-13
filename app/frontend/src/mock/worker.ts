/// <reference lib="webworker" />
/**
 * SharedWorker that hosts the mock server, so two tabs (say Kim's chat and
 * Okafor's) see the same Gates, Tasks and messages. One request per message:
 * `{ id, method, args }` in, `{ id, ok, value | error }` out.
 */
import { ApiError } from '../api/client';
import { createMockServer, type MockMethod, type MockServer } from './server';

declare const self: SharedWorkerGlobalScope;

export type MockRequest = { id: number; method: MockMethod; args: unknown[]; startAt?: number };
export type MockReply =
  | { id: number; ok: true; value: unknown }
  | { id: number; ok: false; error: { code: string; message: string; status: number } };

let server: MockServer | null = null;

self.onconnect = (event) => {
  const port = event.ports[0];
  if (!port) return;
  port.onmessage = (msg: MessageEvent<MockRequest>) => {
    const { id, method, args, startAt } = msg.data;
    // The first tab to connect sets the demo's start time (`?t=`).
    server ??= createMockServer({ startAt });
    const fn = server[method] as (...a: unknown[]) => Promise<unknown>;
    Promise.resolve()
      .then(() => fn(...args))
      .then(
        (value) => port.postMessage({ id, ok: true, value } satisfies MockReply),
        (err: unknown) => {
          const error =
            err instanceof ApiError
              ? { code: err.code, message: err.message, status: err.status }
              : { code: 'internal_error', message: err instanceof Error ? err.message : 'Mock server error', status: 500 };
          port.postMessage({ id, ok: false, error } satisfies MockReply);
        },
      );
  };
};
