import { useEffect, useState } from 'react';

/** Filters of the activity log, kept in the address so a link (or the back button) restores them. */
export type ActivityRouteFilter = { gate: string | null; turnId: string | null; personId: string | null; kind: string | null };

export type Route =
  | { name: 'overview' }
  | { name: 'turn'; turnId: string; inspectionId: string | null; /** `?finding=<finding_id>`: the Finding a link opens (its ID in that Inspection). */ finding: string | null }
  | { name: 'chat' }
  | { name: 'crew' }
  | { name: 'activity'; filter: ActivityRouteFilter };

export function parseRoute(hash: string): Route {
  const [path = '', query = ''] = hash.replace(/^#\/?/, '').split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  if (parts[0] === 'turn' && parts[1]) {
    return { name: 'turn', turnId: parts[1], inspectionId: parts[2] ?? null, finding: new URLSearchParams(query).get('finding') || null };
  }
  if (parts[0] === 'chat') return { name: 'chat' };
  if (parts[0] === 'crew') return { name: 'crew' };
  if (parts[0] === 'activity') {
    const q = new URLSearchParams(query);
    const get = (k: string) => q.get(k) || null;
    return { name: 'activity', filter: { gate: get('gate'), turnId: get('turn'), personId: get('person'), kind: get('kind') } };
  }
  return { name: 'overview' };
}

export const CHAT_HREF = '#/chat';
export const CREW_HREF = '#/crew';

export function activityHref(filter: Partial<ActivityRouteFilter> = {}): string {
  const q = new URLSearchParams();
  if (filter.gate) q.set('gate', filter.gate);
  if (filter.turnId) q.set('turn', filter.turnId);
  if (filter.personId) q.set('person', filter.personId);
  if (filter.kind) q.set('kind', filter.kind);
  const s = q.toString();
  return s ? `#/activity?${s}` : '#/activity';
}

export function turnHref(turnId: string, inspectionId?: string | null, finding?: string | null): string {
  const base = `#/turn/${encodeURIComponent(turnId)}`;
  const path = inspectionId ? `${base}/${encodeURIComponent(inspectionId)}` : base;
  return finding ? `${path}?${new URLSearchParams({ finding })}` : path;
}

export const OVERVIEW_HREF = '#/';

export function navigate(href: string): void {
  window.location.hash = href.replace(/^#/, '');
}

/** Minimal hash router: four views do not need a routing library. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}
