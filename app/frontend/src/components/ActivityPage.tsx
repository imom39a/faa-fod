import { useEffect, useMemo, useRef, useState } from 'react';
import type { ActivityEntry, AgentApi, AgentCost, RosterPerson } from '../api/agentTypes';
import { MOCK_MODE } from '../api';
import { describeAgentError } from '../api/errors';
import {
  CATEGORY_LABEL,
  CATEGORY_ORDER,
  activityCategory,
  activityFacets,
  entryInspectionId,
  entryText,
  filterActivity,
  mergeActivity,
  type ActivityCategory,
} from '../lib/activity';
import { formatClock, formatTime, formatUsd } from '../lib/format';
import { useDeveloperMode } from '../store/settings';
import { PERSON_ROLE_LABEL } from '../lib/labels';
import { activityHref, navigate, turnHref, type ActivityRouteFilter } from '../route';
import {
  AgentIcon,
  ArrowRightIcon,
  ChatIcon,
  CheckCircleIcon,
  ClockIcon,
  CrossIcon,
  DashIcon,
  EyeIcon,
  QuestionIcon,
  ReportIcon,
  TaskIcon,
  UserIcon,
} from './icons';

const ICON: Record<ActivityCategory, React.ReactNode> = {
  inspection: <EyeIcon />,
  task: <TaskIcon />,
  report: <ReportIcon />,
  confirmation: <CheckCircleIcon />,
  refusal: <CrossIcon />,
  shift: <UserIcon />,
  message: <ChatIcon />,
  proposal: <QuestionIcon />,
  timer: <ClockIcon />,
  agent: <AgentIcon />,
  system: <DashIcon />,
};
const PAGE = 300;

/** Everything that happened, newest first, with live updates from GET /api/agent/activity. */
export function ActivityPage({ agent, filter }: { agent: AgentApi; filter: ActivityRouteFilter }) {
  const developer = useDeveloperMode();
  const [entries, setEntries] = useState<ActivityEntry[]>([]);
  const [cost, setCost] = useState<AgentCost | null>(null);
  const [roster, setRoster] = useState<RosterPerson[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loaded, setLoaded] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const state = useRef<{ epoch: number | null; cursor: number }>({ epoch: null, cursor: 0 });

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;
    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await agent.activity({ after: state.current.cursor, limit: 1000 });
        if (cancelled) return;
        if (state.current.epoch !== null && res.epoch !== state.current.epoch) {
          // The demo was reset: the log starts again.
          state.current = { epoch: res.epoch, cursor: 0 };
          setEntries([]);
        } else {
          state.current = { epoch: res.epoch, cursor: Math.max(state.current.cursor, res.cursor) };
          setEntries((prev) => mergeActivity(prev, res.entries));
        }
        setCost(res.cost);
        setError(null);
        setLoaded(true);
      } catch (e) {
        if (!cancelled) setError(e);
      } finally {
        inFlight = false;
      }
    };
    void poll();
    void agent.roster().then(
      (r) => !cancelled && setRoster(r.people),
      () => undefined,
    );
    const timer = setInterval(() => void poll(), 1000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [agent]);

  const facets = useMemo(() => activityFacets(entries), [entries]);
  const category = CATEGORY_ORDER.includes(filter.kind as ActivityCategory) ? (filter.kind as ActivityCategory) : null;
  const shown = useMemo(
    () => filterActivity(entries, { gate: filter.gate, turnId: filter.turnId, personId: filter.personId, category }, roster).reverse(),
    [entries, filter.gate, filter.turnId, filter.personId, category, roster],
  );
  const set = (patch: Partial<ActivityRouteFilter>) => navigate(activityHref({ ...filter, ...patch }));
  const filtered = Boolean(filter.gate || filter.turnId || filter.personId || category);
  const who = (actor: string) => {
    if (actor === 'code') return 'System';
    if (actor === 'agent') return 'Agent';
    if (actor === 'timer') return 'Timer';
    const p = roster.find((x) => x.person_id === actor.toLowerCase() || x.name === actor);
    return p ? `${p.name} (${PERSON_ROLE_LABEL[p.role]})` : actor;
  };

  return (
    <div className="activity">
      <div className="turn-head">
        <h2 className="page-title">Activity log</h2>
        <span className="muted small">Newest first · updates every second</span>
        <span className="spacer" />
        {developer && cost ? (
          <div className="stat-row cost-row" aria-label="Agent session cost">
            <div className="stat">
              <b className="num">{formatUsd(cost.agent_session_usd)}</b>
              <span>Agent session cost</span>
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
        ) : null}
      </div>
      {developer && MOCK_MODE ? (
        <p className="small muted">Mock mode: no model is called; cost and token figures are illustrative.</p>
      ) : null}
      {error ? (
        <div className="banner error" role="alert">
          <span className="grow">
            <strong>Not connected</strong>
            {describeAgentError(error)}
          </span>
        </div>
      ) : null}

      <div className="panel filters" role="group" aria-label="Filters">
        <label className="field">
          Gate
          <select value={filter.gate ?? ''} onChange={(e) => set({ gate: e.target.value || null })}>
            <option value="">All Gates</option>
            {facets.gates.map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Turn
          <select value={filter.turnId ?? ''} onChange={(e) => set({ turnId: e.target.value || null })}>
            <option value="">All Turns</option>
            {facets.turns.map((t) => (
              <option key={t.turn_id}>{t.turn_id}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Person
          <select value={filter.personId ?? ''} onChange={(e) => set({ personId: e.target.value || null })}>
            <option value="">Everyone</option>
            {roster.map((p) => (
              <option key={p.person_id} value={p.person_id}>
                {p.name} · {PERSON_ROLE_LABEL[p.role]}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Kind
          <select value={category ?? ''} onChange={(e) => set({ kind: e.target.value || null })}>
            <option value="">All kinds</option>
            {CATEGORY_ORDER.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABEL[c]}
              </option>
            ))}
          </select>
        </label>
        <button type="button" disabled={!filtered} onClick={() => navigate(activityHref())}>
          Clear filters
        </button>
        <span className="muted small num">
          {shown.length} of {entries.length} entries
        </span>
      </div>

      {!loaded && !error ? <p className="muted">Loading the activity log…</p> : null}
      {loaded && shown.length === 0 ? (
        <p className="empty">{filtered ? 'Nothing matches these filters.' : 'Nothing has happened yet. Press Play to start the demo.'}</p>
      ) : null}
      <ol className="act-list">
        {shown.slice(0, limit).map((e) => {
          const cat = activityCategory(e);
          const by = e.data.by as { name?: string; role?: string } | undefined;
          const usd = typeof e.data.est_cost_usd === 'number' ? e.data.est_cost_usd : null;
          return (
            <li key={e.id} className={`act-row cat-${cat}`}>
              <div className="act-time num">
                {formatTime(e.at)}
                <small>demo {formatClock(e.t)}</small>
              </div>
              <span className={`kind-tag cat-tag cat-${cat}`}>
                {ICON[cat]}
                {CATEGORY_LABEL[cat]}
              </span>
              <div className="act-body">
                <div className="act-text">{entryText(e)}</div>
                <div className="act-meta">
                  {cat === 'confirmation' && by?.name ? (
                    <span>
                      Confirmed by <b>{who(by.name)}</b> at {formatTime(e.at)}
                    </span>
                  ) : (
                    <span>
                      By <b>{who(e.actor)}</b>
                      {typeof e.data.to === 'string' ? ` to ${who(e.data.to)}` : ''}
                    </span>
                  )}
                  {cat === 'report' ? <span>A Report: nothing was recorded on the Inspection</span> : null}
                  {developer && usd !== null ? (
                    <span className="num">
                      Wake cost {formatUsd(usd)} · {String(e.data.tokens_in ?? 0)} in / {String(e.data.tokens_out ?? 0)} out
                    </span>
                  ) : null}
                  {e.gate ? <span className="gate-chip">{e.gate}</span> : null}
                  {e.turn_id ? (
                    <a href={turnHref(e.turn_id, entryInspectionId(e))}>
                      Open Turn {e.turn_id} <ArrowRightIcon className="vicon" />
                    </a>
                  ) : null}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
      {shown.length > limit ? (
        <button type="button" onClick={() => setLimit(limit + PAGE)}>
          Show older entries
        </button>
      ) : null}
    </div>
  );
}
