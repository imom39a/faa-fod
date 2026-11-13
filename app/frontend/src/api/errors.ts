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
