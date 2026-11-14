import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { Api } from '../api/client';
import { describeError } from '../api/errors';
import type { TurnRecord as TurnRecordData, TurnRecordEntry } from '../api/turnRecordTypes';
import { formatTime, formatUsd, plural } from '../lib/format';
import { personRoleLabel } from '../lib/labels';
import { buildRecordDownload, entryEventLabel, entryKindLabel, normaliseTurnRecord } from '../lib/turnRecord';
import { turnHref } from '../route';
import { CameraIcon, ChatIcon, CheckCircleIcon, DashIcon, EscalationIcon, SpinnerIcon, TaskIcon } from './icons';
import '../turn-record.css';

const RECORD_POLL_MS = 2000;
const KNOWN_KINDS = new Set(['inspection', 'task', 'report', 'confirmation']);

const VIA_LABEL: Record<string, string> = {
  command: 'by command or button',
  agent: 'in plain text, read by the agent',
  free_text: 'in plain text',
  accepted_proposal: 'by accepting a proposal',
  dashboard: 'from the dashboard',
  chat: 'from the chat page',
};
const viaLabel = (via: unknown) => (typeof via === 'string' && via ? (VIA_LABEL[via] ?? `via ${via.replace(/_/g, ' ')}`) : '');
const text = (v: unknown) => (typeof v === 'string' ? v : null);

/**
 * The Turn record: every Inspection, Task, Report and Confirmation of the Turn
 * in time order, with who did each and when, the Turn's cost and a JSON
 * download. Read-only: it offers no action that writes.
 */
export function TurnRecord({ api, turnId }: { api: Api; turnId: string }) {
  const [open, setOpen] = useState(false);
  const [record, setRecord] = useState<TurnRecordData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastJson = useRef('');
  const bodyId = useId();

  useEffect(() => {
    lastJson.current = '';
    setRecord(null);
    setError(null);
    if (!open) return;
    let cancelled = false;
    let inFlight = false;
    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const next = normaliseTurnRecord(await api.getTurnRecord(turnId), turnId);
        if (cancelled) return;
        // `generated_at` changes on every call: re-render only when the record itself changed.
        const json = JSON.stringify({ ...next, generated_at: '' });
        if (json !== lastJson.current) {
          lastJson.current = json;
          setRecord(next);
        }
        setError(null);
      } catch (e) {
        if (!cancelled) setError(describeError(e, 'load'));
      } finally {
        inFlight = false;
      }
    };
    void load();
    const id = setInterval(() => void load(), RECORD_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [api, turnId, open]);

  const download = useMemo(() => {
    if (!record) return null;
    const { filename, text: json } = buildRecordDownload(record);
    return { filename, href: `data:application/json;charset=utf-8,${encodeURIComponent(json)}` };
  }, [record]);

  return (
    <section className="panel trec" aria-label="Turn record" data-turn-id={turnId}>
      <div className="trec-head">
        <h2 className="section-title">Turn record</h2>
        <button type="button" className="compact" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen((o) => !o)}>
          {open ? 'Hide Turn record' : 'Show Turn record'}
        </button>
      </div>
      {open && (
        <div id={bodyId}>
          {error && (
            <div className="banner error" role="alert">
              <span className="grow">
                {error} {record ? 'Showing the last record received; retrying.' : 'Retrying.'}
              </span>
            </div>
          )}
          {!record ? (
            !error && (
              <p className="muted row" role="status">
                <SpinnerIcon className="vicon" /> Loading Turn record…
              </p>
            )
          ) : (
            <>
              <div className="trec-top">
                <div className="stat-row" aria-label="Cost of this Turn">
                  <div className="stat">
                    <b className="num">{formatUsd(record.cost.inspections_usd)}</b>
                    <span>Inspections</span>
                  </div>
                  <div className="stat">
                    <b className="num">{formatUsd(record.cost.agent_usd)}</b>
                    <span>Agent</span>
                  </div>
                  <div className="stat">
                    <b className="num">{formatUsd(record.cost.total_usd)}</b>
                    <span>Turn cost</span>
                  </div>
                </div>
                {download && (
                  <a className="btn compact" href={download.href} download={download.filename}>
                    Download JSON
                  </a>
                )}
              </div>
              {record.cost.note && <p className="muted small">{record.cost.note}</p>}
              <p className="muted small trec-key">
                {plural(record.entries.length, 'entry', 'entries')}, oldest first. A Report is what a person said. A Confirmation is what
                was recorded.
              </p>
              {record.entries.length === 0 ? (
                <p className="empty">Nothing is recorded for this Turn yet.</p>
              ) : (
                <ol className="trec-list">
                  {record.entries.map((e) => (
                    <RecordEntry key={`${e.seq}-${e.at}`} entry={e} turnId={record.turn_id || turnId} />
                  ))}
                </ol>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

function KindIcon({ entry }: { entry: TurnRecordEntry }) {
  if (entry.kind === 'inspection') return <CameraIcon className="vicon" />;
  if (entry.kind === 'task') return entry.event === 'escalated' ? <EscalationIcon className="vicon" /> : <TaskIcon className="vicon" />;
  if (entry.kind === 'report') return <ChatIcon className="vicon" />;
  if (entry.kind === 'confirmation') return <CheckCircleIcon className="vicon" />;
  return <DashIcon className="vicon" />;
}

function personText(entry: TurnRecordEntry): { name: string; role: string } | null {
  const p = entry.person;
  if (!p) return null;
  return { name: p.name ?? p.person_id ?? 'Unknown person', role: personRoleLabel(p.role) };
}

function RecordEntry({ entry, turnId }: { entry: TurnRecordEntry; turnId: string }) {
  const kindClass = KNOWN_KINDS.has(entry.kind) ? entry.kind : 'other';
  const person = personText(entry);
  const level = entry.kind === 'task' && entry.event === 'escalated' && typeof entry.data.level === 'number' ? entry.data.level : null;
  const finding = text(entry.data.finding_label) ?? entry.refs.finding_id;
  const event = entryEventLabel(entry.event);
  const who = person ? (
    <>
      <span className="trec-name">{person.name}</span>
      {person.role && <span className="trec-role">{person.role}</span>}
    </>
  ) : (
    <span className="trec-name muted">System</span>
  );

  let body: React.ReactNode;
  if (entry.kind === 'report') {
    const said = text(entry.data.raw_text);
    body = (
      <figure className="trec-said">
        <blockquote className={said ? 'trec-quote' : 'trec-quote trec-quote-plain'}>{said ? `“${said}”` : entry.text}</blockquote>
        <figcaption className="small">
          Said by {who}
          {viaLabel(entry.data.via) ? <span className="muted"> {viaLabel(entry.data.via)}</span> : null}
          {said && entry.text ? <span className="muted trec-line"> {entry.text}</span> : null}
        </figcaption>
      </figure>
    );
  } else if (entry.kind === 'confirmation') {
    body = (
      <div className="trec-stamp">
        <span className="trec-stamp-mark">Recorded</span>
        <p>{entry.text}</p>
        <p className="small">
          Recorded by {who}
          {viaLabel(entry.data.via) ? <span className="muted"> {viaLabel(entry.data.via)}</span> : null}
        </p>
      </div>
    );
  } else {
    body = (
      <>
        <p className="trec-text">{entry.text || <span className="muted">No description.</span>}</p>
        <p className="small">
          {entry.kind === 'task' ? 'With ' : ''}
          {who}
        </p>
      </>
    );
  }

  return (
    <li className={`trec-entry trec-${kindClass}`} data-kind={entry.kind} data-event={entry.event} data-seq={entry.seq}>
      <time className="trec-time num" dateTime={entry.at} title={entry.at}>
        {formatTime(entry.at)}
      </time>
      <div className="trec-kind">
        <KindIcon entry={entry} />
        <span>
          <b>{entryKindLabel(entry.kind)}</b>
          {event && <span className="trec-event"> {event}</span>}
          {level !== null && <span className="trec-level"> · level {level}</span>}
        </span>
      </div>
      <div className="trec-body">
        {body}
        <p className="trec-refs small muted mono">
          {entry.refs.task_id && <span>{entry.refs.task_id}</span>}
          {finding && <span>{finding}</span>}
          {entry.refs.angle && <span>{entry.refs.angle}</span>}
          {entry.refs.inspection_id && <a href={turnHref(turnId, entry.refs.inspection_id)}>{entry.refs.inspection_id}</a>}
          {entry.data.sample === true && <span className="trec-sample">Sample</span>}
        </p>
      </div>
    </li>
  );
}
