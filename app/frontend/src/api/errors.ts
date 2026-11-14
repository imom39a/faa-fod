import { ApiError } from './client';

/** What the user was trying to do, so the message can say what to do next. */
export type ActionContext = 'hold' | 'checked_by_eye' | 'signoff' | 'finding' | 'reinspect' | 'demo' | 'assistant' | 'load';

/** A clear, user-facing message for every error code in the contract. */
export function describeError(err: unknown, context: ActionContext = 'load'): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : 'Something went wrong.';
  }
  switch (err.code) {
    case 'role_not_allowed':
      if (context === 'hold') {
        return 'A Ramp Lead is required: only a Ramp Lead can confirm a HOLD Finding. Hand over to the Ramp Lead, or switch role if that is you.';
      }
      if (context === 'checked_by_eye') {
        return 'A Ramp Lead is required: only a Ramp Lead can record an Angle as checked by eye.';
      }
      return 'A Ramp Lead is required for this action.';
    case 'hold_needs_acknowledge':
      return 'Acknowledge this HOLD first (someone is going to it), then record it as removed.';
    case 'open_findings':
      return 'Sign-off is blocked: this Inspection still has open Findings. Confirm each one first.';
    case 'unusable_angles':
      return 'Sign-off is blocked: an unusable Angle must be re-inspected, or checked by eye by a Ramp Lead.';
    case 'not_found':
      return 'That record was not found. It may have been replaced by a newer Inspection or the demo was reset.';
    case 'network':
      return 'The inspection service cannot be reached. Check that the backend is running; the dashboard keeps retrying.';
    default:
      return err.message || `The request was refused (${err.code}).`;
  }
}

/**
 * A user-facing message for a refusal from the always-on agent endpoints
 * (`/api/agent/*`). The server's own wording names the Task or Finding, so it is
 * kept wherever it says more than a fixed sentence could.
 */
export function describeAgentError(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : 'Something went wrong.';
  }
  const said = err.message ? ` (${err.message.replace(/\.$/, '')}.)` : '';
  switch (err.code) {
    case 'bad_credentials':
      return 'That PIN does not match the person you picked. Check the name and try again.';
    case 'not_signed_in':
      return 'You are not signed in, or the service was restarted. Sign in again.';
    case 'role_not_allowed':
      // A refused Handover is about the other person's role; the server's sentence says whose and which Tasks.
      if (/^Handover refused/.test(err.message)) return err.message;
      return `Your role cannot do this.${said}`;
    case 'hold_needs_acknowledge':
      return 'Acknowledge this HOLD first (someone is going to it), then record it as removed.';
    case 'open_findings':
      return `Sign-off is blocked: this Inspection still has open Findings.${said}`;
    case 'unusable_angles':
      return `Sign-off is blocked: an unusable Angle must be re-inspected, or checked by eye by a Ramp Lead.${said}`;
    case 'not_your_task':
      return `That Task is not yours.${said}`;
    case 'task_closed':
      return `That Task is already closed.${said}`;
    case 'nothing_to_answer':
      return 'There is no open question for you. It may have expired. Use the buttons on the Task instead.';
    case 'proposal_void':
      return `That question no longer applies: the Finding changed after it was asked. Nothing was recorded.${said}`;
    case 'open_hold':
      // The server names the Task and whose it is (a supervisor's /shift is about someone else), and says when the supervisor was told.
      return err.message || 'You hold an open HOLD Task. Hand it over before leaving.';
    case 'nothing_to_hand_over':
      return 'You have no open Tasks to hand over.';
    case 'already_confirmed':
      return 'This Finding already has a Confirmation. Nothing was changed.';
    case 'already_signed_off':
      return 'This Inspection is already signed off.';
    case 'angle_usable':
      return `That Angle is usable, so there is nothing to check by eye.${said}`;
    case 'inspection_in_progress':
    case 'inspection_running':
      return 'An Inspection is still running at this Gate. Try again when it finishes.';
    case 'invalid_command':
      return err.message || 'That command was not understood. Type /help for the list.';
    case 'invalid_request':
      return err.message || 'The request was not valid.';
    case 'refused':
      return err.message || 'The request was refused.';
    case 'not_found':
      return err.message || 'That Task, Finding or Gate was not found. It may have been replaced by a newer Inspection.';
    case 'network':
      return 'The inspection service cannot be reached. Check that the agent is running; this page keeps retrying.';
    default:
      return err.message || `The request was refused (${err.code}).`;
  }
}
