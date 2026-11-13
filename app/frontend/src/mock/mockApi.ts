import type { Api } from '../api/client';
import type { Report } from '../api/types';
import { MockBackend } from './backend';

const TICK_MS = 250;
const LATENCY_MS = 120;
/** Wall-clock time a mock (re-)inspection takes, so its progress state is visible. */
const REINSPECT_MS = 1800;
const MANUAL_INSPECT_MS = 2500;

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** `?t=120` starts the mock demo clock at 120 s (mock mode only; handy for demos and tests). */
function startAtFromUrl(): number {
  if (typeof window === 'undefined') return 0;
  const t = Number(new URLSearchParams(window.location.search).get('t'));
  return Number.isFinite(t) && t > 0 ? t : 0;
}

/**
 * The contract API served in-browser from fixture data. Each call is delayed a
 * little and returns a deep copy, as a network round trip would.
 */
export function createMockApi(backend = new MockBackend({ startAt: startAtFromUrl() })): Api {
  let last = Date.now();
  setInterval(() => {
    const now = Date.now();
    backend.tick((now - last) / 1000);
    last = now;
  }, TICK_MS);

  async function call<T>(fn: () => T, delay = LATENCY_MS): Promise<T> {
    await sleep(delay);
    return structuredClone(fn());
  }

  return {
    getState: () => call(() => backend.getState(), 30),
    getTurn: (turnId) => call(() => backend.getTurn(turnId), 60),
    getInspection: (id) => call(() => backend.getInspection(id), 60),
    exportHref: (report: Report) =>
      `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(report, null, 2))}`,
    confirmFinding: (id, findingId, body) => {
      const finding = backend.getInspection(id).findings.find((f) => f.finding_id === findingId);
      // "Removed" on an acknowledged HOLD runs a re-inspection, which takes a moment.
      const reinspects =
        finding?.severity === 'HOLD' && finding.status === 'acknowledged' && body.outcome === 'removed' && body.role === 'ramp_lead';
      return call(() => backend.confirmFinding(id, findingId, body), reinspects ? REINSPECT_MS : LATENCY_MS);
    },
    confirmAll: (id, who) => call(() => backend.confirmAll(id, who)),
    reportNotFound: (id, findingId, who) => call(() => backend.reportNotFound(id, findingId, who)),
    answerProposal: (id, proposalId, accept, who) => {
      // Accepting a re-inspection Proposal runs a re-inspection, which takes a moment.
      const reinspects = accept && backend.getInspection(id).proposals?.find((p) => p.proposal_id === proposalId)?.kind === 'reinspect_angle';
      return call(() => backend.answerProposal(id, proposalId, accept, who), reinspects ? REINSPECT_MS : LATENCY_MS);
    },
    reinspectAngle: (id, angle, who) => call(() => backend.reinspectAngle(id, angle, who), REINSPECT_MS),
    checkedByEye: (id, angle, who) => call(() => backend.checkedByEye(id, angle, who)),
    signoff: (id, who) => call(() => backend.signoff(id, who)),
    inspectGate: async (gate, body) => {
      const report = await call(() => backend.inspectGate(gate, body));
      setTimeout(() => backend.completeInspection(report.inspection_id), MANUAL_INSPECT_MS);
      return report;
    },
    demoPlay: () => call(() => backend.play()),
    demoPause: () => call(() => backend.pause()),
    demoReset: () => call(() => backend.reset()),
    demoSpeed: (speed) => call(() => backend.setSpeed(speed)),
    assistant: (body) => call(() => backend.assistant(body.inspection_id, body.message), 700),
    getRules: () => call(() => backend.getRules()),
  };
}
