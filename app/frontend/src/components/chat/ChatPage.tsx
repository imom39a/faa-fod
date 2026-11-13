import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import type { AgentApi, ChatMessage, CommandResult, Proposal, RosterPerson, SayResult, Task } from '../../api/agentTypes';
import { MOCK_MODE } from '../../api';
import { describeAgentError } from '../../api/errors';
import { formatClock, formatTime } from '../../lib/format';
import { latestMessagePerTask, messageVariant, parseRefusal, reinspectionRunning, senderLabel, tidyMessageText, type MessageVariant } from '../../lib/inbox';
import { PERSON_ROLE_LABEL, SHIFT_LABEL } from '../../lib/labels';
import { isActiveTask, type Viewer } from '../../lib/taskActions';
import { turnHref } from '../../route';
import { useInboxStore, type InboxStore } from '../../store/inboxStore';
import { useSession, type Session, type SessionStore } from '../../store/session';
import { SeverityBadge } from '../bits';
import {
  AgentIcon,
  ArrowRightIcon,
  CameraIcon,
  CheckCircleIcon,
  CrossIcon,
  EscalationIcon,
  QuestionIcon,
  RemoveIcon,
  ReportIcon,
  SendIcon,
  SignOutIcon,
  SpinnerIcon,
  TaskIcon,
  UserIcon,
} from '../icons';
import { QuickActions, TaskList, type RunCommand } from './TaskList';

type Props = { agent: AgentApi; sessionStore: SessionStore; inboxStore: InboxStore };

/** The per-person chat with the always-on agent: sign-in, thread, Tasks, proposals. */
export function ChatPage({ agent, sessionStore, inboxStore }: Props) {
  const session = useSession(sessionStore);
  const inbox = useInboxStore(inboxStore);
  if (!session) {
    return <SignIn agent={agent} sessionStore={sessionStore} note={inbox.signedOutNote} onNoteSeen={() => inboxStore.clearNote()} />;
  }
  return <ChatRoom key={session.person.person_id} agent={agent} session={session} sessionStore={sessionStore} inboxStore={inboxStore} />;
}

// ---------------------------------------------------------------------- sign-in

function useRoster(agent: AgentApi, intervalMs: number | null): { roster: RosterPerson[] | null; error: unknown; reload: () => void } {
  const [roster, setRoster] = useState<RosterPerson[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      agent.roster().then(
        (r) => {
          if (!cancelled) {
            setRoster(r.people);
            setError(null);
          }
        },
        (e: unknown) => {
          if (!cancelled) setError(e);
        },
      );
    void load();
    const timer = intervalMs ? setInterval(() => void load(), intervalMs) : null;
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [agent, intervalMs, nonce]);
  return { roster, error, reload: () => setNonce((n) => n + 1) };
}

function SignIn({ agent, sessionStore, note, onNoteSeen }: { agent: AgentApi; sessionStore: SessionStore; note: string | null; onNoteSeen: () => void }) {
  const { roster, error: rosterError, reload } = useRoster(agent, 5000);
  const [personId, setPersonId] = useState<string | null>(null);
  const [pin, setPin] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const picked = roster?.find((p) => p.person_id === personId) ?? null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!picked || !pin) return;
    setPending(true);
    setError(null);
    try {
      const out = await agent.join(picked.person_id, pin);
      onNoteSeen();
      sessionStore.signIn({ token: out.token, person: out.person });
    } catch (err) {
      setError(describeAgentError(err));
      setPin('');
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="signin">
      <h2 className="page-title">Chat with the agent</h2>
      <p className="muted">
        Sign in to see your Tasks and messages. Your role comes from the roster, not from this page.
      </p>
      {note ? (
        <div className="banner warn" role="alert">
          <span className="grow">
            <strong>Signed out</strong>
            {note}
          </span>
        </div>
      ) : null}
      {rosterError && !roster ? (
        <div className="banner error" role="alert">
          <span className="grow">
            <strong>The roster could not be loaded</strong>
            {describeAgentError(rosterError)}
          </span>
          <button type="button" className="compact" onClick={reload}>
            Try again
          </button>
        </div>
      ) : null}
      {!roster && !rosterError ? (
        <p className="muted row">
          <SpinnerIcon className="vicon" /> Loading the roster…
        </p>
      ) : null}
      {roster ? (
        <form className="panel signin-form" onSubmit={submit}>
          <fieldset>
            <legend className="section-title">1. Who are you?</legend>
            {roster.length === 0 ? <p className="empty">The roster is empty. Ask the supervisor to add people to the roster file.</p> : null}
            <div className="people">
              {roster.map((p) => (
                <button
                  key={p.person_id}
                  type="button"
                  className="person-btn"
                  aria-pressed={personId === p.person_id}
                  onClick={() => {
                    setPersonId(p.person_id);
                    setPin('');
                    setError(null);
                  }}
                >
                  <span className="person-name">{p.name}</span>
                  <span className="person-role">{PERSON_ROLE_LABEL[p.role]}</span>
                  <span className="person-gates">Gates {p.gates.join(', ') || 'none'}</span>
                  <span className="person-state">
                    {SHIFT_LABEL[p.shift]}
                    {p.signed_in ? ' · signed in elsewhere' : ''}
                  </span>
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset disabled={!picked}>
            <legend className="section-title">2. Your PIN</legend>
            <div className="pin-row">
              <label className="field">
                {picked ? `PIN for ${picked.name}` : 'Pick your name first'}
                <input
                  className="pin-input"
                  type="password"
                  inputMode="numeric"
                  autoComplete="off"
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  aria-invalid={error !== null}
                  maxLength={12}
                />
              </label>
              <button type="submit" className="primary big" disabled={!picked || !pin || pending}>
                {pending ? <SpinnerIcon className="vicon" /> : null}
                Sign in{picked ? ` as ${picked.name}` : ''}
              </button>
            </div>
            {error ? (
              <p className="form-error" role="alert">
                <CrossIcon className="vicon" /> {error}
              </p>
            ) : null}
          </fieldset>
          <p className="small muted">
            The PIN stands in for sign-in in this proof of concept. It is not a secret and not how production would identify people.
            {MOCK_MODE ? ' Mock mode demo PINs: Kim 1111, Okafor 2222, Patel 3333, Reyes 4444, Dana 9999.' : ''}
          </p>
        </form>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------- the room

type Notice = { tone: 'ok' | 'warn' | 'info' | 'error'; title: string; text: string };

/** What to say right after a command answered. The same lines also arrive in the thread. */
function resultNotice(lines: string[]): Notice | null {
  const text = lines.join('\n');
  if (/still shows the object/.test(text)) return { tone: 'warn', title: 'Still there: the HOLD stays open', text };
  if (/(^|\s)Recorded: /.test(text) || /^Inspection signed off by /.test(text)) return { tone: 'ok', title: 'Recorded', text };
  if (/^New photo of /.test(text)) return { tone: 'info', title: 'New photo taken. Nothing was recorded', text };
  if (/^Logged/.test(text)) return { tone: 'info', title: 'Report logged. Nothing was recorded on the Inspection', text };
  if (/^Declined/.test(text)) return { tone: 'info', title: 'Declined', text };
  return null;
}

function ChatRoom({ agent, session, sessionStore, inboxStore }: Props & { session: Session }) {
  const inbox = useInboxStore(inboxStore);
  const { roster } = useRoster(agent, 10_000);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [reinspecting, setReinspecting] = useState<string | null>(null);
  const { token, person } = session;
  const viewer: Viewer = useMemo(() => ({ person_id: person.person_id, role: person.role }), [person.person_id, person.role]);
  const people = roster ?? [person];
  const names = useMemo(() => Object.fromEntries(people.map((p) => [p.person_id, p.name])), [people]);

  const act = useCallback(
    async (key: string, send: () => Promise<CommandResult | SayResult>, reinspectLabel: string | null = null) => {
      setBusy(key);
      setNotice(null);
      setReinspecting(reinspectLabel);
      // The server puts "Re-inspecting ..." in the thread before it takes the photo: show it straight away.
      const nudge = setTimeout(() => void inboxStore.refresh(), 400);
      try {
        const out = await send();
        if ('lines' in out) setNotice(resultNotice(out.lines));
      } catch (err) {
        setNotice({ tone: 'error', title: 'Refused. Nothing was recorded', text: describeAgentError(err) });
      } finally {
        clearTimeout(nudge);
        setBusy(null);
        setReinspecting(null);
        void inboxStore.refresh();
      }
    },
    [inboxStore],
  );

  const run: RunCommand = useCallback(
    (key, command, meta) => void act(key, () => agent.command(token, command), meta?.reinspects && meta.task ? `${meta.task.gate} ${meta.task.angle ?? ''}`.trim() : null),
    [act, agent, token],
  );
  const answer = (p: Proposal, accept: boolean) => void act(`${p.proposal_id}:${accept ? 'y' : 'n'}`, () => agent.answerProposal(token, p.proposal_id, accept));
  const say = (text: string) => act('say', () => agent.say(token, text));

  const myTasks = inbox.tasks;
  const openCount = myTasks.filter(isActiveTask).length;
  const running = reinspecting ?? (reinspectionRunning(inbox.messages, person.person_id) ? 'the Angle' : null);

  return (
    <div className="chat-page">
      <div className="chat-head">
        <span className="avatar" aria-hidden="true">
          <UserIcon />
        </span>
        <div className="chat-who">
          <strong>{person.name}</strong>
          <span>
            {PERSON_ROLE_LABEL[person.role]} · Gates {person.gates.join(', ') || 'none'} · {SHIFT_LABEL[person.shift]}
          </span>
        </div>
        <span className="spacer" />
        <span className="muted small nowrap">
          {openCount} open {openCount === 1 ? 'Task' : 'Tasks'}
        </span>
        <button type="button" onClick={() => sessionStore.signOut()}>
          <SignOutIcon className="vicon" /> Sign out
        </button>
      </div>

      {inbox.error ? (
        <div className="banner error" role="alert">
          <span className="grow">
            <strong>Not connected</strong>
            {describeAgentError(inbox.error)} Showing the last messages received.
          </span>
        </div>
      ) : null}

      <div className="chat-layout">
        <section className="panel thread-panel" aria-label="Thread with the agent">
          <Thread
            messages={inbox.messages}
            loaded={inbox.loaded}
            meId={person.person_id}
            names={names}
            tasks={myTasks}
            proposals={inbox.proposals}
            viewer={viewer}
            busy={busy}
            run={run}
            runningReinspection={running !== null}
          />
          {running ? (
            <div className="busy-bar" role="status">
              <SpinnerIcon className="spin" /> Re-inspecting {running}: taking a new photo. Nothing is recorded until it comes back.
            </div>
          ) : null}
          {notice ? (
            <div className={`banner ${notice.tone}`} role={notice.tone === 'error' ? 'alert' : 'status'}>
              <span className="grow">
                <strong>{notice.title}</strong>
                <span className="pre">{notice.text}</span>
              </span>
              <button type="button" className="compact quiet" onClick={() => setNotice(null)}>
                Dismiss
              </button>
            </div>
          ) : null}
          {inbox.proposals.map((p) => (
            <ProposalCard key={p.proposal_id} proposal={p} busy={busy} onAnswer={answer} names={names} />
          ))}
          <Composer onSend={say} sending={busy === 'say'} disabled={busy !== null} supervisor={person.role === 'supervisor'} />
        </section>

        <TaskList tasks={myTasks} now={Date.now()} viewer={viewer} roster={people} busy={busy} run={run} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------- proposals

function ProposalCard({ proposal: p, busy, onAnswer, names }: { proposal: Proposal; busy: string | null; onAnswer: (p: Proposal, accept: boolean) => void; names: Record<string, string> }) {
  const confirms = p.kind === 'confirm';
  const question = p.question ? `${p.question.charAt(0).toUpperCase()}${p.question.slice(1)}?` : 'Accept?';
  const turnId = p.action.turn_id;
  return (
    <div className="proposal-card" role="group" aria-label={`Question ${p.proposal_id}`}>
      <div className="proposal-head">
        <span className="kind-tag k-question">
          <QuestionIcon /> Question for you
        </span>
        <span className="mono muted">{p.proposal_id}</span>
        <span className="muted small">from {senderLabel(p.created_by, names)}</span>
        <span className="spacer" />
        <span className={`expiry num${p.expires_in_s < 30 ? ' soon' : ''}`}>Expires in {formatClock(p.expires_in_s)}</span>
      </div>
      <p className="proposal-question">{question}</p>
      <p className="small muted">
        {confirms
          ? 'Accept records this Confirmation in your name. Decline records nothing.'
          : p.kind === 'reinspect'
            ? 'Accept takes a new photo. A re-inspection never closes a Finding by itself.'
            : 'Accept moves these Tasks to you.'}
      </p>
      <div className="action-buttons">
        <button type="button" className="good big" disabled={busy !== null} onClick={() => onAnswer(p, true)}>
          {busy === `${p.proposal_id}:y` ? <SpinnerIcon className="vicon" /> : <CheckCircleIcon className="vicon" />}
          Accept
        </button>
        <button type="button" className="big" disabled={busy !== null} onClick={() => onAnswer(p, false)}>
          {busy === `${p.proposal_id}:n` ? <SpinnerIcon className="vicon" /> : <CrossIcon className="vicon" />}
          Decline
        </button>
        {turnId ? (
          <a className="btn quiet" href={turnHref(turnId)}>
            Open Turn <ArrowRightIcon className="vicon" />
          </a>
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------- thread

const VARIANT_TAG: Partial<Record<MessageVariant, { label: string; icon: React.ReactNode; cls: string }>> = {
  my_report: { label: 'Report · not a Confirmation', icon: <ReportIcon />, cls: 'k-report' },
  my_command: { label: 'Command', icon: <TaskIcon />, cls: 'k-command' },
  recorded: { label: 'Recorded · Confirmation', icon: <CheckCircleIcon />, cls: 'k-recorded' },
  refused: { label: 'Refused · nothing recorded', icon: <CrossIcon />, cls: 'k-refused' },
  report_logged: { label: 'Report logged · nothing recorded', icon: <ReportIcon />, cls: 'k-report' },
  reinspecting: { label: 'New photo', icon: <CameraIcon />, cls: 'k-photo' },
  still_there: { label: 'Still there · HOLD stays open', icon: <RemoveIcon />, cls: 'k-still' },
  photo: { label: 'New photo · nothing recorded', icon: <CameraIcon />, cls: 'k-photo' },
  escalation: { label: 'Escalation', icon: <EscalationIcon />, cls: 'k-escalation' },
  question: { label: 'Question', icon: <QuestionIcon />, cls: 'k-question' },
  task: { label: 'Task', icon: <TaskIcon />, cls: 'k-task' },
};

type ThreadProps = {
  messages: ChatMessage[];
  loaded: boolean;
  meId: string;
  names: Record<string, string>;
  tasks: Task[];
  proposals: Proposal[];
  viewer: Viewer;
  busy: string | null;
  run: RunCommand;
  runningReinspection: boolean;
};

function Thread({ messages, loaded, meId, names, tasks, proposals, viewer, busy, run, runningReinspection }: ThreadProps) {
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const [away, setAway] = useState(false);
  const latestForTask = useMemo(() => latestMessagePerTask(messages, meId), [messages, meId]);
  const last = messages.at(-1);

  // Follow new messages unless the person has scrolled up to read.
  useLayoutEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages.length, proposals.length, runningReinspection]);

  const onScroll = () => {
    const el = box.current;
    if (!el) return;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setAway(!stick.current);
  };
  const jump = () => {
    stick.current = true;
    setAway(false);
    const el = box.current;
    if (el) el.scrollTop = el.scrollHeight;
  };
  const waiting = last && messageVariant(last, meId) === 'my_report' && last.to === 'agent';

  return (
    <div className="thread-wrap">
      <div className="thread" ref={box} onScroll={onScroll} role="log" aria-live="polite" aria-label="Messages" tabIndex={0}>
        {!loaded ? (
          <p className="muted row">
            <SpinnerIcon className="vicon" /> Loading your messages…
          </p>
        ) : messages.length === 0 ? (
          <p className="empty thread-empty">
            No messages yet. When an Inspection needs you, the agent writes to you here. Start the demo with Play if nothing is running.
          </p>
        ) : null}
        {messages.map((m) => {
          const task = m.task_id ? tasks.find((t) => t.task_id === m.task_id) : undefined;
          const actionable = task && isActiveTask(task) && task.assignee_id === meId && latestForTask.get(task.task_id) === m.message_id;
          return (
            <MessageRow
              key={m.message_id}
              message={m}
              meId={meId}
              names={names}
              task={task}
              pending={m.proposal_id ? proposals.some((p) => p.proposal_id === m.proposal_id) : false}
              spinning={runningReinspection && m === last}
            >
              {actionable && task ? <QuickActions task={task} viewer={viewer} busy={busy} run={run} /> : null}
            </MessageRow>
          );
        })}
        {waiting ? (
          <p className="typing" role="status">
            <AgentIcon className="vicon" /> The agent is reading your message…
          </p>
        ) : null}
      </div>
      {away ? (
        <button type="button" className="jump compact" onClick={jump}>
          Jump to latest
        </button>
      ) : null}
    </div>
  );
}

type RowProps = {
  message: ChatMessage;
  meId: string;
  names: Record<string, string>;
  task: Task | undefined;
  /** For a question: whether it can still be answered. */
  pending: boolean;
  spinning: boolean;
  children?: React.ReactNode;
};

function MessageRow({ message: m, meId, names, task, pending, spinning, children }: RowProps) {
  const variant = messageVariant(m, meId);
  const mine = variant === 'my_report' || variant === 'my_command';
  const tag = VARIANT_TAG[variant];
  const refusal = variant === 'refused' ? parseRefusal(m.text) : null;
  const text = refusal ? refusal.message : tidyMessageText(m.text);
  const toOther = mine && m.to !== 'agent' && m.to !== 'code' ? ` to ${senderLabel(m.to, names)}` : '';
  const table = !mine && /\n/.test(text) && / {3,}/.test(text);
  return (
    <div className={`tmsg ${mine ? 'side-me' : 'side-them'} v-${variant}`}>
      <div className="tmsg-head">
        <span className="tmsg-who">{mine ? `You${toOther}` : senderLabel(m.from, names)}</span>
        {variant === 'hold_alert' ? <SeverityBadge severity="HOLD" /> : null}
        {tag ? (
          <span className={`kind-tag ${tag.cls}`}>
            {spinning && variant === 'reinspecting' ? <SpinnerIcon className="spin" /> : tag.icon}
            {variant === 'task' && m.task_id ? `Task ${m.task_id}` : tag.label}
          </span>
        ) : null}
        <time className="tmsg-time num" dateTime={m.at}>
          {formatTime(m.at)}
        </time>
      </div>
      <div className={`tmsg-text${variant === 'my_command' || table ? ' mono' : ''}`}>{text}</div>
      {refusal ? <div className="tmsg-note mono">{refusal.code}</div> : null}
      {variant === 'my_report' && m.to === 'agent' ? (
        <div className="tmsg-note">Sent to the agent as a Report. It records nothing on the Inspection.</div>
      ) : null}
      {variant === 'question' ? (
        <div className="tmsg-note">{pending ? 'Waiting for your answer: use Accept or Decline below.' : 'This question is closed (answered, expired or void).'}</div>
      ) : null}
      {children}
      {!children && task && !mine ? (
        <div className="quick-actions">
          <a className="btn compact quiet" href={turnHref(task.turn_id)}>
            Open Turn <ArrowRightIcon className="vicon" />
          </a>
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------- composer

function Composer({ onSend, sending, disabled, supervisor }: { onSend: (text: string) => Promise<void>; sending: boolean; disabled: boolean; supervisor: boolean }) {
  const [text, setText] = useState('');
  const trimmed = text.trim();
  const isCommand = trimmed.startsWith('/') || /^(y|n|yes|no)(\s|$)/i.test(trimmed);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!trimmed || disabled) return;
    setText('');
    void onSend(trimmed);
  };
  return (
    <form className="composer" onSubmit={submit}>
      <label className="sr-only" htmlFor="chat-text">
        Message to the agent
      </label>
      <div className="composer-row">
        <input
          id="chat-text"
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={500}
          autoComplete="off"
          placeholder={supervisor ? 'Message the agent, or type a command such as /tasks' : 'Tell the agent what you found or did…'}
        />
        <button type="submit" className="primary" disabled={!trimmed || disabled}>
          {sending ? <SpinnerIcon className="vicon" /> : <SendIcon className="vicon" />}
          {isCommand ? 'Run command' : 'Send Report'}
        </button>
      </div>
      <p className="composer-hint">
        {isCommand ? (
          <>
            <TaskIcon className="vicon" /> This is a command: it is run as you, exactly as typed.
          </>
        ) : (
          <>
            <ReportIcon className="vicon" /> Plain text is a <strong>Report</strong> to the agent, not a Confirmation. To record something, use the buttons on a Task
            or answer a question. <span className="mono">/help</span> lists the commands.
          </>
        )}
      </p>
    </form>
  );
}
