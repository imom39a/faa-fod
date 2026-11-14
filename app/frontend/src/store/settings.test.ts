import { describe, expect, it } from 'vitest';
import { DEFAULT_SETTINGS, parseSettings } from './settings';

describe('settings', () => {
  it('starts with developer mode off', () => {
    expect(DEFAULT_SETTINGS.developerMode).toBe(false);
    expect(parseSettings(null)).toEqual({ developerMode: false });
  });

  it('reads a saved choice', () => {
    expect(parseSettings('{"developerMode":true}')).toEqual({
      developerMode: true,
    });
    expect(parseSettings('{"developerMode":false}')).toEqual({
      developerMode: false,
    });
  });

  it('treats anything else as off', () => {
    expect(parseSettings('not json')).toEqual({ developerMode: false });
    expect(parseSettings('{"developerMode":"yes"}')).toEqual({
      developerMode: false,
    });
    expect(parseSettings('null')).toEqual({ developerMode: false });
  });
});
