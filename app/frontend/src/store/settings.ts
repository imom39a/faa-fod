import { useSyncExternalStore } from 'react';

const STORAGE_KEY = 'fodgate.settings.v1';

/**
 * Settings for this browser. Developer mode shows what only matters to whoever builds
 * or runs the app: model cost, tokens, LLM calls, timings and which model decided a
 * Finding. It never changes a Verdict, a Finding or what a person can do.
 */
export type Settings = { developerMode: boolean };

export const DEFAULT_SETTINGS: Settings = { developerMode: false };

export function parseSettings(raw: string | null): Settings {
  if (!raw) return DEFAULT_SETTINGS;
  try {
    const v = JSON.parse(raw) as Partial<Settings> | null;
    return { developerMode: v?.developerMode === true };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function load(): Settings {
  try {
    return parseSettings(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return DEFAULT_SETTINGS;
  }
}

let current: Settings | null = null;
const listeners = new Set<() => void>();

function snapshot(): Settings {
  if (current === null) current = load();
  return current;
}

export function setDeveloperMode(on: boolean): void {
  current = { ...snapshot(), developerMode: on };
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
  } catch {
    // Storage unavailable (private window): the choice lasts for this page only.
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Another tab changed the setting.
  const onStorage = (e: StorageEvent) => {
    if (e.key !== STORAGE_KEY) return;
    current = parseSettings(e.newValue);
    listener();
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', onStorage);
  };
}

export function useSettings(): Settings {
  return useSyncExternalStore(subscribe, snapshot, () => DEFAULT_SETTINGS);
}

/** True when developer details (cost, tokens, timings, models) should be shown. */
export function useDeveloperMode(): boolean {
  return useSettings().developerMode;
}
