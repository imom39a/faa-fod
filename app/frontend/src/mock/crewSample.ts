/**
 * Sample data for the Crew and Tasks page in mock mode (issue #2, AC8).
 *
 * At page load the mock demo has not run yet: the dispatcher has a Roster but
 * no Task, so the page would be mostly empty. While the dispatcher has no Task
 * of its own, the mock Board gets a small marked sample instead: a Ramp Agent
 * on a break, open Tasks of several types (one an escalated HOLD, one a removal
 * the agent escalated, one a Task type this dashboard does not know), a closed Task, a short activity log and
 * an illustrative cost. As soon as the demo creates a real Task, the Board is
 * the dispatcher's own again, unchanged.
 *
 * Only the Board is decorated. Nothing is added to the dispatcher, so the chat
 * page, the activity log and the Turn record never see the sample. Every
 * sample Task has `created_by: 'sample'` and every sample activity entry has
 * `data.sample: true`, so the page can mark them.
 */
import type { ActivityEntry, Board, RosterPerson, Task, TaskReport, TaskType } from '../api/agentTypes';
import type { MockBackend } from './backend';

/** `created_by` of every sample Task. */
export const SAMPLE_CREATOR = 'sample';
/** A Task type no ticket has added yet: the page must show it by name. */
export const SAMPLE_UNKNOWN_TYPE = 'future_type_example';

type BoardTask = Board['tasks'][number];
type BoardPerson = Board['roster'][number];

/** The Turns the sample Tasks point at: the mock Turns already inspected when the demo starts. */
const SAMPLE_TURNS = { T2: 'T2-DL2210', T5: 'T5-DL1776', T8: 'T8-DL1907' } as const;

const SAMPLE_PERSON: RosterPerson = {
  person_id: 'sample-lee',
  name: 'Lee (sample)',
  role: 'ramp_agent',
  gates: ['T5', 'T8'],
  shift: 'break',
  signed_in: false,
};

/**
 * Returns a function that adds the sample to a Board while the Board has no
 * Task. Sample Tasks are not links: at page load no mock Inspection holds
 * their Findings, so the page shows them as plain rows.
 * Times are fixed when this is called, so "open for" grows as on a live Board.
 */
export function createCrewSample(backend: Pick<MockBackend, 'getTurn'>, now = Date.now()) {
  const ago = (s: number) => new Date(now - s * 1000).toISOString();
  const latestInspection = (turnId: string): string | null => {
    try {
      return backend.getTurn(turnId).inspections.at(-1)?.inspection_id ?? null;
    } catch {
      return null;
    }
  };

  return function withCrewSample(board: Board): Board {
    if (board.tasks.length > 0) return board;
    const tasks = sampleTasks(latestInspection, ago);
    const people: BoardPerson[] = [...board.roster, { ...SAMPLE_PERSON, gates: [...SAMPLE_PERSON.gates], open_tasks: 0 }];
    const roster = people.map((p) => ({
      ...p,
      open_tasks: p.open_tasks + tasks.filter((t) => t.assignee_id === p.person_id && t.status !== 'closed').length,
    }));
    const t = board.clock_t;
    const timers = [
      // S-3 was assigned 40 s ago; the no-Report ladder asks at 60 s and offers reassignment at 120 s.
      { task_id: 'S-3', kind: 'no_report_ask', fire_t: t + 20 },
      { task_id: 'S-3', kind: 'no_report_offer', fire_t: t + 80 },
    ];
    const cost =
      board.cost.agent_session_usd > 0
        ? board.cost
        : { ...board.cost, agent_session_usd: 0.0061, wakes: 2, tokens_in: 4210, tokens_out: 388, process_usd: 0.0061 };
    return { ...board, tasks, roster, timers: [...board.timers, ...timers], activity: [...sampleActivity(ago, t), ...board.activity], cost };
  };
}

function sampleTasks(latestInspection: (turnId: string) => string | null, ago: (s: number) => string): BoardTask[] {
  const base = (turnId: string, gate: string): Pick<Task, 'turn_id' | 'gate' | 'inspection_id' | 'created_by' | 'closed_at' | 'close_reason' | 'closed_by_confirmation_id'> => ({
    turn_id: turnId,
    gate,
    inspection_id: latestInspection(turnId) ?? '',
    created_by: SAMPLE_CREATOR,
    closed_at: null,
    close_reason: null,
    closed_by_confirmation_id: null,
  });
  const report = (by: string, s: number, kind: string, via: string, raw: string | null = null): TaskReport => ({
    by_person_id: by,
    at: ago(s),
    kind,
    raw_text: raw,
    via,
  });
  return [
    {
      ...base(SAMPLE_TURNS.T5, 'T5'),
      task_id: 'S-1',
      type: 'ack_hold',
      finding_id: 'F1',
      inspection_finding_id: null,
      angle: 'ENG-R',
      severity: 'HOLD',
      required_role: 'ramp_lead',
      assignee_id: 'okafor',
      instruction: 'Acknowledge the HOLD at T5 ENG-R: a hammer near the right engine intake. Nothing moves until a Ramp Lead clears it.',
      status: 'assigned',
      escalation_level: 2,
      created_at: ago(75),
      reports: [],
    },
    {
      ...base(SAMPLE_TURNS.T8, 'T8'),
      task_id: 'S-2',
      type: 'remove',
      finding_id: 'F2',
      inspection_finding_id: null,
      angle: 'CARGO',
      severity: 'REMOVE',
      required_role: 'any',
      assignee_id: 'kim',
      instruction: 'Remove the bag tag by the belt loader at T8 CARGO and report back.',
      status: 'accepted',
      escalation_level: 1,
      created_at: ago(190),
      reports: [report('kim', 170, 'accepted', 'command')],
    },
    {
      ...base(SAMPLE_TURNS.T8, 'T8'),
      task_id: 'S-3',
      // A type added by a later ticket: the page shows its name and instruction.
      type: SAMPLE_UNKNOWN_TYPE as TaskType,
      finding_id: null,
      inspection_finding_id: null,
      angle: null,
      severity: null,
      required_role: 'any',
      assignee_id: 'kim',
      instruction: 'Example of a Task type that a later ticket adds. The page shows its name and this instruction.',
      status: 'assigned',
      escalation_level: 0,
      created_at: ago(40),
      reports: [],
    },
    {
      ...base(SAMPLE_TURNS.T2, 'T2'),
      task_id: 'S-4',
      type: 'check_by_eye',
      finding_id: null,
      inspection_finding_id: null,
      angle: 'NOSE',
      severity: null,
      // check_by_eye is Ramp Lead only (LEAD_ONLY): Reyes is the Ramp Lead for T2.
      required_role: 'ramp_lead',
      assignee_id: 'reyes',
      instruction: 'Check the NOSE Angle at T2 by eye: its photo is unusable.',
      status: 'accepted',
      escalation_level: 0,
      created_at: ago(130),
      reports: [report('reyes', 110, 'accepted', 'command')],
    },
    {
      // A finished removal next to the open one (S-2): a closed sign-off would contradict the open Tasks.
      ...base(SAMPLE_TURNS.T8, 'T8'),
      task_id: 'S-5',
      type: 'remove',
      finding_id: 'F3',
      inspection_finding_id: null,
      angle: 'WIDE',
      severity: 'ADVISORY',
      required_role: 'any',
      assignee_id: 'kim',
      instruction: 'Remove the plastic wrap near the stand edge at T8 WIDE and report back.',
      status: 'closed',
      escalation_level: 0,
      created_at: ago(260),
      closed_at: ago(230),
      close_reason: 'Finding confirmed removed',
      reports: [report('kim', 240, 'done', 'command')],
    },
  ];
}

/** Oldest first, as on the Board. Negative ids keep them below any real entry. */
function sampleActivity(ago: (s: number) => string, t: number): ActivityEntry[] {
  const rows: [number, string, string, string | null, string | null, string, string, Record<string, unknown>][] = [
    [190, 'code', 'task_assigned', 'T8', SAMPLE_TURNS.T8, 'code', 'S-2 remove F2 -> Kim (Ramp Agent).', { task_id: 'S-2' }],
    [170, 'code', 'task_accepted', 'T8', SAMPLE_TURNS.T8, 'kim', 'Report on S-2 by Kim: accepted (command). Finding F2 stays open.', { task_id: 'S-2', kind: 'accepted', via: 'command' }],
    [130, 'timer', 'timer_fired', 'T8', SAMPLE_TURNS.T8, 'timer', 'S-2 has no Report after 60 s. Asked Kim.', { task_id: 'S-2', timer: 'no_report_ask' }],
    [130, 'code', 'task_assigned', 'T2', SAMPLE_TURNS.T2, 'code', 'S-4 check by eye NOSE -> Reyes (Ramp Lead).', { task_id: 'S-4' }],
    [110, 'code', 'task_accepted', 'T2', SAMPLE_TURNS.T2, 'reyes', 'Report on S-4 by Reyes: accepted (command).', { task_id: 'S-4', kind: 'accepted', via: 'command' }],
    [75, 'code', 'task_assigned', 'T5', SAMPLE_TURNS.T5, 'code', 'S-1 acknowledge HOLD F1 -> Okafor (Ramp Lead).', { task_id: 'S-1' }],
    // S-4 was assigned 130 s ago; accepting does not cancel the no-Report timers, so both have fired.
    [70, 'timer', 'timer_fired', 'T2', SAMPLE_TURNS.T2, 'timer', 'S-4 has no Report after 60 s. Asked Reyes.', { task_id: 'S-4', timer: 'no_report_ask' }],
    [70, 'timer', 'timer_fired', 'T8', SAMPLE_TURNS.T8, 'timer', 'S-2 still has no Report after 120 s. Offered reassignment to Okafor.', { task_id: 'S-2', timer: 'no_report_offer' }],
    // A no-Report timer only asks and offers reassignment. A Task other than a HOLD is escalated by the agent's escalate tool.
    [56, 'person', 'message', 'T8', SAMPLE_TURNS.T8, 'okafor', 'okafor> Kim is still on the belt loader. Push S-2 up.', { from: 'okafor', to: 'agent', kind: 'person', task_id: 'S-2' }],
    [54, 'agent', 'agent_tool', 'T8', SAMPLE_TURNS.T8, 'agent', 'escalate(S-2, "Okafor asks: no Report from Kim after the reassignment offer")  [code: ok, level 1]', { tool: 'escalate', ok: true }],
    [54, 'code', 'task_escalated', 'T8', SAMPLE_TURNS.T8, 'agent', 'S-2 : Okafor asks: no Report from Kim after the reassignment offer. Escalation level 1. Told: kim, dana.', { task_id: 'S-2', level: 1, notified: ['kim', 'dana'] }],
    [52, 'cost', 'agent_wake', 'T8', SAMPLE_TURNS.T8, 'agent', 'Agent wake: 1 tool call, $0.0027 (illustrative).', { trigger: 'human_message', est_cost_usd: 0.0027 }],
    [45, 'timer', 'task_escalated', 'T5', SAMPLE_TURNS.T5, 'timer', 'S-1 HOLD F1 at T5 ENG-R: not acknowledged after 30 s. Escalation level 1. Told: okafor, dana.', { task_id: 'S-1', level: 1, notified: ['okafor', 'dana'] }],
    [40, 'agent', 'agent_tool', 'T8', SAMPLE_TURNS.T8, 'agent', `assign_task(S-3 "${SAMPLE_UNKNOWN_TYPE}", to=kim)  [code: ok, role ramp_agent]`, { tool: 'assign_task', ok: true }],
    [38, 'cost', 'agent_wake', 'T8', SAMPLE_TURNS.T8, 'agent', 'Agent wake: 1 tool call, $0.0034 (illustrative).', { est_cost_usd: 0.0034 }],
    [15, 'timer', 'task_escalated', 'T5', SAMPLE_TURNS.T5, 'timer', 'S-1 HOLD F1 at T5 ENG-R: not acknowledged after 60 s. Escalation level 2. Told: okafor, reyes, dana.', { task_id: 'S-1', level: 2, notified: ['okafor', 'reyes', 'dana'] }],
    [10, 'timer', 'timer_fired', 'T2', SAMPLE_TURNS.T2, 'timer', 'S-4 still has no Report after 120 s. Offered reassignment to Okafor.', { task_id: 'S-4', timer: 'no_report_offer' }],
  ];
  return rows.map(([s, kind, event, gate, turnId, actor, text, data], i) => ({
    id: i - rows.length,
    at: ago(s),
    t: Math.round((t - s) * 10) / 10,
    kind,
    event,
    gate,
    turn_id: turnId,
    actor,
    text,
    data: { ...data, sample: true },
  }));
}
