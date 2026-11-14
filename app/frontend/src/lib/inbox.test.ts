import { describe, expect, it } from 'vitest';
import type { ChatMessage } from '../api/agentTypes';
import { messageVariant, splitDraftReport, tidyMessageText } from './inbox';

const msg = (over: Partial<ChatMessage>): ChatMessage => ({
  message_id: 1,
  from: 'code',
  to: 'kim',
  kind: 'code',
  text: '',
  task_id: null,
  proposal_id: null,
  at: '2026-11-13T14:00:00Z',
  t: 0,
  ...over,
});

describe('splitDraftReport', () => {
  const text =
    'Task K-4: A loose strap lies outside the gate safety envelope at T8 (F3, ADVISORY). Do not remove it: it is not the ramp crew\'s to remove. ' +
    'Report it to Ramp 1 control (the shared taxilane between stands), then record who you told: /reported F3 ramp1. ' +
    'Draft to send (written by code from the camera images; check it first):\n\nTo: Ramp 1 control\nFrom: Ramp crew, Gate T8 (flight DL519)\n\n1. A loose strap.';

  it('separates the drafted report from the Task message and keeps its line breaks', () => {
    const parts = splitDraftReport(text)!;
    expect(parts.body.startsWith('Task K-4:')).toBe(true);
    expect(parts.body.endsWith('check it first):')).toBe(true);
    expect(parts.draft.split('\n')).toEqual(['To: Ramp 1 control', 'From: Ramp crew, Gate T8 (flight DL519)', '', '1. A loose strap.']);
  });

  it('leaves a message with no draft alone', () => {
    expect(splitDraftReport('Task K-3: Remove the bag tag (REMOVE, T5 CARGO, F2).')).toBeNull();
    expect(splitDraftReport('Handover from Okafor (Ramp Lead) to Reyes (Ramp Lead): 1 open Task.\n- K-1 ack_hold at T5')).toBeNull();
  });
});

describe('messageVariant: Handover and the new Report wording', () => {
  const brief = 'Handover from Okafor (Ramp Lead) to Reyes (Ramp Lead): 1 open Task.\n- K-1 ack_hold at T5 ENG-R F1 (HOLD)\nTake these over?   [y / n]   (P-2)';

  it('shows the brief as a question to the person asked, and not as a Report to the person who asked', () => {
    const m = msg({ from: 'okafor', to: 'reyes', proposal_id: 'P-2', text: brief });
    expect(messageVariant(m, 'reyes')).toBe('question');
    expect(messageVariant(m, 'okafor')).toBe('my_handover');
    expect(tidyMessageText(brief).split('\n')).toHaveLength(3);
    expect(tidyMessageText(brief).endsWith('Take these over?')).toBe(true);
  });

  it('never shows a logged Report or a declined Handover as recorded', () => {
    expect(messageVariant(msg({ text: 'Logged your Report on K-3. F2 stays open until a Confirmation is recorded.' }), 'kim')).toBe('report_logged');
    expect(messageVariant(msg({ text: 'Declined (P-2): no Task moved. Okafor has been told.' }), 'reyes')).toBe('report_logged');
    expect(messageVariant(msg({ text: 'Reyes declined your Handover (P-2). Your Tasks stay with you. You are still on shift.' }), 'okafor')).toBe('plain');
    expect(messageVariant(msg({ text: 'Recorded: F3 reported to Ramp 1 control by Kim (Ramp Agent). The ramp crew does not remove it.' }), 'kim')).toBe('recorded');
    expect(messageVariant(msg({ to: 'patel', task_id: 'K-9', text: 'The new photo of T1 NOSE still shows the object for F4. K-9 is open again: please go back and report here.' }), 'patel')).toBe('still_there');
  });
});
