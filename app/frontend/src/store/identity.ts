import { useCallback, useState } from 'react';
import type { Person, Role } from '../api/types';

const STORAGE_KEY = 'fodgate.identity.v1';

/** The role switch stands in for sign-in: a role, and a name per role. */
export type Identity = { role: Role; names: Record<Role, string> };

export const DEFAULT_IDENTITY: Identity = {
  role: 'ramp_agent',
  names: { ramp_agent: 'R. Ortiz', ramp_lead: 'K. Bauer' },
};

export function parseIdentity(raw: string | null): Identity {
  if (!raw) return DEFAULT_IDENTITY;
  try {
    const v = JSON.parse(raw) as Partial<Identity> | null;
    const role: Role = v?.role === 'ramp_lead' ? 'ramp_lead' : 'ramp_agent';
    return {
      role,
      names: {
        ramp_agent: typeof v?.names?.ramp_agent === 'string' ? v.names.ramp_agent : DEFAULT_IDENTITY.names.ramp_agent,
        ramp_lead: typeof v?.names?.ramp_lead === 'string' ? v.names.ramp_lead : DEFAULT_IDENTITY.names.ramp_lead,
      },
    };
  } catch {
    return DEFAULT_IDENTITY;
  }
}

function load(): Identity {
  try {
    return parseIdentity(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return DEFAULT_IDENTITY;
  }
}

function save(identity: Identity): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(identity));
  } catch {
    // Storage unavailable (private window): the choice lasts for this page only.
  }
}

export function useIdentity(): {
  identity: Identity;
  person: Person;
  setRole(role: Role): void;
  setName(name: string): void;
} {
  const [identity, setIdentity] = useState<Identity>(load);
  const update = useCallback((fn: (prev: Identity) => Identity) => {
    setIdentity((prev) => {
      const next = fn(prev);
      save(next);
      return next;
    });
  }, []);
  const setRole = useCallback((role: Role) => update((prev) => ({ ...prev, role })), [update]);
  const setName = useCallback(
    (name: string) => update((prev) => ({ ...prev, names: { ...prev.names, [prev.role]: name } })),
    [update],
  );
  return { identity, person: { role: identity.role, name: identity.names[identity.role].trim() }, setRole, setName };
}
