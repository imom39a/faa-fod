/**
 * The chat thread: merging inbox polls by cursor, and telling the kinds of
 * entry apart. A Report (what a person said) and a Confirmation (what was
 * recorded on the Inspection) must never look alike.
 */
import type { ChatMessage, Inbox } from '../api/agentTypes';

export type ThreadState = {
  /** Null until the first poll answers. */
  epoch: number | null;
  /** Pass as `after` on the next poll. */
  cursor: number;
  /** Oldest first, no duplicates. */
  messages: ChatMessage[];
};

export const EMPTY_THREAD: ThreadState = { epoch: null, cursor: 0, messages: [] };

/** Add newly polled messages: no duplicates, oldest first whatever order the polls answered in. */
export function mergeMessages(existing: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  if (incoming.length === 0) return existing;
  const seen = new Set(existing.map((m) => m.message_id));
  const fresh = incoming.filter((m) => {
    if (seen.has(m.message_id)) return false;
    seen.add(m.message_id);
    return true;
  });
  if (fresh.length === 0) return existing;
  const last = existing.at(-1)?.message_id ?? 0;
  const merged = [...existing, ...fresh];
  const inOrder = fresh.every((m, i) => m.message_id > (i === 0 ? last : fresh[i - 1]!.message_id));
  return inOrder ? merged : merged.sort((a, b) => a.message_id - b.message_id);
}

/**
 * Fold one inbox response into the thread. When the epoch changes (the demo was
 * reset) the thread is dropped and the cursor goes back to 0: the response was
 * asked for with the old cursor, so the caller polls again from the start.
 */
export function applyInbox(state: ThreadState, inbox: Pick<Inbox, 'epoch' | 'cursor' | 'messages'>): ThreadState {
  if (state.epoch !== null && inbox.epoch !== state.epoch) {
    return { epoch: inbox.epoch, cursor: 0, messages: [] };
  }
  return {
    epoch: inbox.epoch,
    cursor: Math.max(state.cursor, inbox.cursor),
    messages: mergeMessages(state.messages, inbox.messages),
  };
}

export type MessageVariant =
  /** What this person typed as plain text: a Report to the agent, never a Confirmation. */
  | 'my_report'
  /** A command this person pressed or typed. */
  | 'my_command'
  /** The Handover brief this person's `/handover` sent to someone else. It moves nothing until they accept. */
  | 'my_handover'
  /** A Confirmation was recorded. */
  | 'recorded'
  | 'refused'
  /** The agent logged a Report. Nothing was recorded on the Inspection. */
  | 'report_logged'
  | 'reinspecting'
  /** A re-inspection after "removed" still shows the object. */
  | 'still_there'
  /** A new photo came back; nothing was recorded by it. */
  | 'photo'
  | 'escalation'
  | 'hold_alert'
  /** A proposal: a question only this person can answer. */
  | 'question'
  | 'task'
  | 'plain';

/** How to show one message to the person whose thread it is. The wording is fixed by commands.py and dispatcher.py. */
export function messageVariant(m: ChatMessage, meId: string): MessageVariant {
  if (m.from === meId) {
    if (m.kind === 'command') return 'my_command';
    return m.proposal_id && /^Handover from /.test(m.text) ? 'my_handover' : 'my_report';
  }
  const t = m.text;
  if (/^Refused \(/.test(t)) return 'refused';
  if (/still shows the object/.test(t)) return 'still_there';
  if (/^Re-inspecting /.test(t)) return 'reinspecting';
  if (/(^|\s)Recorded: /.test(t) || /^Inspection signed off by /.test(t)) return 'recorded';
  if (m.proposal_id) return 'question';
  if (/^(Second call:|Escalation level \d)/.test(t)) return 'escalation';
  if (/^HOLD at /.test(t)) return 'hold_alert';
  if (/^(Logged|Declined)/.test(t)) return 'report_logged';
  if (/^New photo of /.test(t)) return 'photo';
  if (m.task_id) return 'task';
  return 'plain';
}

/** The `[y / n] (P-2)` hint is for a terminal; the chat page shows buttons. */
export function tidyMessageText(text: string): string {
  return text.replace(/\s*\[y \/ n\]\s*\(P-\d+\)/gi, '').trimEnd();
}

/**
 * The message for a Task outside the gate safety envelope ends with a drafted report ("To: Ramp 1 control ...")
 * after a blank line. Returns the two parts so the draft can be folded away, or null when there is no draft.
 */
export function splitDraftReport(text: string): { body: string; draft: string } | null {
  const at = text.indexOf('\n\nTo: ');
  if (at < 0) return null;
  return { body: text.slice(0, at).trimEnd(), draft: text.slice(at + 2).trim() };
}

/** "Refused (role_not_allowed): Only a Ramp Lead ..." → the code and the sentence. */
export function parseRefusal(text: string): { code: string; message: string } | null {
  const m = /^Refused \(([^)]+)\):\s*([\s\S]*)$/.exec(text);
  return m ? { code: m[1]!, message: m[2]! } : null;
}

/** True while the newest thing said to this person is "Re-inspecting ...": the new photo is still being taken. */
export function reinspectionRunning(messages: ChatMessage[], meId: string): ChatMessage | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i]!;
    if (m.to !== meId) continue;
    return messageVariant(m, meId) === 'reinspecting' ? m : null;
  }
  return null;
}

/** The newest message about each Task: the one that carries that Task's quick actions. */
export function latestMessagePerTask(messages: ChatMessage[], meId: string): Map<string, number> {
  const out = new Map<string, number>();
  for (const m of messages) {
    if (m.task_id && m.to === meId) out.set(m.task_id, m.message_id);
  }
  return out;
}

export function senderLabel(from: string, names: Record<string, string>): string {
  if (from === 'code') return 'System';
  if (from === 'agent') return 'Agent';
  if (from === 'timer') return 'Timer';
  return names[from] ?? from;
}
