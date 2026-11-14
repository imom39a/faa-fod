import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, type Api } from '../api/client';
import { describeError, type ActionContext } from '../api/errors';
import type { AngleName, Finding, Person, Report, RuleSet, State, Turn } from '../api/types';
import { formatTime, plural } from '../lib/format';
import { tileModel } from '../lib/gates';
import { ANALYSIS_LABEL, KIND_LABEL, unusableReasonLabel } from '../lib/labels';
import {
  buildTimeline,
  confirmAllTargets,
  holdRemovalOutcome,
  isAngleUnresolved,
  isFindingOpen,
  isOutsideBoundary,
  openFindings,
  personLabel,
  reinspectOutcome,
} from '../lib/report';
import { OVERVIEW_HREF, navigate, turnHref } from '../route';
import { AngleFrame, type NumberedFinding } from './AngleFrame';
import { AssistantPanel } from './AssistantPanel';
import { AdvisoryTag, Credit, SeverityBadge, VerdictMark, verdictTone } from './bits';
import { DetailsPanel } from './DetailsPanel';
import { FindingCard, type ConfirmRequest } from './FindingCard';
import { CheckCircleIcon, EyeOffIcon, SpinnerIcon, ToneIcon } from './icons';
import { SignoffDialog } from './SignoffDialog';
import { Timeline } from './Timeline';
import { TurnRecord } from './TurnRecord';

type Notice = { tone: 'ok' | 'error' | 'warn' | 'info'; title: string; text?: string };

type Props = {
  api: Api;
  turnId: string;
  /** Inspection named in the URL; null follows the latest Inspection of the Turn. */
  pinnedInspectionId: string | null;
  /** Finding ID from `?finding=` (a link from the Crew and Tasks page): selected once when it loads. */
  focusFindingId?: string | null;
  state: State | null;
  person: Person;
  rules: RuleSet | null;
  refreshState: () => void;
};

const TURN_POLL_MS = 1500;

function defaultAngle(report: Report): AngleName {
  const withOpen = report.findings.find(isFindingOpen)?.angle;
  const unusable = report.angles.find(isAngleUnresolved)?.angle;
  return withOpen ?? unusable ?? report.angles[0]?.angle ?? 'NOSE';
}

export function TurnView({ api, turnId, pinnedInspectionId, focusFindingId = null, state, person, rules, refreshState }: Props) {
  const [turn, setTurn] = useState<Turn | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [angleChoice, setAngleChoice] = useState<{ inspectionId: string; angle: AngleName } | null>(null);
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [hotFindingId, setHotFindingId] = useState<string | null>(null);
  const [signoffOpen, setSignoffOpen] = useState(false);
  const [signoffError, setSignoffError] = useState<string | null>(null);
  const [confirmingAll, setConfirmingAll] = useState(false);
  const lastJson = useRef('');

  const load = useCallback(async () => {
    try {
      const next = await api.getTurn(turnId);
      const json = JSON.stringify(next);
      if (json !== lastJson.current) {
        lastJson.current = json;
        setTurn(next);
      }
      setLoadError(null);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'not_found') {
        lastJson.current = '';
        setTurn(null);
      }
      setLoadError(describeError(e, 'load'));
    }
  }, [api, turnId]);

  useEffect(() => {
    lastJson.current = '';
    setTurn(null);
    setNotice(null);
    void load();
    const id = setInterval(() => void load(), TURN_POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const inspections = turn?.inspections ?? [];
  const latest = inspections.at(-1) ?? null;
  const selected = inspections.find((r) => r.inspection_id === pinnedInspectionId) ?? latest;
  const selectedId = selected?.inspection_id ?? null;

  useEffect(() => {
    setSelectedFindingId(null);
    setHotFindingId(null);
    setConfirmingAll(false);
    setSignoffOpen(false);
  }, [selectedId]);

  // Open the Finding a link names, once per Inspection and Finding, so polling does not undo the viewer's choice.
  const focused = useRef('');
  useEffect(() => {
    const f = focusFindingId ? selected?.findings.find((x) => x.finding_id === focusFindingId) : undefined;
    const key = `${selectedId}|${focusFindingId}`;
    if (!f || !selected || focused.current === key) return;
    focused.current = key;
    setAngleChoice({ inspectionId: selected.inspection_id, angle: f.angle });
    setSelectedFindingId(f.finding_id);
    requestAnimationFrame(() => document.querySelector(`[data-finding="${CSS.escape(f.finding_id)}"]`)?.scrollIntoView({ block: 'nearest' }));
  }, [focusFindingId, selected, selectedId]);

  const numbered: NumberedFinding[] = useMemo(
    () => (selected ? selected.findings.map((finding, i) => ({ finding, number: i + 1 })) : []),
    [selected],
  );
  const timeline = useMemo(() => (turn ? buildTimeline(turn, state?.demo.t ?? null) : []), [turn, state?.demo.t]);

  const gateState = state?.gates.find((g) => g.gate === turn?.gate && g.turn?.turn_id === turnId) ?? null;
  const gate = gateState ? tileModel(gateState) : null;

  if (!turn || !selected) {
    return (
      <div>
        <div className="turn-head">
          <a className="btn" href={OVERVIEW_HREF}>
            ‹ Gates
          </a>
          <h2>Turn {turnId}</h2>
        </div>
        {loadError ? (
          <div className="banner error" role="alert">
            <span className="grow">{loadError}</span>
          </div>
        ) : turn ? (
          <>
            <p className="muted" style={{ marginBottom: 12 }}>
              No Inspection has run for this Turn yet.
            </p>
            <div className="panel turn-timeline">
              <Timeline entries={timeline} selectedId={null} onSelect={() => undefined} />
            </div>
          </>
        ) : (
          <p className="muted row">
            <SpinnerIcon className="vicon" /> Loading Turn…
          </p>
        )}
      </div>
    );
  }

  const report = selected;
  const isLatest = report === latest;
  const analysing = report.status === 'inspecting';
  const actionable = isLatest && report.status === 'awaiting_confirmation';
  const angleName = angleChoice?.inspectionId === report.inspection_id ? angleChoice.angle : defaultAngle(report);
  const angle = report.angles.find((a) => a.angle === angleName) ?? report.angles[0];
  const open = openFindings(report);
  const allTargets = confirmAllTargets(report);
  const outsideInAll = allTargets.filter(isOutsideBoundary).length;
  const tone = report.status === 'confirmed' ? 'confirmed' : analysing ? 'busy' : verdictTone(report.verdict, report.highest_open_severity);

  const selectInspection = (id: string) => navigate(turnHref(turnId, id));
  const selectAngle = (a: AngleName) => {
    setSelectedFindingId(null);
    setAngleChoice({ inspectionId: report.inspection_id, angle: a });
  };
  const selectFinding = (f: Finding, scrollCard: boolean) => {
    setAngleChoice({ inspectionId: report.inspection_id, angle: f.angle });
    setSelectedFindingId(f.finding_id);
    if (scrollCard) {
      document.querySelector(`[data-finding="${CSS.escape(f.finding_id)}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  };

  /** Run one action against the API, then show its Report and any outcome notice. */
  const act = async (
    label: string,
    context: ActionContext,
    fn: () => Promise<Report>,
    after?: (result: Report) => Notice | null,
    keepAngle?: AngleName,
  ): Promise<boolean> => {
    if (busy) return false;
    if (person.name === '') {
      setNotice({ tone: 'error', title: 'Enter your name first', text: 'Every Confirmation records who made it. Type your name next to the role switch.' });
      return false;
    }
    setBusy(label);
    setNotice(null);
    try {
      const result = await fn();
      await load();
      refreshState();
      if (keepAngle) setAngleChoice({ inspectionId: result.inspection_id, angle: keepAngle });
      if (result.inspection_id !== report.inspection_id) navigate(turnHref(turnId, result.inspection_id));
      setNotice(after?.(result) ?? null);
      return true;
    } catch (e) {
      setNotice({ tone: 'error', title: 'Not done', text: describeError(e, context) });
      return false;
    } finally {
      setBusy(null);
    }
  };

  const confirm = (f: Finding, request: ConfirmRequest) => {
    const holdRemoval = f.severity === 'HOLD' && request.outcome === 'removed';
    void act(
      holdRemoval
        ? `Re-inspecting ${f.angle}: capturing a new frame and checking that the item is gone…`
        : 'Recording Confirmation…',
      f.severity === 'HOLD' ? 'hold' : 'finding',
      () => api.confirmFinding(report.inspection_id, f.finding_id, { ...request, ...person }),
      (result) => {
        if (holdRemoval) {
          return holdRemovalOutcome(f, result) === 'cleared'
            ? {
                tone: 'ok',
                title: `${f.angle} re-inspected: the item is gone. HOLD cleared.`,
                text: `Recorded as removed by ${personLabel(person)}. The new on-demand Inspection is shown.`,
              }
            : {
                tone: 'warn',
                title: `${f.angle} re-inspected: the item is still there. The HOLD stays open.`,
                text: 'No Confirmation was recorded. Remove the item, then acknowledge and confirm again.',
              };
        }
        if (request.outcome === 'acknowledged') {
          return { tone: 'info', title: 'HOLD acknowledged: someone is going to it.', text: 'When the item is off the stand, press "Removed" to re-inspect the Angle.' };
        }
        return null;
      },
      holdRemoval ? f.angle : undefined,
    );
  };

  const reinspect = (a: AngleName) =>
    void act(
      `Re-inspecting ${a}: capturing a new frame and analysing it…`,
      'reinspect',
      () => api.reinspectAngle(report.inspection_id, a, person),
      (result) => {
        const o = reinspectOutcome(a, result);
        if (!o.usable) {
          return {
            tone: 'warn',
            title: `${a} re-inspected: still unusable (${unusableReasonLabel(o.reason).toLowerCase()}).`,
            text: 'Try again, or a Ramp Lead records it as checked by eye.',
          };
        }
        return o.openCount > 0
          ? { tone: 'warn', title: `${a} re-inspected: ${plural(o.openCount, 'open Finding')}.`, text: 'The new on-demand Inspection is shown.' }
          : { tone: 'ok', title: `${a} re-inspected: usable, no open Findings.`, text: 'The new on-demand Inspection is shown.' };
      },
      a,
    );

  const checkedByEye = (a: AngleName) =>
    void act(
      'Recording checked by eye…',
      'checked_by_eye',
      () => api.checkedByEye(report.inspection_id, a, person),
      () => ({ tone: 'ok', title: `${a} recorded as checked by eye by ${personLabel(person)}.` }),
    );

  const confirmAll = () => {
    setConfirmingAll(false);
    void act('Recording Confirmations…', 'finding', () => api.confirmAll(report.inspection_id, person), (result) => {
      const left = openFindings(result).length;
      return {
        tone: 'ok',
        title: `${plural(allTargets.length, 'Finding')} confirmed as removed.`,
        text: left > 0 ? `${plural(left, 'HOLD Finding')} still open: a Ramp Lead confirms each one.` : undefined,
      };
    });
  };

  const signoff = async () => {
    if (busy) return;
    if (person.name === '') {
      setSignoffError('Enter your name next to the role switch before signing off.');
      return;
    }
    setBusy('Recording sign-off…');
    setSignoffError(null);
    try {
      await api.signoff(report.inspection_id, person);
      await load();
      refreshState();
      setSignoffOpen(false);
      setNotice({ tone: 'ok', title: `Inspection signed off by ${personLabel(person)}.`, text: `Gate ${report.gate} is confirmed by a person.` });
    } catch (e) {
      setSignoffError(describeError(e, 'signoff'));
    } finally {
      setBusy(null);
    }
  };

  const inspectNow = () =>
    void act('Starting an on-demand Inspection…', 'reinspect', () => api.inspectGate(turn.gate, { kind: 'on_demand' }));

  const angleFindings = numbered.filter((n) => n.finding.angle === angleName);
  // With nothing picked, the first Finding of the Angle on screen is expanded (open ones first).
  const shownFindingId =
    (selectedFindingId && report.findings.some((f) => f.finding_id === selectedFindingId) ? selectedFindingId : null) ??
    (angleFindings.find((n) => isFindingOpen(n.finding)) ?? angleFindings[0])?.finding.finding_id ??
    null;

  return (
    <div>
      <div className="turn-head">
        <a className="btn" href={OVERVIEW_HREF}>
          ‹ Gates
        </a>
        <span className="gate">{turn.gate}</span>
        <div>
          <b>
            {turn.flight ?? gate?.flight ?? turn.turn_id}
            {turn.aircraft_type ? ` · ${turn.aircraft_type}` : ''}
          </b>
          <div className="muted small">Turn {turn.turn_id}</div>
        </div>
        {gate && (
          <span className={`status-line tone-${gate.tone}`}>
            <ToneIcon tone={gate.tone} />
            {gate.statusLabel}
          </span>
        )}
        {gate?.pushbackText && <span className={`num${gate.pushbackOverdue ? ' overdue' : ''}`}>{gate.pushbackText}</span>}
        <span className="spacer" />
        <button type="button" onClick={inspectNow} disabled={busy !== null || !latest || latest.status === 'inspecting' || gateState?.status === 'departed' || !gateState}>
          Run on-demand Inspection
        </button>
      </div>

      <div className="turn-grid">
        <nav className="panel turn-timeline" aria-label="Turn timeline">
          <h2 className="section-title">Turn timeline</h2>
          <Timeline entries={timeline} selectedId={report.inspection_id} onSelect={selectInspection} />
        </nav>

        <div className="turn-main">
          {!isLatest && latest && (
            <div className="banner info">
              <span className="grow">
                <strong>This is an earlier Inspection, shown as a record.</strong>
                Confirmations are made on the latest Inspection of the Turn.
              </span>
              <button type="button" onClick={() => selectInspection(latest.inspection_id)}>
                Open latest Inspection
              </button>
            </div>
          )}

          <div className={`verdict-bar tone-${tone}`} data-verdict={report.verdict ?? 'pending'}>
            {analysing || !report.verdict ? (
              <>
                <span className="verdict-word">
                  <SpinnerIcon /> Inspecting
                </span>
                <AdvisoryTag />
                <span className="muted">Verdict pending. The 6 Angles are being analysed.</span>
              </>
            ) : (
              <>
                <span className="muted small">Verdict</span>
                <span style={{ fontSize: 24, display: 'inline-flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                  <VerdictMark verdict={report.verdict} confirmed={report.status === 'confirmed'} />
                </span>
                {report.highest_open_severity && (
                  <span className="row small muted">
                    <SeverityBadge severity={report.highest_open_severity} big /> highest open severity
                  </span>
                )}
              </>
            )}
            <span className="muted small">
              {KIND_LABEL[report.kind]} · captured {formatTime(report.captured_at)}
            </span>
            <span className="spacer" />
            {report.inspection_signoff ? (
              <span className="row">
                <CheckCircleIcon className="vicon ok-ink" />
                <span>
                  Signed off by <b>{personLabel(report.inspection_signoff.by)}</b> at {formatTime(report.inspection_signoff.at)}
                </span>
              </span>
            ) : actionable ? (
              <button type="button" className="good" disabled={busy !== null} onClick={() => { setSignoffError(null); setSignoffOpen(true); }}>
                Sign off Inspection…
              </button>
            ) : null}
          </div>

          {busy && (
            <div className="busy-bar" role="status">
              <SpinnerIcon /> {busy}
            </div>
          )}
          {notice && (
            <div className={`banner ${notice.tone}`} role={notice.tone === 'error' ? 'alert' : 'status'} style={{ marginBottom: 0 }}>
              <span className="grow">
                <strong>{notice.title}</strong>
                {notice.text}
              </span>
              <button type="button" className="compact quiet" onClick={() => setNotice(null)}>
                Dismiss
              </button>
            </div>
          )}

          {angle && (
            <section className="panel" aria-label="Angle viewer">
              <div className="viewer-cap">
                <h2>{angle.angle} Angle</h2>
                <span className="muted small">
                  {angle.analysis ? (ANALYSIS_LABEL[angle.analysis] ?? angle.analysis) : ''}
                  {angle.source_inspection_id && angle.source_inspection_id !== report.inspection_id ? ' · frame inherited from an earlier Inspection' : ''}
                  {angle.reference_url ? '' : ' · no reference frame'}
                </span>
              </div>
              <AngleFrame
                angle={angle}
                findings={analysing ? [] : angleFindings}
                variant="large"
                selectedId={shownFindingId}
                hotId={hotFindingId}
                onHover={setHotFindingId}
                onSelect={(id) => {
                  const f = report.findings.find((x) => x.finding_id === id);
                  if (f) selectFinding(f, true);
                }}
              />
              <Credit attribution={angle.attribution} />

              <div className="angle-actions">
                {angle.status === 'unusable' ? (
                  <p className="angle-note">
                    <b>
                      <EyeOffIcon className="vicon" /> {angle.angle} is unusable: {unusableReasonLabel(angle.unusable_reason).toLowerCase()}.
                    </b>{' '}
                    {angle.checked_by_eye
                      ? `Checked by eye by ${personLabel(angle.checked_by_eye.by)} at ${formatTime(angle.checked_by_eye.at)}: this Angle was cleared by a person, not by the system.`
                      : 'The Inspection cannot be ALL CLEAR until it is re-inspected usable, or a Ramp Lead checks it by eye (FOD-R6).'}
                  </p>
                ) : (
                  <p className="angle-note muted small">
                    {angleFindings.length > 0 ? `${plural(angleFindings.length, 'Finding')} in this Angle.` : 'No Findings in this Angle.'}
                  </p>
                )}
                {actionable && (
                  <>
                    <button type="button" disabled={busy !== null} onClick={() => reinspect(angle.angle)}>
                      Re-inspect {angle.angle}
                    </button>
                    {isAngleUnresolved(angle) && (
                      <button
                        type="button"
                        disabled={busy !== null}
                        title="Ramp Lead only"
                        onClick={() => checkedByEye(angle.angle)}
                      >
                        Record checked by eye{person.role === 'ramp_lead' ? '' : ' (Ramp Lead)'}
                      </button>
                    )}
                  </>
                )}
              </div>

              <div className="grid6" role="group" aria-label="The 6 Angles">
                {report.angles.map((a) => {
                  const list = analysing ? [] : numbered.filter((n) => n.finding.angle === a.angle);
                  const openHere = list.filter((n) => isFindingOpen(n.finding));
                  const top = openHere.reduce<Finding | null>(
                    (best, n) => (!best || rank(n.finding) > rank(best) ? n.finding : best),
                    null,
                  );
                  return (
                    <button
                      key={a.angle}
                      type="button"
                      className="thumb-btn"
                      aria-pressed={a.angle === angleName}
                      aria-label={`${a.angle} Angle: ${thumbState(a.status === 'unusable', a.checked_by_eye !== null, a.unusable_reason, openHere.length, list.length)}`}
                      onClick={() => selectAngle(a.angle)}
                      data-angle={a.angle}
                    >
                      <AngleFrame angle={a} findings={list} variant="thumb" selectedId={shownFindingId} hotId={hotFindingId} />
                      <span className="thumb-label">
                        {a.angle}
                        <span
                          className={`thumb-state tone-${a.status === 'unusable' ? (a.checked_by_eye ? 'clear' : 'incomplete') : top ? verdictTone(null, top.severity) : 'idle'}`}
                        >
                          {a.status === 'unusable' && !a.checked_by_eye ? <EyeOffIcon /> : null}
                          {thumbState(a.status === 'unusable', a.checked_by_eye !== null, a.unusable_reason, openHere.length, list.length)}
                        </span>
                      </span>
                      <Credit attribution={a.attribution} compact />
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          <div className="lower">
            {!analysing && <DetailsPanel report={report} api={api} />}
            {!analysing && (
              <AssistantPanel
                key={report.inspection_id}
                api={api}
                report={report}
                canReinspect={actionable}
                busy={busy !== null}
                onReinspect={reinspect}
              />
            )}
          </div>
          <TurnRecord api={api} turnId={turnId} />
        </div>

        <section className="panel turn-side" aria-label="Findings">
          <div className="findings-head">
            <h2>
              Findings ({report.findings.length})
              {report.findings.length > 0 ? <span className="muted small"> · {open.length} open</span> : null}
            </h2>
            {actionable && allTargets.length > 0 && !confirmingAll && (
              <button
                type="button"
                className="good"
                disabled={busy !== null}
                onClick={() => (outsideInAll > 0 ? setConfirmingAll(true) : confirmAll())}
              >
                Confirm all removed ({allTargets.length})
              </button>
            )}
          </div>
          {confirmingAll && (
            <div className="banner warn">
              <span className="grow">
                <strong>
                  {outsideInAll} of these {allTargets.length} Findings {outsideInAll === 1 ? 'is' : 'are'} outside the gate safety envelope.
                </strong>
                "Confirm all" records {outsideInAll === 1 ? 'it' : 'them'} as reported, not removed by the ramp crew. Only continue if
                that report has been made to Ramp 1 control / Airport Operations.
                <span className="row" style={{ marginTop: 8 }}>
                  <button type="button" className="good" onClick={confirmAll}>
                    Yes, confirm all {allTargets.length}
                  </button>
                  <button type="button" onClick={() => setConfirmingAll(false)}>
                    Cancel
                  </button>
                </span>
              </span>
            </div>
          )}
          {analysing ? (
            <p className="empty">Analysis in progress. Findings appear when the Verdict is ready.</p>
          ) : report.findings.length === 0 ? (
            <p className="empty">
              No Findings in this Inspection.
              {report.verdict === 'INCOMPLETE' ? ' The Verdict is INCOMPLETE because an Angle is unusable: open it in the viewer.' : ''}
            </p>
          ) : (
            <ol className="flist">
              {numbered.map(({ finding, number }) => (
                <FindingCard
                  key={finding.finding_id}
                  finding={finding}
                  number={number}
                  rules={rules}
                  person={person}
                  actionable={actionable}
                  busy={busy !== null}
                  selected={finding.finding_id === shownFindingId}
                  hot={finding.finding_id === hotFindingId}
                  attribution={report.angles.find((a) => a.angle === finding.angle)?.attribution ?? null}
                  onSelect={() => selectFinding(finding, false)}
                  onHover={(hot) => setHotFindingId(hot ? finding.finding_id : null)}
                  onConfirm={(request) => confirm(finding, request)}
                />
              ))}
            </ol>
          )}
        </section>
      </div>

      {signoffOpen && actionable && (
        <SignoffDialog
          report={report}
          numbered={numbered}
          person={person}
          busy={busy !== null}
          error={signoffError}
          onConfirm={() => void signoff()}
          onClose={() => setSignoffOpen(false)}
        />
      )}
    </div>
  );
}

function rank(f: Finding): number {
  return f.severity === 'HOLD' ? 3 : f.severity === 'REMOVE' ? 2 : 1;
}

function thumbState(unusable: boolean, byEye: boolean, reason: string | null, openCount: number, total: number): string {
  if (unusable) return byEye ? 'By eye' : unusableReasonLabel(reason);
  if (openCount > 0) return `${openCount} open`;
  if (total > 0) return `${total} confirmed`;
  return 'Clear';
}
