import { describe, expect, it } from 'vitest';
import { CREW_HREF, SETTINGS_HREF, parseRoute, turnHref } from './route';

describe('router: Crew and Tasks and Finding links', () => {
  it('parses the Crew and Tasks route', () => {
    expect(parseRoute(CREW_HREF)).toEqual({ name: 'crew' });
  });

  it('parses the Settings route', () => {
    expect(parseRoute(SETTINGS_HREF)).toEqual({ name: 'settings' });
  });

  it('keeps old Turn links working', () => {
    expect(parseRoute('#/turn/turn-T5-1')).toEqual({ name: 'turn', turnId: 'turn-T5-1', inspectionId: null, finding: null });
    expect(parseRoute('#/turn/turn-T5-1/insp-009')).toEqual({ name: 'turn', turnId: 'turn-T5-1', inspectionId: 'insp-009', finding: null });
    expect(turnHref('turn-T5-1')).toBe('#/turn/turn-T5-1');
    expect(turnHref('turn-T5-1', 'insp-009')).toBe('#/turn/turn-T5-1/insp-009');
  });

  it('round-trips a Finding in a Turn link', () => {
    const href = turnHref('turn-T5-1', 'insp-009', 'F2');
    expect(href).toBe('#/turn/turn-T5-1/insp-009?finding=F2');
    expect(parseRoute(href)).toEqual({ name: 'turn', turnId: 'turn-T5-1', inspectionId: 'insp-009', finding: 'F2' });
  });
});
