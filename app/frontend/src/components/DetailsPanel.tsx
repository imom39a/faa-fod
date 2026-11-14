import type { Api } from '../api/client';
import type { Report } from '../api/types';
import { formatMs, formatUsd, plural } from '../lib/format';
import { ANALYSIS_LABEL, humanise } from '../lib/labels';
import { costSummary } from '../lib/report';
import { useDeveloperMode } from '../store/settings';

/**
 * Run details: observations, dismissed Candidates, versions, export. Cost, tokens, LLM calls
 * and timings are developer details, shown only in developer mode (Settings).
 */
export function DetailsPanel({ report, api }: { report: Report; api: Api }) {
  const developer = useDeveloperMode();
  const cost = costSummary(report.run_metadata);
  const timings = Object.entries(report.run_metadata.timings_ms);
  const total = report.run_metadata.timings_ms.total;
  const notes = report.run_metadata.notes;
  const noteList = Array.isArray(notes) ? notes : notes ? [notes] : [];

  return (
    <section className="panel" aria-label="Inspection details">
      <h2 className="section-title">Inspection details</h2>
      {developer && (
        <div className="stat-row" aria-label="Cost and timing">
          <div className="stat">
            <b className="num">{formatUsd(cost.costUsd)}</b>
            <span>estimated cost</span>
          </div>
          <div className="stat">
            <b className="num">{total !== undefined ? formatMs(total) : 'n/a'}</b>
            <span>total time</span>
          </div>
          <div className="stat">
            <b className="num">{(cost.tokensIn + cost.tokensOut).toLocaleString()}</b>
            <span>
              tokens ({cost.calls} LLM {cost.calls === 1 ? 'call' : 'calls'})
            </span>
          </div>
        </div>
      )}
      <a className="btn compact" href={api.exportHref(report)} download={`${report.inspection_id}.json`}>
        Export report as JSON
      </a>

      <details className="block" open style={{ marginTop: 12 }}>
        <summary>Non-FOD observations ({report.observations.length})</summary>
        {report.observations.length === 0 ? (
          <p className="muted small">None. Snow, ice, spills and live wildlife are reported here, outside the Verdict (FOD-R7).</p>
        ) : (
          <ul className="plain-list">
            {report.observations.map((o, i) => (
              <li key={i}>
                <b>
                  {o.angle}: {humanise(o.kind)}.
                </b>{' '}
                {o.text} <span className="muted">No severity; kept out of the Verdict (FOD-R7).</span>
              </li>
            ))}
          </ul>
        )}
      </details>

      <details className="block">
        <summary>Dismissed Candidates ({report.dismissed_candidates.length})</summary>
        {report.dismissed_candidates.length === 0 ? (
          <p className="muted small">No Candidates were dismissed.</p>
        ) : (
          <ul className="plain-list">
            {report.dismissed_candidates.map((d, i) => (
              <li key={i}>
                <b>{d.angle}:</b> {d.reason}
                {d.bbox.length === 4 ? <span className="muted mono"> [{d.bbox.join(', ')}]</span> : null}
              </li>
            ))}
          </ul>
        )}
      </details>

      {developer && (
        <details className="block">
          <summary>Run metadata</summary>
          <table className="kv">
            <thead>
              <tr>
                <th>LLM call</th>
                <th>Model</th>
                <th className="r">Tokens in</th>
                <th className="r">Tokens out</th>
                <th className="r">Est. cost</th>
              </tr>
            </thead>
            <tbody>
              {report.run_metadata.llm_calls.length === 0 ? (
                <tr>
                  <td colSpan={5} className="muted">
                    No LLM calls recorded.
                  </td>
                </tr>
              ) : (
                report.run_metadata.llm_calls.map((c, i) => (
                  <tr key={i}>
                    <td>{humanise(c.purpose)}</td>
                    <td className="mono">{c.model}</td>
                    <td className="r num">{c.tokens_in.toLocaleString()}</td>
                    <td className="r num">{c.tokens_out.toLocaleString()}</td>
                    <td className="r num">{formatUsd(c.est_cost_usd)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          <table className="kv" style={{ marginTop: 10 }}>
            <tbody>
              <tr>
                <th>Stage timings</th>
                <td>{timings.length === 0 ? 'n/a' : timings.map(([k, v]) => `${k} ${formatMs(v)}`).join(' · ')}</td>
              </tr>
              <tr>
                <th>Local models</th>
                <td>{report.run_metadata.local_models.map((m) => `${m.name} (${m.version})`).join(', ') || 'none'}</td>
              </tr>
              <tr>
                <th>Analysis per Angle</th>
                <td>
                  {report.angles.map((a) => `${a.angle}: ${a.analysis ? (ANALYSIS_LABEL[a.analysis] ?? a.analysis) : 'n/a'}`).join(' · ')}
                </td>
              </tr>
              {noteList.length > 0 && (
                <tr>
                  <th>Notes</th>
                  <td>{noteList.join(' ')}</td>
                </tr>
              )}
            </tbody>
          </table>
        </details>
      )}

      <details className="block">
        <summary>Versions and identifiers</summary>
        <table className="kv">
          <tbody>
            <tr>
              <th>Rule set</th>
              <td className="mono">{report.rule_set_version}</td>
            </tr>
            <tr>
              <th>Report schema</th>
              <td className="mono">{report.schema_version}</td>
            </tr>
            <tr>
              <th>Inspection</th>
              <td className="mono">{report.inspection_id}</td>
            </tr>
            {report.parent_inspection_id && (
              <tr>
                <th>Re-inspection of</th>
                <td className="mono">{report.parent_inspection_id}</td>
              </tr>
            )}
            <tr>
              <th>Captured / analysed</th>
              <td className="mono">
                {report.captured_at} / {report.analysed_at ?? 'pending'}
              </td>
            </tr>
            <tr>
              <th>Missing Angles</th>
              <td>{report.missing_angles.length > 0 ? report.missing_angles.join(', ') : 'none'}</td>
            </tr>
            <tr>
              <th>Findings</th>
              <td>{plural(report.findings.length, 'Finding')}</td>
            </tr>
          </tbody>
        </table>
      </details>
    </section>
  );
}
