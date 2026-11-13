import { useEffect, useState } from 'react';

export type Route = { name: 'overview' } | { name: 'turn'; turnId: string; inspectionId: string | null };

export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  if (parts[0] === 'turn' && parts[1]) {
    return { name: 'turn', turnId: parts[1], inspectionId: parts[2] ?? null };
  }
  return { name: 'overview' };
}

export function turnHref(turnId: string, inspectionId?: string | null): string {
  const base = `#/turn/${encodeURIComponent(turnId)}`;
  return inspectionId ? `${base}/${encodeURIComponent(inspectionId)}` : base;
}

export const OVERVIEW_HREF = '#/';

export function navigate(href: string): void {
  window.location.hash = href.replace(/^#/, '');
}

/** Minimal hash router: two views do not need a routing library. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}
