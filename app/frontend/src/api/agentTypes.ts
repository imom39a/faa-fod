/**
 * Types for the always-on agent API (`/api/agent/*`), as served by
 * app/backend/fodgate/api.py and fodgate/dispatch/. Who is acting always comes
 * from the session token; nothing here carries a role chosen by the client.
 */
import type { AngleName, Severity } from './types';

export type PersonRole = 'ramp_agent' | 'ramp_lead' | 'supervisor';
export type ShiftStatus = 'on' | 'break' | 'off';

/** One roster row. A PIN never leaves the server. */
export type RosterPerson = {
  person_id: string;
  name: string;
  role: PersonRole;
  /** The Gates this person covers. */
  gates: string[];
  shift: ShiftStatus;
  /** True while their chat page has polled the inbox in the last few seconds. */
  signed_in: boolean;
};

export type RosterResponse = { people: RosterPerson[] };
export type JoinResponse = { token: string; person: RosterPerson };

export type TaskType = 'ack_hold' | 'remove' | 'walk_and_report' | 'check_by_eye' | 'report_outside_boundary' | 'sign_off';
/** `assigned`, `accepted` and `reported` are active; anything else is closed or cancelled. */
export type TaskStatus = 'assigned' | 'accepted' | 'reported' | 'closed' | 'cancelled';
export const ACTIVE_TASK_STATUSES: readonly TaskStatus[] = ['assigned', 'accepted', 'reported'];

export type Task = {
  /** "K-3". */
  task_id: string;
  type: TaskType;
  gate: string;
  turn_id: string;
  inspection_id: string;
  /** The Finding's short label ("F1"), not the raw Finding ID. Null for Angle and sign-off Tasks. */
  finding_id: string | null;
  /** The same Finding's raw ID in `inspection_id`, so a link can open it there. Optional: older servers omit it. */
  inspection_finding_id?: string | null;
  angle: AngleName | null;
  /** Copied from the Finding by code. Null for Angle and sign-off Tasks. */
  severity: Severity | null;
  required_role: 'ramp_lead' | 'any';
  assignee_id: string | null;
  instruction: string;
  status: TaskStatus | (string & {});
  /** `code`, `agent` or a person_id. */
  created_by: string;
  /** 0 = not escalated; 1 = second call; 2 = every Ramp Lead and the supervisor told. */
  escalation_level: number;
  created_at: string;
  closed_at: string | null;
  close_reason: string | null;
  closed_by_confirmation_id: number | null;
};

/** `code` = fixed wording from code, `agent` = written by the model, `timer` = a timer fired,
 *  `person` = free text typed by a person, `command` = a command a person typed or pressed. */
export type MessageKind = 'code' | 'agent' | 'timer' | 'person' | 'command';

export type ChatMessage = {
  message_id: number;
  /** A person_id, or `code` / `agent` / `timer`. */
  from: string;
  /** A person_id, or `agent` / `code` for what a person typed. */
  to: string;
  kind: MessageKind | (string & {});
  text: string;
  task_id: string | null;
  proposal_id: string | null;
  at: string;
  /** Demo clock seconds. */
  t: number;
};

export type ProposalKind = 'confirm' | 'reinspect' | 'handover';

/** A question only the addressed person can answer. Accepting it runs the action as that person. */
export type Proposal = {
  /** "P-2". */
  proposal_id: string;
  kind: ProposalKind | (string & {});
  /** "record F2 as removed". */
  question: string;
  action: {
    kind?: string;
    label?: string;
    outcome?: string;
    false_alarm_reason?: string | null;
    gate?: string;
    angle?: string;
    turn_id?: string;
    from_id?: string;
  };
  created_by: string;
  created_at: string;
  status: 'pending' | 'accepted' | 'declined' | 'expired' | 'void' | (string & {});
  /** Demo clock seconds. */
  expires_t: number;
  expires_in_s: number;
};

/** GET /agent/inbox?after=<cursor>. */
export type Inbox = {
  person: RosterPerson;
  /** Changes when the demo is reset: drop the thread and start again from 0. */
  epoch: number;
  clock_t: number;
  /** Pass as `after` on the next poll. */
  cursor: number;
  /** Messages to or from this person with an ID above `after`, oldest first. */
  messages: ChatMessage[];
  /** Active Tasks plus the last few closed ones (every Task for a supervisor). */
  tasks: Task[];
  pending_proposals: Proposal[];
};

/** POST /agent/command and POST /agent/proposals/{id}/answer. */
export type CommandResult = { ok: true; lines: string[] };

/** POST /agent/say. Text that is a command is run as one (`routed: "command"`). */
export type SayResult =
  | { ok: true; routed: 'agent'; message_id: number }
  | { ok: true; routed: 'command'; lines: string[] };

/** How the agent console groups an entry. */
export type ActivityConsoleKind = 'code' | 'wake' | 'agent' | 'timer' | 'cost' | 'idle' | 'person' | 'message';

export type ActivityEntry = {
  id: number;
  at: string;
  /** Demo clock seconds. */
  t: number;
  kind: ActivityConsoleKind | (string & {});
  /** What happened: `task_assigned`, `confirmation`, `agent_wake`, ... */
  event: string;
  gate: string | null;
  turn_id: string | null;
  /** `code`, `agent`, `timer`, a person_id, or (for a Confirmation) the person's name. */
  actor: string;
  text: string;
  data: Record<string, unknown>;
};

export type AgentCost = {
  agent_session_usd: number;
  wakes: number;
  tokens_in: number;
  tokens_out: number;
  model_requests: number;
  process_usd: number;
  cap_usd: number | null;
};

/** GET /agent/activity?after=<cursor>. Entries are oldest first. */
export type ActivityResponse = {
  epoch: number;
  cursor: number;
  entries: ActivityEntry[];
  cost: AgentCost;
};

export type ActivityQuery = { after?: number; gate?: string; turn_id?: string; limit?: number };

export type TaskReport = { by_person_id: string; at: string; kind: string; raw_text: string | null; via: string };

/** GET /agent/board: the read-only picture of the dispatcher. */
export type Board = {
  mode: string;
  model: string;
  model_available: boolean;
  model_note: string;
  clock_t: number;
  tasks: (Task & { reports: TaskReport[] })[];
  roster: (RosterPerson & { open_tasks: number })[];
  timers: { task_id: string | null; kind: string; fire_t: number }[];
  activity: ActivityEntry[];
  cost: AgentCost;
};

/** A command in its structured form: `{ command: "ack", args: ["F1"] }` runs `/ack F1`. */
export type CommandName =
  | 'ack'
  | 'removed'
  | 'false-alarm'
  | 'not-found'
  | 'reported'
  | 'all-removed'
  | 'reinspect'
  | 'eye'
  | 'signoff'
  | 'accept'
  | 'done'
  | 'cant'
  | 'reassign'
  | 'handover'
  | 'break'
  | 'back'
  | 'shift'
  | 'msg'
  | 'tasks'
  | 'who'
  | 'help';

export type StructuredCommand = { command: CommandName; args: (string | number)[] };

/** Every `/api/agent/*` endpoint. Calls that act as a person take that person's session token. */
export interface AgentApi {
  roster(): Promise<RosterResponse>;
  join(personId: string, pin: string): Promise<JoinResponse>;
  inbox(token: string, after?: number): Promise<Inbox>;
  /** The structured form, used by buttons. */
  command(token: string, command: StructuredCommand): Promise<CommandResult>;
  /** The typed form: "/ack F1", or "y" / "n". */
  commandText(token: string, text: string): Promise<CommandResult>;
  answerProposal(token: string, proposalId: string, accept: boolean): Promise<CommandResult>;
  /** Free text for the agent: a Report, never a Confirmation. */
  say(token: string, text: string): Promise<SayResult>;
  board(): Promise<Board>;
  activity(query?: ActivityQuery): Promise<ActivityResponse>;
}
