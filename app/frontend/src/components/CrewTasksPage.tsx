import type { ActivityEntry, AgentApi, Board } from '../api/agentTypes';
import type { Severity } from '../api/types';
import { MOCK_MODE } from '../api';
import { describeAgentError } from '../api/errors';
import { CATEGORY_LABEL, activityCategory, actorLabel, entryInspectionId, entryText } from '../lib/activity';
import {
  assigneeLabel,
  crewEscalationLabel,
  crewStatusLabel,
  escalationsInProgress,
  escalationLevelLabel,
  escalationWho,
  groupRoster,
  nextTimerIn,
  openFor,
  openTasks,
  recentActivity,
  recentlyClosedTasks,
  taskDetail,
  taskHref,
  taskInstruction,
  taskTarget,
  taskTypeInfo,
  type BoardPerson,
  type BoardTask,
} from '../lib/crewTasks';
import { formatClock, formatTime, formatUsd, plural } from '../lib/format';
import { useDeveloperMode } from '../store/settings';
import { personRoleLabel, SHIFT_LABEL } from '../lib/labels';
import { isAbnormal, severityTone } from '../lib/gates';
import { isActiveTask } from '../lib/taskActions';
import { activityHref, turnHref } from '../route';
import { useBoard } from '../store/boardStore';
import { SeverityBadge } from './bits';
import { ActivityCategoryIcon } from './ActivityCategoryIcon';
import { AgentIcon, ArrowRightIcon, CheckCircleIcon, EscalationIcon, SpinnerIcon, TaskIcon, UserIcon } from './icons';
import '../crew-tasks.css';

const KNOWN_SEVERITY: readonly string[] = ['HOLD', 'REMOVE', 'ADVISORY'];
const ACTIVITY_SHOWN = 15;
/** Mock mode's sample Board (src/mock/crewSample.ts) marks its Tasks this way. */
const isSample = (t: Pick<BoardTask, 'created_by'>) => t.created_by === 'sample';

/**
 * Crew and Tasks: who is on shift, every open Task, Escalations in progress,
 * recent agent activity and the session cost, from GET /api/agent/board.
 * Read-only: it offers links, never an action.
 */
export function CrewTasksPage({ agent }: { agent: Pick<AgentApi, 'board'> }) {
  const developer = useDeveloperMode();
  const { board, receivedAt, error } = useBoard(agent);

  return (
    <div className="crew" data-page="crew-tasks">
      <div className="turn-head">
        <h2 className="page-title">Crew and Tasks</h2>
        <span className="muted small">
          Read-only · updates every second
          {receivedAt ? ` · last update ${formatTime(new Date(receivedAt).toISOString())}` : ''}
        </span>
        <span className="spacer" />
        <a className="btn compact quiet" href={activityHref()}>
          Full activity log <ArrowRightIcon className="vicon" />
        </a>
      </div>
      {developer && MOCK_MODE ? (
        <p className="small muted crew-note">Mock mode: no model is called; cost and token figures are illustrative.</p>
      ) : null}
      {error ? (
        <div className="banner error" role="alert">
          <span className="grow">
            <strong>Not connected</strong>
            {describeAgentError(error)}
            {board ? ' Showing the last board received.' : ''}
          </span>
        </div>
      ) : null}
      {board ? (
        <CrewBoard board={board} now={receivedAt} />
      ) : !error ? (
        <p className="muted row" role="status">
          <SpinnerIcon className="vicon" /> Loading Crew and Tasks…
        </p>
      ) : null}
    </div>
  );
}

function CrewBoard({ board, now }: { board: Board; now: number }) {
  const developer = useDeveloperMode();
  const open = openTasks(board.tasks);
  const escalated = escalationsInProgress(board.tasks).length;
  const closed = recentlyClosedTasks(board.tasks);
  const holds = open.filter((t) => t.severity === 'HOLD').length;
  const sample = board.tasks.some(isSample);

  return (
    <>
      {sample ? (
        <p className="small muted crew-note" role="note">
          <span className="crew-sample">Sample</span> Sample Tasks and activity, shown until the demo creates a Task. Sample Tasks do not
          open a Turn. Press Play for live Tasks that open their Turn and Finding.
        </p>
      ) : null}
      <div className="crew-layout">
        <div className="crew-main">
          <section className="panel crew-section" aria-labelledby="crew-open-h">
            <h3 id="crew-open-h" className="crew-h">
              <TaskIcon className="vicon" /> Open Tasks <span className="crew-count">{open.length}</span>
              {holds > 0 ? <span className="crew-sub">{plural(holds, 'HOLD')}</span> : null}
              {escalated > 0 ? <span className="crew-sub">{escalated} escalated</span> : null}
            </h3>
            {open.length === 0 ? (
              <p className="muted crew-empty">No open Tasks.</p>
            ) : (
              <TaskTable label="Open Tasks" tasks={open} board={board} now={now} />
            )}
          </section>

          {closed.length > 0 ? (
            <details className="panel crew-section crew-closed">
              <summary className="crew-h">
                <CheckCircleIcon className="vicon" /> Recently closed <span className="crew-count">{closed.length}</span>
              </summary>
              <TaskTable label="Recently closed Tasks" tasks={closed} board={board} now={now} />
            </details>
          ) : null}
        </div>

        <div className="crew-side">
          <RosterSection roster={board.roster} />
          {developer && <CostSection board={board} />}
          <ActivitySection entries={board.activity} roster={board.roster} />
        </div>
      </div>
    </>
  );
}

/**
 * Tasks as rows, most urgent first (spec/design-system.md: "Prefer a table or rows to a
 * grid of cards"). A HOLD or REMOVE row has its severity colour as a bar on the left edge
 * and a severity badge; an escalated Task shows the double-chevron icon and its level in
 * the status column. Neither relies on colour alone.
 */
function TaskTable({ label, tasks, board, now }: { label: string; tasks: BoardTask[]; board: Board; now: number }) {
  return (
    <div className="crew-table" role="table" aria-label={label}>
      <div className="crew-row crew-row-head" role="row">
        <span role="columnheader">Gate</span>
        <span role="columnheader">Task</span>
        <span role="columnheader">Severity</span>
        <span role="columnheader">Assigned to · status</span>
        <span role="columnheader" className="r">
          Open
        </span>
      </div>
      {tasks.map((t) => (
        <TaskRow key={t.task_id} task={t} board={board} now={now} />
      ))}
    </div>
  );
}

function TaskRow({ task, board, now }: { task: BoardTask; board: Board; now: number }) {
  const info = taskTypeInfo(task);
  const instruction = taskInstruction(task);
  const detail = taskDetail(instruction);
  const active = isActiveTask(task);
  const hold = task.severity === 'HOLD';
  const escalation = active ? crewEscalationLabel(task.escalation_level) : null;
  const level = active ? escalationLevelLabel(task.escalation_level) : null;
  const next = level ? nextTimerIn(task.task_id, board.timers, board.clock_t) : null;
  const status = crewStatusLabel(task);
  const assignee = assigneeLabel(task.assignee_id, board.roster);
  const target = taskTarget(task);
  const age = active ? openFor(task.created_at, now) : '';
  const severity = task.severity && KNOWN_SEVERITY.includes(task.severity) ? (task.severity as Severity) : null;
  const tone = severity ? severityTone(severity) : null;
  const cls = [
    'crew-row',
    tone ? `tone-${tone}` : '',
    tone && isAbnormal(tone) ? 'is-abnormal' : '',
    hold ? 'is-hold' : '',
    escalation ? 'is-escalated' : '',
    active ? '' : 'is-closed',
    info.known ? '' : 'is-unknown-type',
  ]
    .filter(Boolean)
    .join(' ');
  const name = [
    isSample(task) ? 'Sample' : null,
    `${task.task_id}: ${info.label}`,
    hold ? 'HOLD' : task.severity,
    escalation,
    `Gate ${task.gate}`,
    target,
    `assigned to ${assignee}`,
    status,
    age ? `open for ${age}` : null,
  ]
    .filter(Boolean)
    .join(', ');
  const badge = severity ? <SeverityBadge severity={severity} /> : task.severity ? <span className="tag">{task.severity}</span> : null;

  return (
    <TaskLink
      task={task}
      name={name}
      className={cls}
      data={{
        'data-task-id': task.task_id,
        'data-task-type': info.raw,
        'data-severity': task.severity ?? '',
        'data-escalation-level': String(task.escalation_level),
        'data-status': task.status,
      }}
    >
      <span role="cell" className="crew-cell-gate">
        {task.gate}
      </span>
      <span role="cell" className="crew-cell-task">
        <span className="crew-task-type">
          <b
            className={info.known ? undefined : 'mono'}
            title={info.known ? undefined : 'A Task type this dashboard does not know yet. Shown as the server names it.'}
          >
            {info.label}
          </b>
          {isSample(task) ? <span className="crew-sample">Sample</span> : null}
          <span className="crew-sev-inline">{badge}</span>
        </span>
        <span className="crew-task-detail" title={instruction || undefined}>
          <b>{target}</b>
          {detail ? ` · ${detail}` : ''}
        </span>
      </span>
      <span role="cell" className="crew-cell-sev">
        {badge ?? <span className="muted">–</span>}
      </span>
      <span role="cell" className="crew-cell-status">
        <span className="crew-who">{assignee}</span>
        <span className="crew-status-line">
          <span>{status}</span>
          {level ? (
            <span className="crew-esc-line" title={escalationWho(task.escalation_level)}>
              <EscalationIcon className="vicon" /> {level}
              {next !== null ? <span className="muted num"> · next {formatClock(next)}</span> : null}
            </span>
          ) : null}
        </span>
      </span>
      <span role="cell" className="crew-cell-age r num">
        {age || '–'}
      </span>
    </TaskLink>
  );
}

/**
 * A real Task links to its Turn and Finding. A mock sample Task is a plain
 * row: at page load the mock has no Inspection that holds its Finding, so a
 * link would open a Turn that says something else.
 */
function TaskLink({
  task,
  name,
  className,
  data,
  children,
}: {
  task: BoardTask;
  name: string;
  className: string;
  data: Record<string, string>;
  children: React.ReactNode;
}) {
  if (isSample(task)) {
    return (
      <div role="row" className={`${className} is-sample`} aria-label={`${name}. Sample Task: no Turn to open.`} {...data}>
        {children}
      </div>
    );
  }
  return (
    <a role="row" className={className} href={taskHref(task)} aria-label={`${name}. Open the Turn and Finding.`} {...data}>
      {children}
    </a>
  );
}

function RosterSection({ roster }: { roster: BoardPerson[] }) {
  const { onShift, onBreak, offShift } = groupRoster(roster);
  return (
    <section className="panel crew-section" aria-labelledby="crew-roster-h">
      <h3 id="crew-roster-h" className="crew-h">
        <UserIcon className="vicon" /> Roster
      </h3>
      {roster.length === 0 ? (
        <p className="muted crew-empty">No one is on the Roster.</p>
      ) : (
        <>
          <PeopleGroup title={SHIFT_LABEL.on} people={onShift} empty="No one is on shift." />
          <PeopleGroup title={SHIFT_LABEL.break} people={onBreak} empty="No one is on a break." />
          {offShift.length > 0 ? <PeopleGroup title={SHIFT_LABEL.off} people={offShift} empty="" /> : null}
        </>
      )}
    </section>
  );
}

function PeopleGroup({ title, people, empty }: { title: string; people: BoardPerson[]; empty: string }) {
  return (
    <div className="crew-people-group">
      <h4 className="crew-h4">
        {title} <span className="crew-count">{people.length}</span>
      </h4>
      {people.length === 0 ? (
        <p className="small muted">{empty}</p>
      ) : (
        <ul className="crew-people" aria-label={title}>
          {people.map((p) => (
            <li key={p.person_id} className={`crew-person shift-${p.shift}`} data-person-id={p.person_id} data-shift={p.shift}>
              <span className="crew-person-name">{p.name}</span>
              <span className="crew-person-role">{personRoleLabel(p.role)}</span>
              <span className="crew-person-gates">Gates {p.gates.length ? p.gates.join(', ') : 'none'}</span>
              <span className="crew-person-load small muted">
                {plural(p.open_tasks, 'open Task')}
                {p.signed_in ? ' · in the chat' : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CostSection({ board }: { board: Board }) {
  const cost = board.cost;
  return (
    <section className="panel crew-section" aria-labelledby="crew-cost-h">
      <h3 id="crew-cost-h" className="crew-h">
        Session cost
      </h3>
      <div className="stat-row cost-row" aria-label="Agent session cost">
        <div className="stat">
          <b className="num">{formatUsd(cost.agent_session_usd)}</b>
          <span>Agent session</span>
        </div>
        <div className="stat">
          <b className="num">{cost.wakes}</b>
          <span>Agent wakes</span>
        </div>
        <div className="stat">
          <b className="num">
            {cost.tokens_in.toLocaleString()} / {cost.tokens_out.toLocaleString()}
          </b>
          <span>Tokens in / out</span>
        </div>
        <div className="stat">
          <b className="num">
            {formatUsd(cost.process_usd)}
            {cost.cap_usd !== null ? ` of ${formatUsd(cost.cap_usd)}` : ''}
          </b>
          <span>{cost.cap_usd !== null ? 'Process spend of cap' : 'Process spend'}</span>
        </div>
      </div>
      {board.model_note ? <p className="small muted">{board.model_note}</p> : null}
    </section>
  );
}

function ActivitySection({ entries, roster }: { entries: ActivityEntry[]; roster: BoardPerson[] }) {
  const shown = recentActivity(entries, ACTIVITY_SHOWN);
  return (
    <section className="panel crew-section" aria-labelledby="crew-act-h">
      <h3 id="crew-act-h" className="crew-h">
        <AgentIcon className="vicon" /> Recent agent activity
      </h3>
      {shown.length === 0 ? (
        <p className="muted crew-empty">Nothing has happened yet.</p>
      ) : (
        <ol className="crew-activity" aria-label="Recent agent activity, newest first">
          {shown.map((e) => {
            const cat = activityCategory(e);
            return (
              <li key={e.id} className={`crew-act cat-${cat}`} data-event={e.event}>
                <span className="crew-act-time num">{formatTime(e.at)}</span>
                <span className={`kind-tag cat-${cat}`}>
                  <ActivityCategoryIcon category={cat} />
                  {CATEGORY_LABEL[cat]}
                </span>
                <span className="crew-act-text">
                  {e.turn_id && e.data?.sample !== true ? (
                    <a href={turnHref(e.turn_id, entryInspectionId(e))} className="gate-chip" title={`Turn ${e.turn_id}`}>
                      {e.gate ?? e.turn_id}
                    </a>
                  ) : e.gate ? (
                    <span className="gate-chip">{e.gate}</span>
                  ) : null}{' '}
                  <span className="muted">{actorLabel(e.actor, roster)}:</span> {entryText(e)}
                  {e.data?.sample === true ? <span className="crew-sample">Sample</span> : null}
                </span>
              </li>
            );
          })}
        </ol>
      )}
      <a className="crew-more" href={activityHref()}>
        Full activity log <ArrowRightIcon className="vicon" />
      </a>
    </section>
  );
}
