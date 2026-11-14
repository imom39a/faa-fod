// PROTOTYPE (throwaway). Three layout and styling directions for the whole app,
// switchable with `?variant=A|B|C|0` on every existing route. `0` is the current app.
// The real pages render inside each variant's shell; only the shell, the home
// (Gates) page and the theme differ. Nothing here writes anything.
import { useEffect, useState, useSyncExternalStore, type ReactNode } from 'react';
import type { RosterPerson, Task } from '../api/agentTypes';
import type { DemoState, GateState, State } from '../api/types';
import { ChatIcon, GridIcon, ListIcon, TaskIcon } from '../components/icons';
import { formatClock } from '../lib/format';
import type { Tone } from '../lib/gates';
import { isActiveTask } from '../lib/taskActions';
import { CHAT_HREF, CREW_HREF, OVERVIEW_HREF, activityHref, type Route } from '../route';

/** Working product name. Change it here only. */
export const PRODUCT_NAME = 'StandClear';
export const PRODUCT_TAGLINE = 'Gate FOD inspection';

export const VARIANTS = [
  { key: 'A', name: 'Handheld, daylight' },
  { key: 'B', name: 'Ops console' },
  { key: 'C', name: 'Split view, night' },
  { key: '0', name: 'Current app' },
] as const;
export type VariantKey = (typeof VARIANTS)[number]['key'];

const EVENT = 'prototype-variant';

function readVariant(): VariantKey {
  const v = new URLSearchParams(window.location.search).get('variant');
  return VARIANTS.some((x) => x.key === v) ? (v as VariantKey) : 'A';
}

export function setVariant(v: VariantKey): void {
  const url = new URL(window.location.href);
  url.searchParams.set('variant', v);
  window.history.replaceState(null, '', url);
  window.dispatchEvent(new Event(EVENT));
}

export function useVariant(): VariantKey {
  const v = useSyncExternalStore(
    (cb) => {
      window.addEventListener(EVENT, cb);
      window.addEventListener('popstate', cb);
      return () => {
        window.removeEventListener(EVENT, cb);
        window.removeEventListener('popstate', cb);
      };
    },
    readVariant,
  );
  useEffect(() => {
    document.documentElement.dataset.variant = v;
    document.title = v === '0' ? 'Gate FOD Inspection' : PRODUCT_NAME;
  }, [v]);
  return v;
}

export type ShellProps = {
  route: Route;
  state: State | null;
  /** Who is signed in to the chat on this tab, if anyone. */
  person: RosterPerson | null;
  tasks: Task[];
  demoControls: ReactNode;
  roleSwitch: ReactNode;
  banners: ReactNode;
  /** The real page for every route except the Gates overview, which each variant draws itself. */
  children: ReactNode;
};

export function myOpen(person: RosterPerson | null, tasks: Task[]) {
  const open = person ? tasks.filter((t) => isActiveTask(t) && t.assignee_id === person.person_id) : [];
  return { open: open.length, holds: open.filter((t) => t.severity === 'HOLD').length };
}

export const NAV_ITEMS = [
  { key: 'gates', label: 'Gates', short: 'Gates', href: OVERVIEW_HREF, Icon: GridIcon, on: (r: Route) => r.name === 'overview' || r.name === 'turn' },
  { key: 'chat', label: 'My Tasks and chat', short: 'My Tasks', href: CHAT_HREF, Icon: ChatIcon, on: (r: Route) => r.name === 'chat' },
  { key: 'crew', label: 'Crew and Tasks', short: 'Crew', href: CREW_HREF, Icon: TaskIcon, on: (r: Route) => r.name === 'crew' },
  { key: 'activity', label: 'Activity', short: 'Activity', href: activityHref(), Icon: ListIcon, on: (r: Route) => r.name === 'activity' },
] as const;

/** Tones that mean "abnormal": the only ones a calm display should colour. */
export const ABNORMAL: ReadonlySet<Tone> = new Set<Tone>(['hold', 'remove', 'incomplete', 'advisory']);

/** "34" + "min", "due", "+5" + "min late". */
export function shortPush(g: GateState): { n: string; unit: string; overdue: boolean } | null {
  const m = g.turn?.minutes_to_pushback;
  if (m === null || m === undefined || !Number.isFinite(m) || g.status === 'departed' || g.status === 'idle') return null;
  const r = Math.round(m);
  if (r > 0) return { n: String(r), unit: 'min', overdue: false };
  if (r === 0) return { n: 'due', unit: 'now', overdue: true };
  return { n: `+${-r}`, unit: 'min late', overdue: true };
}

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 32 32" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 11V4h7M21 4h7v7M28 21v7h-7M11 28H4v-7" />
      <path d="M10 16.5l4.2 4.2L22.5 12" />
    </svg>
  );
}

/** Demo clock plus a tray holding the demo and role controls: demo scaffolding, kept out of the product chrome. */
export function DemoTray({ demo, demoControls, roleSwitch }: { demo: DemoState | null; demoControls: ReactNode; roleSwitch: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="demo-tray">
      <button type="button" className="demo-tray-btn" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="num">{demo ? formatClock(demo.t) : '-:--'}</span>
        <small>{!demo ? 'demo' : demo.playing ? `demo ${demo.speed}x` : 'demo paused'}</small>
      </button>
      {open ? (
        <div className="demo-tray-panel">
          <p className="small muted">Demo scaffolding. Not part of the product.</p>
          {demoControls}
          {roleSwitch}
        </div>
      ) : null}
    </div>
  );
}

/** Floating variant switcher. Not part of any design. */
export function PrototypeSwitcher({ current }: { current: VariantKey }) {
  const i = VARIANTS.findIndex((v) => v.key === current);
  const step = (d: number) => setVariant(VARIANTS[(i + d + VARIANTS.length) % VARIANTS.length]!.key);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)) return;
      if (e.key === 'ArrowLeft') step(-1);
      if (e.key === 'ArrowRight') step(1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });
  if (!import.meta.env.DEV) return null;
  return (
    <div className="proto-switch" role="group" aria-label="Prototype variant">
      <button type="button" onClick={() => step(-1)} aria-label="Previous variant">‹</button>
      <span>
        <b>{current === '0' ? 'Current' : current}</b> {VARIANTS[i]!.name}
      </span>
      <button type="button" onClick={() => step(1)} aria-label="Next variant">›</button>
    </div>
  );
}
