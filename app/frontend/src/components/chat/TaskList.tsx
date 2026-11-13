import { useState } from 'react';
import type { RosterPerson, StructuredCommand, Task } from '../../api/agentTypes';
import { FALSE_ALARM_REASONS, PERSON_ROLE_LABEL } from '../../lib/labels';
import {
  actionCommand,
  escalationLabel,
  formatAge,
  isActiveTask,
  sortTasks,
  taskActions,
  taskStatusLabel,
  TASK_TYPE_LABEL,
  type ActionGroup,
  type ActionInput,
  type TaskAction,
  type Viewer,
} from '../../lib/taskActions';
import { turnHref } from '../../route';
import { SeverityBadge } from '../bits';
import { ArrowRightIcon, CheckCircleIcon, ClockIcon, CrossIcon, EscalationIcon, HoldIcon, PenIcon, ReportIcon, SpinnerIcon, TaskIcon } from '../icons';

/** Sends one structured command; `key` names the button so it can show progress. */
export type RunCommand = (key: string, command: StructuredCommand, meta?: { reinspects?: boolean; task?: Task }) => void;

type CommonProps = {
  viewer: Viewer;
  roster: RosterPerson[];
  /** Key of the action being sent, if any. Everything is disabled while one is in flight. */
  busy: string | null;
  run: RunCommand;
};

const GROUP_TITLE: Record<ActionGroup, string> = {
  confirmation: 'Record on the Inspection (a Confirmation, in your name)',
  report: 'Report to the agent (not a Confirmation)',
  photo: 'New photo (records nothing)',
  routing: 'Routing',
};
const GROUP_ORDER: ActionGroup[] = ['confirmation', 'report', 'photo', 'routing'];

export const actionKey = (task: Task, action: TaskAction) => `${task.task_id}:${action.id}`;

function buttonClass(a: TaskAction): string {
  if (a.primary) return a.group === 'confirmation' ? 'good' : 'primary';
  return '';
}

/** Every action the viewer's role is offered on a Task, grouped so a Report cannot be mistaken for a Confirmation. */
export function TaskActions({ task, viewer, roster, busy, run }: CommonProps & { task: Task }) {
  const [open, setOpen] = useState<TaskAction | null>(null);
  const [note, setNote] = useState('');
  const [personId, setPersonId] = useState('');
  const actions = taskActions(task, viewer);
  if (actions.length === 0) return null;

  const send = (a: TaskAction, input: ActionInput = {}) => {
    run(actionKey(task, a), actionCommand(a.id, task, input), { reinspects: a.reinspects, task });
    setOpen(null);
    setNote('');
  };
  const press = (a: TaskAction) => {
    if (a.needs) setOpen(open?.id === a.id ? null : a);
    else send(a);
  };
  const candidates = roster.filter((p) => p.person_id !== task.assignee_id && p.role !== 'supervisor');

  return (
    <div className="task-actions">
      {GROUP_ORDER.map((group) => {
        const inGroup = actions.filter((a) => a.group === group);
        if (inGroup.length === 0) return null;
        const reasons = [...new Set(inGroup.filter((a) => !a.enabled && a.why).map((a) => a.why!))];
        return (
          <div key={group} className={`action-group group-${group}`}>
            <div className="action-group-title">{GROUP_TITLE[group]}</div>
            <div className="action-buttons">
              {inGroup.map((a) => {
                const key = actionKey(task, a);
                return (
                  <button
                    key={a.id}
                    type="button"
                    className={buttonClass(a)}
                    disabled={!a.enabled || busy !== null}
                    title={a.enabled ? undefined : a.why}
                    aria-expanded={a.needs ? open?.id === a.id : undefined}
                    onClick={() => press(a)}
                  >
                    {busy === key ? <SpinnerIcon className="vicon" /> : null}
                    {a.label}
                  </button>
                );
              })}
            </div>
            {reasons.map((r) => (
              <p key={r} className="action-why">
                {r}.
              </p>
            ))}
          </div>
        );
      })}

      {open?.needs === 'reason' ? (
        <div className="reason-picker" role="group" aria-label="Reason for the false alarm">
          <strong>Why is {task.finding_id} a false alarm?</strong> This records a Confirmation in your name.
          <div className="action-buttons">
            {FALSE_ALARM_REASONS.map((r) => (
              <button key={r.value} type="button" disabled={busy !== null} onClick={() => send(open, { reason: r.value })}>
                {r.label}
              </button>
            ))}
            <button type="button" className="quiet" onClick={() => setOpen(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {open?.needs === 'note' ? (
        <form
          className="reason-picker"
          onSubmit={(e) => {
            e.preventDefault();
            send(open, { note });
          }}
        >
          <label className="field">
            Why can you not do {task.task_id}? The Ramp Lead is told. This is a Report, not a Confirmation.
            <input type="text" value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} placeholder="For example: at another Gate" autoFocus />
          </label>
          <div className="action-buttons">
            <button type="submit" className="primary" disabled={busy !== null}>
              Send
            </button>
            <button type="button" className="quiet" onClick={() => setOpen(null)}>
              Cancel
            </button>
          </div>
        </form>
      ) : null}

      {open?.needs === 'person' ? (
        <form
          className="reason-picker"
          onSubmit={(e) => {
            e.preventDefault();
            if (personId) send(open, { personId });
          }}
        >
          <label className="field">
            Move {task.task_id} to
            <select value={personId} onChange={(e) => setPersonId(e.target.value)}>
              <option value="">Pick a person…</option>
              {candidates.map((p) => (
                <option key={p.person_id} value={p.person_id}>
                  {p.name} · {PERSON_ROLE_LABEL[p.role]}
                  {p.shift === 'on' ? '' : ` (${p.shift})`}
                </option>
              ))}
            </select>
          </label>
          <div className="action-buttons">
            <button type="submit" className="primary" disabled={busy !== null || !personId}>
              Move
            </button>
            <button type="button" className="quiet" onClick={() => setOpen(null)}>
              Cancel
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}

/** The one or two next steps for a Task, repeated under the agent's newest message about it. */
export function QuickActions({ task, viewer, busy, run }: Omit<CommonProps, 'roster'> & { task: Task }) {
  const quick = taskActions(task, viewer).filter((a) => a.quick && a.enabled && !a.needs);
  return (
    <div className="quick-actions">
      {quick.map((a) => (
        <button
          key={a.id}
          type="button"
          className={`compact ${buttonClass(a)}`}
          disabled={busy !== null}
          onClick={() => run(actionKey(task, a), actionCommand(a.id, task), { reinspects: a.reinspects, task })}
        >
          {busy === actionKey(task, a) ? <SpinnerIcon className="vicon" /> : null}
          {a.label}
          {a.group === 'report' ? <span className="btn-kind">Report</span> : null}
        </button>
      ))}
      <a className="btn compact quiet" href={turnHref(task.turn_id)}>
        Open Turn <ArrowRightIcon className="vicon" />
      </a>
    </div>
  );
}

function StatusChip({ task }: { task: Task }) {
  const label = taskStatusLabel(task);
  const icon =
    task.status === 'closed' ? (
      <CheckCircleIcon />
    ) : task.status === 'cancelled' ? (
      <CrossIcon />
    ) : task.status === 'reported' ? (
      <ReportIcon />
    ) : task.status === 'accepted' ? (
      <PenIcon />
    ) : (
      <TaskIcon />
    );
  return (
    <span className={`status-chip st-${task.status}`}>
      {icon}
      {label}
    </span>
  );
}

function TaskCard({ task, now, ...common }: CommonProps & { task: Task; now: number }) {
  const active = isActiveTask(task);
  const hold = task.severity === 'HOLD';
  const escalation = active ? escalationLabel(task.escalation_level) : null;
  const assignee = common.roster.find((p) => p.person_id === task.assignee_id);
  const mine = task.assignee_id === common.viewer.person_id;
  const reinspecting = common.busy !== null && common.busy.startsWith(`${task.task_id}:`) && /:(removed|reinspect)$/.test(common.busy);
  return (
    <li className={`task-card${hold && active ? ' is-hold' : ''}${escalation ? ' is-escalated' : ''}${active ? '' : ' is-closed'}`}>
      <div className="task-top">
        <span className="task-gate">{task.gate}</span>
        <span className="task-where">
          {[task.angle, task.finding_id].filter(Boolean).join(' · ') || 'Whole Gate'}
        </span>
        {task.severity ? <SeverityBadge severity={task.severity} big={hold} /> : null}
        <span className="task-id mono">{task.task_id}</span>
      </div>
      {hold && active ? (
        <p className="hold-line">
          <HoldIcon className="vicon" /> HOLD: nothing moves until a Ramp Lead clears this.
        </p>
      ) : null}
      {escalation ? (
        <p className="esc-flag">
          <EscalationIcon className="vicon" /> {escalation.toUpperCase()}
        </p>
      ) : null}
      <h3 className="task-type">{TASK_TYPE_LABEL[task.type] ?? task.type}</h3>
      <p className="task-instruction">{task.instruction}</p>
      <div className="task-meta">
        <StatusChip task={task} />
        <span className="nowrap">
          <ClockIcon className="vicon" /> {active ? `Age ${formatAge(task.created_at, now)}` : `Created ${formatAge(task.created_at, now)} ago`}
        </span>
        {!mine ? <span className="nowrap">With {assignee?.name ?? task.assignee_id ?? 'nobody'}</span> : null}
      </div>
      {!active && task.close_reason ? <p className="small muted">{task.close_reason}.</p> : null}
      {reinspecting ? (
        <div className="busy-bar" role="status">
          <SpinnerIcon className="spin" /> Re-inspecting {task.gate} {task.angle}: taking a new photo…
        </div>
      ) : null}
      <div className="task-links">
        <a className="btn compact" href={turnHref(task.turn_id)}>
          Open Turn: photos and Finding boxes <ArrowRightIcon className="vicon" />
        </a>
      </div>
      {active ? <TaskActions task={task} {...common} /> : null}
    </li>
  );
}

export function TaskList({ tasks, now, ...common }: CommonProps & { tasks: Task[]; now: number }) {
  const sorted = sortTasks(tasks);
  const open = sorted.filter(isActiveTask);
  const closed = sorted.filter((t) => !isActiveTask(t));
  const supervisor = common.viewer.role === 'supervisor';
  return (
    <aside className="panel tasks-panel" aria-label={supervisor ? 'All Tasks' : 'My Tasks'}>
      <div className="findings-head">
        <h2>
          {supervisor ? 'All Tasks' : 'My Tasks'} <span className="muted num">({open.length} open)</span>
        </h2>
      </div>
      {open.length === 0 ? (
        <p className="empty">{supervisor ? 'No open Tasks at any Gate.' : 'No Tasks. The agent will message you here.'}</p>
      ) : (
        <ul className="task-list">
          {open.map((t) => (
            <TaskCard key={t.task_id} task={t} now={now} {...common} />
          ))}
        </ul>
      )}
      {closed.length > 0 ? (
        <details className="block">
          <summary>Recently closed ({closed.length})</summary>
          <ul className="task-list">
            {closed.map((t) => (
              <TaskCard key={t.task_id} task={t} now={now} {...common} />
            ))}
          </ul>
        </details>
      ) : null}
    </aside>
  );
}
