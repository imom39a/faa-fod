/**
 * The mock "server": one MockBackend and one MockDispatcher behind the same
 * calls the HTTP client makes, with a little latency and a ticking demo clock.
 * It runs in a SharedWorker (worker.ts) so every tab of the browser talks to the
 * same mock, or in the page itself where SharedWorker is unavailable.
 */
import type { StructuredCommand } from '../api/agentTypes';
import type { AngleName, ConfirmBody, InspectBody, Person } from '../api/types';
import { MockBackend } from './backend';
import { MockDispatcher, isCommand } from './dispatch';
import { createCrewSample } from './crewSample';
import { buildMockTurnRecord } from './turnRecord';

const TICK_MS = 250;
const LATENCY_MS = 120;
/** Wall-clock time a mock (re-)inspection takes, so its progress state is visible. */
const REINSPECT_MS = 1800;
const MANUAL_INSPECT_MS = 2500;
/** How long the mock agent "thinks" before it answers free text. */
const AGENT_REPLY_MS = 900;

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export type MockServer = ReturnType<typeof createMockServer>;
export type MockMethod = keyof MockServer;

export function createMockServer(options: { startAt?: number } = {}) {
  const backend = new MockBackend({ startAt: options.startAt ?? 0 });
  const dispatcher = new MockDispatcher(backend);
  const withCrewSample = createCrewSample(backend);

  let last = Date.now();
  setInterval(() => {
    const now = Date.now();
    const dt = (now - last) / 1000;
    last = now;
    backend.tick(dt);
    dispatcher.tick(dt);
  }, TICK_MS);

  /** Run after a delay, let the dispatcher see what changed, and return a deep copy (as a network round trip would). */
  async function call<T>(fn: () => T, delay = LATENCY_MS): Promise<T> {
    await sleep(delay);
    try {
      return structuredClone(fn());
    } finally {
      dispatcher.step();
    }
  }

  async function command(token: string, text: string) {
    await sleep(LATENCY_MS);
    const pending = dispatcher.beginCommand(token, text);
    await sleep(pending.reinspects ? REINSPECT_MS : 0);
    return structuredClone(dispatcher.finishCommand(pending));
  }

  return {
    getState: () => call(() => backend.getState(), 30),
    getTurn: (turnId: string) => call(() => backend.getTurn(turnId), 60),
    getInspection: (id: string) => call(() => backend.getInspection(id), 60),
    confirmFinding: (id: string, findingId: string, body: ConfirmBody) => {
      const finding = backend.getInspection(id).findings.find((f) => f.finding_id === findingId);
      // "Removed" on an acknowledged HOLD runs a re-inspection, which takes a moment.
      const reinspects =
        finding?.severity === 'HOLD' && finding.status === 'acknowledged' && body.outcome === 'removed' && body.role === 'ramp_lead';
      return call(() => backend.confirmFinding(id, findingId, body), reinspects ? REINSPECT_MS : LATENCY_MS);
    },
    confirmAll: (id: string, who: Person) => call(() => backend.confirmAll(id, who)),
    reinspectAngle: (id: string, angle: AngleName, who: Person) => call(() => backend.reinspectAngle(id, angle, who), REINSPECT_MS),
    checkedByEye: (id: string, angle: AngleName, who: Person) => call(() => backend.checkedByEye(id, angle, who)),
    signoff: (id: string, who: Person) => call(() => backend.signoff(id, who)),
    inspectGate: async (gate: string, body: InspectBody) => {
      const report = await call(() => backend.inspectGate(gate, body));
      setTimeout(() => {
        backend.completeInspection(report.inspection_id);
        dispatcher.step();
      }, MANUAL_INSPECT_MS);
      return report;
    },
    demoPlay: () => call(() => backend.play()),
    demoPause: () => call(() => backend.pause()),
    demoReset: () => call(() => backend.reset()),
    demoSpeed: (speed: number) => call(() => backend.setSpeed(speed)),
    assistant: (inspectionId: string, message: string) => call(() => backend.assistant(inspectionId, message), 700),
    getRules: () => call(() => backend.getRules()),
    getTurnRecord: (turnId: string) => call(() => buildMockTurnRecord(backend, dispatcher, turnId), 60),

    agentRoster: () => call(() => dispatcher.roster(), 60),
    agentJoin: (personId: string, pin: string) => call(() => dispatcher.join(personId, pin)),
    agentInbox: (token: string, after: number) => call(() => dispatcher.inbox(token, after), 30),
    agentCommand: (token: string, c: StructuredCommand) => command(token, [`/${c.command.trim().replace(/^\//, '')}`, ...c.args.map(String)].join(' ')),
    agentCommandText: (token: string, text: string) => command(token, text),
    agentAnswer: (token: string, proposalId: string, accept: boolean) => command(token, `${accept ? 'y' : 'n'} ${proposalId}`),
    agentSay: async (token: string, text: string) => {
      const norm = text.split(/\s+/).filter(Boolean).join(' ');
      if (norm && norm.length <= 500 && isCommand(norm)) return { ...(await command(token, norm)), routed: 'command' as const };
      const out = await call(() => dispatcher.say(token, text));
      setTimeout(() => dispatcher.drainWakes(), AGENT_REPLY_MS);
      return out;
    },
    agentBoard: () => call(() => withCrewSample(dispatcher.board()), 60),
    agentActivity: (after: number, gate?: string, turnId?: string, limit?: number) =>
      call(() => dispatcher.activity({ after, gate, turn_id: turnId, limit }), 30),
  };
}
