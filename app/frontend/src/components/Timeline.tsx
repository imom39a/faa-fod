import type { Report } from '../api/types';
import { formatTime } from '../lib/format';
import { KIND_LABEL } from '../lib/labels';
import { turnRecords, type InspectionRecord, type TimelineEntry } from '../lib/report';
import { VerdictMark, verdictTone } from './bits';
import { SpinnerIcon } from './icons';

type Props = { entries: TimelineEntry[]; selectedId: string | null; onSelect: (inspectionId: string) => void };

/** The Turn in time order: milestones, each Inspection, and what people recorded on it. */
export function Timeline({ entries, selectedId, onSelect }: Props) {
  const records = turnRecords(entries.flatMap((e) => (e.type === 'inspection' ? [e.report] : [])));
  return (
    <ol className="tl" aria-label="Inspection timeline">
      {entries.map((e) => {
        if (e.type === 'milestone') {
          return (
            <li key={e.key} className={`tl-milestone${e.done ? ' done' : ''}`}>
              <span className="dot" aria-hidden="true" />
              <span>
                {e.label}
                {e.done ? '' : ' (to come)'}
              </span>
            </li>
          );
        }
        if (e.type === 'scheduled') {
          return (
            <li key={e.key}>
              <div className="tl-item scheduled">
                <div className="tl-kind">{KIND_LABEL[e.kind]}</div>
                <div className="small">Scheduled, not run yet</div>
              </div>
            </li>
          );
        }
        return (
          <li key={e.key}>
            <InspectionItem
              report={e.report}
              records={records.get(e.report.inspection_id) ?? []}
              superseded={e.superseded} selected={e.report.inspection_id === selectedId} onSelect={onSelect} />
          </li>
        );
      })}
    </ol>
  );
}

function InspectionItem(props: { report: Report; records: InspectionRecord[]; superseded: boolean; selected: boolean; onSelect: (id: string) => void }) {
  const { report: r, records, superseded, selected, onSelect } = props;
  const tone = r.status === 'confirmed' ? 'confirmed' : verdictTone(r.verdict, r.highest_open_severity);
  return (
    <button
      type="button"
      className={`tl-item tone-${tone}${superseded ? ' superseded' : ''}`}
      aria-current={selected}
      onClick={() => onSelect(r.inspection_id)}
      data-inspection={r.inspection_id}
    >
      <div className="tl-kind">
        <span>{KIND_LABEL[r.kind] ?? r.kind}</span>
        <span className="muted num">{formatTime(r.captured_at)}</span>
      </div>
      <div className="tl-verdict">
        {r.status === 'inspecting' || !r.verdict ? (
          <span className="row muted">
            <SpinnerIcon className="vicon" /> Inspecting
          </span>
        ) : (
          <VerdictMark verdict={r.verdict} confirmed={r.status === 'confirmed'} />
        )}
        {superseded ? <span className="tag">Superseded</span> : null}
      </div>
      {records.length > 0 && (
        <ul className="tl-records">
          {records.map((rec) => (
            <li key={rec.key}>
              <b>{rec.text}</b>
              <br />
              {rec.who}, {formatTime(rec.at)}
            </li>
          ))}
        </ul>
      )}
    </button>
  );
}
