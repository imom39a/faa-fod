import { ApiError, type Api } from '../api/client';
import type { AgentApi } from '../api/agentTypes';
import type { Report } from '../api/types';
import { createMockServer, type MockMethod, type MockServer } from './server';
import type { MockReply, MockRequest } from './worker';

/** `?t=120` starts the mock demo clock at 120 s (mock mode only; handy for demos and tests). */
function startAtFromUrl(): number {
  if (typeof window === 'undefined') return 0;
  const t = Number(new URLSearchParams(window.location.search).get('t'));
  return Number.isFinite(t) && t > 0 ? t : 0;
}

type Call = <M extends MockMethod>(method: M, ...args: Parameters<MockServer[M]>) => ReturnType<MockServer[M]>;

/** Calls into the mock server running in this page. */
function localTransport(startAt: number): Call {
  const server = createMockServer({ startAt });
  return ((method: MockMethod, ...args: unknown[]) => (server[method] as (...a: unknown[]) => unknown)(...args)) as Call;
}

/** Calls into the mock server shared by every tab of this browser. */
function workerTransport(startAt: number): Call {
  const worker = new SharedWorker(new URL('./worker.ts', import.meta.url), { type: 'module', name: 'fodgate-mock' });
  const waiting = new Map<number, { resolve: (v: unknown) => void; reject: (e: unknown) => void }>();
  let next = 0;
  worker.port.onmessage = (msg: MessageEvent<MockReply>) => {
    const reply = msg.data;
    const w = waiting.get(reply.id);
    if (!w) return;
    waiting.delete(reply.id);
    if (reply.ok) w.resolve(reply.value);
    else w.reject(new ApiError(reply.error.code, reply.error.message, reply.error.status));
  };
  worker.onerror = () => {
    for (const w of waiting.values()) w.reject(new ApiError('network', 'The mock server (SharedWorker) failed to start.', 0));
    waiting.clear();
  };
  return ((method: MockMethod, ...args: unknown[]) =>
    new Promise<unknown>((resolve, reject) => {
      const id = ++next;
      waiting.set(id, { resolve, reject });
      worker.port.postMessage({ id, method, args, startAt } satisfies MockRequest);
    })) as Call;
}

/**
 * The contract API served from fixture data, with no backend. The mock server
 * lives in a SharedWorker where the browser has one, so two tabs can be two
 * different people in the same demo; otherwise it lives in this page.
 */
export function createMockApi(): Api {
  const startAt = startAtFromUrl();
  const call = typeof SharedWorker === 'undefined' ? localTransport(startAt) : workerTransport(startAt);

  const agent: AgentApi = {
    roster: () => call('agentRoster'),
    join: (personId, pin) => call('agentJoin', personId, pin),
    inbox: (token, after = 0) => call('agentInbox', token, after),
    command: (token, c) => call('agentCommand', token, c),
    commandText: (token, text) => call('agentCommandText', token, text),
    answerProposal: (token, proposalId, accept) => call('agentAnswer', token, proposalId, accept),
    say: (token, text) => call('agentSay', token, text),
    board: () => call('agentBoard'),
    activity: (q = {}) => call('agentActivity', q.after ?? 0, q.gate, q.turn_id, q.limit),
  };

  return {
    getState: () => call('getState'),
    getTurn: (turnId) => call('getTurn', turnId),
    getInspection: (id) => call('getInspection', id),
    exportHref: (report: Report) => `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(report, null, 2))}`,
    confirmFinding: (id, findingId, body) => call('confirmFinding', id, findingId, body),
    confirmAll: (id, who) => call('confirmAll', id, who),
    reinspectAngle: (id, angle, who) => call('reinspectAngle', id, angle, who),
    checkedByEye: (id, angle, who) => call('checkedByEye', id, angle, who),
    signoff: (id, who) => call('signoff', id, who),
    inspectGate: (gate, body) => call('inspectGate', gate, body),
    demoPlay: () => call('demoPlay'),
    demoPause: () => call('demoPause'),
    demoReset: () => call('demoReset'),
    demoSpeed: (speed) => call('demoSpeed', speed),
    assistant: (body) => call('assistant', body.inspection_id, body.message),
    getRules: () => call('getRules'),
    agent,
  };
}
