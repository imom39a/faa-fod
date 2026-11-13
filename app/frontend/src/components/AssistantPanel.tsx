import { useState } from 'react';
import type { Api } from '../api/client';
import { describeError } from '../api/errors';
import { ANGLE_ORDER, type AngleName, type AssistantResponse, type Report } from '../api/types';

type Exchange = { question: string; answer: AssistantResponse | null; error: string | null };

const QUICK_PROMPTS = [
  'Summarise this Inspection for the Ramp Lead.',
  'Which Angles should be re-inspected, and why?',
  'Draft a report to Airport Operations.',
];

type Props = {
  api: Api;
  report: Report;
  /** Re-inspection is offered only on the latest, unsigned Inspection. */
  canReinspect: boolean;
  busy: boolean;
  onReinspect: (angle: AngleName) => void;
};

/** Assistant for the selected Inspection. It suggests; a person clicks to act. */
export function AssistantPanel({ api, report, canReinspect, busy, onReinspect }: Props) {
  const [message, setMessage] = useState('');
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [pending, setPending] = useState(false);
  const [copied, setCopied] = useState<number | null>(null);

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || pending) return;
    setPending(true);
    setMessage('');
    const index = exchanges.length;
    setExchanges((prev) => [...prev, { question: q, answer: null, error: null }]);
    try {
      const answer = await api.assistant({ inspection_id: report.inspection_id, message: q });
      setExchanges((prev) => prev.map((x, i) => (i === index ? { ...x, answer } : x)));
    } catch (e) {
      setExchanges((prev) => prev.map((x, i) => (i === index ? { ...x, error: describeError(e, 'assistant') } : x)));
    } finally {
      setPending(false);
    }
  };

  const copy = async (text: string, index: number) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(index);
    } catch {
      setCopied(null);
    }
  };

  return (
    <section className="panel" aria-label="Assistant">
      <h2 className="section-title">Assistant for this Inspection</h2>
      <p className="muted small">Answers are advisory. Nothing is re-inspected or confirmed until you press a button.</p>
      <div className="row" style={{ marginTop: 8 }}>
        {QUICK_PROMPTS.map((p) => (
          <button key={p} type="button" className="compact" disabled={pending} onClick={() => void ask(p)}>
            {p}
          </button>
        ))}
      </div>

      <div className="chat" aria-live="polite">
        {exchanges.map((x, i) => (
          <div key={i} style={{ display: 'contents' }}>
            <div className="msg user">
              <span className="who">You</span>
              {x.question}
            </div>
            <div className="msg" data-assistant-reply>
              <span className="who">Assistant</span>
              {x.error ? <span role="alert">{x.error}</span> : x.answer ? x.answer.reply : 'Thinking…'}
              {x.answer && x.answer.suggested_reinspect_angles.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <b>Suggested re-inspection:</b>
                  <div className="row" style={{ marginTop: 6 }}>
                    {x.answer.suggested_reinspect_angles.map((a) => {
                      const known = (ANGLE_ORDER as readonly string[]).includes(a);
                      return (
                        <button
                          key={a}
                          type="button"
                          className="compact"
                          disabled={!known || !canReinspect || busy}
                          title={canReinspect ? `Run an on-demand Inspection of ${a}` : 'Only the latest, unsigned Inspection can be re-inspected'}
                          onClick={() => onReinspect(a as AngleName)}
                        >
                          Re-inspect {a}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
              {x.answer?.draft_report && (
                <div className="draft">
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <b>Drafted report</b>
                    <button type="button" className="compact" onClick={() => void copy(x.answer?.draft_report ?? '', i)}>
                      {copied === i ? 'Copied' : 'Copy text'}
                    </button>
                  </div>
                  <pre data-draft-report>{x.answer.draft_report}</pre>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask(message);
        }}
      >
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Ask about this Inspection"
          aria-label="Message to the assistant"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void ask(message);
            }
          }}
        />
        <div className="row" style={{ justifyContent: 'flex-end', marginTop: 8 }}>
          <button type="submit" className="primary" disabled={pending || message.trim() === ''}>
            {pending ? 'Asking…' : 'Ask'}
          </button>
        </div>
      </form>
    </section>
  );
}
