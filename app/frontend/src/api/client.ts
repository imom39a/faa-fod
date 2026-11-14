import type {
  ActivityResponse,
  AgentApi,
  Board,
  CommandResult,
  Inbox,
  JoinResponse,
  RosterResponse,
  SayResult,
} from './agentTypes';
import type {
  AngleName,
  ApiErrorCode,
  AssistantRequest,
  AssistantResponse,
  ConfirmBody,
  DemoSpeed,
  InspectBody,
  Person,
  Report,
  RuleSet,
  State,
  Turn,
} from './types';
import type { TurnRecord } from './turnRecordTypes';
import { normaliseTurnRecord } from '../lib/turnRecord';

/** A 4xx/5xx from the API (`{ error, message }`) or a transport failure. */
export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;

  constructor(code: ApiErrorCode, message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

/** Everything the dashboard asks of the backend. One method per contract row. */
export interface Api {
  getState(): Promise<State>;
  getTurn(turnId: string): Promise<Turn>;
  getInspection(inspectionId: string): Promise<Report>;
  /** href for the JSON export of a Report (GET /inspections/{id}/export). */
  exportHref(report: Report): string;
  confirmFinding(inspectionId: string, findingId: string, body: ConfirmBody): Promise<Report>;
  confirmAll(inspectionId: string, who: Person): Promise<Report>;
  reinspectAngle(inspectionId: string, angle: AngleName, who: Person): Promise<Report>;
  checkedByEye(inspectionId: string, angle: AngleName, who: Person): Promise<Report>;
  signoff(inspectionId: string, who: Person): Promise<Report>;
  inspectGate(gate: string, body: InspectBody): Promise<Report>;
  demoPlay(): Promise<State>;
  demoPause(): Promise<State>;
  demoReset(): Promise<State>;
  demoSpeed(speed: DemoSpeed): Promise<State>;
  assistant(body: AssistantRequest): Promise<AssistantResponse>;
  getRules(): Promise<RuleSet>;
  /** GET /turns/{turn_id}/record: the read-only Turn record. */
  getTurnRecord(turnId: string): Promise<TurnRecord>;
  /** The always-on agent: roster, sign-in, chat thread, commands, activity log. */
  agent: AgentApi;
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

const enc = encodeURIComponent;

/** Fill in list fields a partial Report might omit, so the UI never reads undefined. */
export function normaliseReport(r: Report): Report {
  return {
    ...r,
    missing_angles: r.missing_angles ?? [],
    angles: r.angles ?? [],
    findings: r.findings ?? [],
    dismissed_candidates: r.dismissed_candidates ?? [],
    observations: r.observations ?? [],
    inspection_signoff: r.inspection_signoff ?? null,
    run_metadata: {
      local_models: r.run_metadata?.local_models ?? [],
      llm_calls: r.run_metadata?.llm_calls ?? [],
      timings_ms: r.run_metadata?.timings_ms ?? {},
      notes: r.run_metadata?.notes,
    },
  };
}

function normaliseTurn(t: Turn): Turn {
  return { ...t, inspections: (t.inspections ?? []).map(normaliseReport), events: t.events ?? [] };
}

export function createHttpApi(base = '/api', fetchImpl: FetchLike = (i, init) => fetch(i, init)): Api {
  async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown, token?: string): Promise<T> {
    let res: Response;
    try {
      const headers: Record<string, string> = {};
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      // The session token says who is acting; the server looks the role up in the roster.
      if (token !== undefined) headers.Authorization = `Bearer ${token}`;
      res = await fetchImpl(base + path, {
        method,
        headers: Object.keys(headers).length > 0 ? headers : undefined,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError('network', 'The inspection service cannot be reached.', 0);
    }
    if (!res.ok) {
      let code: ApiErrorCode = res.status === 404 ? 'not_found' : `http_${res.status}`;
      let message = `Request failed (${res.status}).`;
      try {
        const data: unknown = await res.json();
        if (data && typeof data === 'object') {
          const d = data as { error?: unknown; message?: unknown };
          if (typeof d.error === 'string') code = d.error;
          if (typeof d.message === 'string') message = d.message;
        }
      } catch {
        // Not JSON (e.g. the proxy's 502 page when the backend is down).
        if (res.status >= 500) code = 'network';
      }
      throw new ApiError(code, message, res.status);
    }
    return (await res.json()) as T;
  }

  const get = <T>(path: string) => request<T>('GET', path);
  const post = <T>(path: string, body: unknown = {}) => request<T>('POST', path, body);
  const report = (p: Promise<Report>) => p.then(normaliseReport);

  const agent: AgentApi = {
    roster: () => get<RosterResponse>('/agent/roster'),
    join: (personId, pin) => post<JoinResponse>('/agent/join', { person_id: personId, pin }),
    inbox: (token, after = 0) => request<Inbox>('GET', `/agent/inbox?after=${enc(String(after))}`, undefined, token),
    command: (token, c) => request<CommandResult>('POST', '/agent/command', { command: c.command, args: c.args }, token),
    commandText: (token, text) => request<CommandResult>('POST', '/agent/command', { text }, token),
    answerProposal: (token, proposalId, accept) =>
      request<CommandResult>('POST', `/agent/proposals/${enc(proposalId)}/answer`, { accept }, token),
    say: (token, text) => request<SayResult>('POST', '/agent/say', { text }, token),
    board: () => get<Board>('/agent/board'),
    activity: (q = {}) => {
      const params = new URLSearchParams({ after: String(q.after ?? 0) });
      if (q.gate) params.set('gate', q.gate);
      if (q.turn_id) params.set('turn_id', q.turn_id);
      if (q.limit) params.set('limit', String(q.limit));
      return get<ActivityResponse>(`/agent/activity?${params.toString()}`);
    },
  };

  return {
    getState: () => get<State>('/state'),
    getTurn: (turnId) => get<Turn>(`/turns/${enc(turnId)}`).then(normaliseTurn),
    getInspection: (id) => report(get<Report>(`/inspections/${enc(id)}`)),
    exportHref: (r) => `${base}/inspections/${enc(r.inspection_id)}/export`,
    confirmFinding: (id, findingId, body) =>
      report(post<Report>(`/inspections/${enc(id)}/findings/${enc(findingId)}/confirm`, body)),
    confirmAll: (id, who) => report(post<Report>(`/inspections/${enc(id)}/findings/confirm-all`, who)),
    reinspectAngle: (id, angle, who) =>
      report(post<Report>(`/inspections/${enc(id)}/angles/${enc(angle)}/reinspect`, who)),
    checkedByEye: (id, angle, who) =>
      report(post<Report>(`/inspections/${enc(id)}/angles/${enc(angle)}/checked-by-eye`, who)),
    signoff: (id, who) => report(post<Report>(`/inspections/${enc(id)}/signoff`, who)),
    inspectGate: (gate, body) => report(post<Report>(`/gates/${enc(gate)}/inspect`, body)),
    demoPlay: () => post<State>('/demo/play'),
    demoPause: () => post<State>('/demo/pause'),
    demoReset: () => post<State>('/demo/reset'),
    demoSpeed: (speed) => post<State>('/demo/speed', { speed }),
    assistant: (body) => post<AssistantResponse>('/assistant', body),
    getRules: () => get<RuleSet>('/rules'),
    getTurnRecord: (turnId) => get<unknown>(`/turns/${enc(turnId)}/record`).then((r) => normaliseTurnRecord(r, turnId)),
    agent,
  };
}
