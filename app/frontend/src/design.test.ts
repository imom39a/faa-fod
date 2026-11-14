import { describe, expect, it } from 'vitest';

/**
 * Pins the rules of spec/design-system.md that code can check. If one of these fails,
 * fix the stylesheet or component, or change the design system and this test together.
 */
const CSS = import.meta.glob<string>('./**/*.css', { query: '?raw', import: 'default', eager: true });
const COMPONENTS = import.meta.glob<string>('./components/**/*.tsx', { query: '?raw', import: 'default', eager: true });

const HEX = /#[0-9a-fA-F]{3,8}\b/g;
const styles = CSS['./styles.css']!;
const rootBlock = styles.slice(styles.indexOf(':root {'), styles.indexOf('}', styles.indexOf(':root {')) + 1);

function token(name: string): string {
  const m = new RegExp(`--${name}:\\s*([^;]+);`).exec(rootBlock);
  if (!m) throw new Error(`styles.css :root has no --${name}`);
  return m[1]!.trim();
}

/** WCAG relative luminance of a #rrggbb colour. */
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

describe('design system', () => {
  it('keeps every literal colour in the :root tokens of styles.css', () => {
    const offenders: string[] = [];
    for (const [path, raw] of Object.entries(CSS)) {
      const css = path === './styles.css' ? raw.replace(rootBlock, '') : raw;
      for (const hex of css.match(HEX) ?? []) offenders.push(`${path}: ${hex}`);
    }
    expect(offenders).toEqual([]);
  });

  it('has no literal colours in components', () => {
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(COMPONENTS)) {
      for (const hex of source.match(/['"]#[0-9a-fA-F]{3,8}['"]/g) ?? []) offenders.push(`${path}: ${hex}`);
    }
    expect(offenders).toEqual([]);
  });

  it('keeps touch targets at 44px or more', () => {
    expect(parseInt(token('tap'), 10)).toBeGreaterThanOrEqual(44);
  });

  it('keeps text readable: 4.5:1 for ink on panels and for ink on each fill', () => {
    const pairs: [string, string][] = [
      ['text', 'bg'],
      ['text', 'panel'],
      ['muted', 'panel'],
      ['muted', 'panel-3'],
      ['faint', 'panel-2'],
      ['faint', 'panel-3'],
      ['hold', 'panel'],
      ['remove', 'panel'],
      ['advisory', 'panel'],
      ['incomplete', 'panel'],
      ['await', 'panel'],
      ['confirmed', 'panel'],
      ['hold-ink', 'hold'],
      ['remove-ink', 'remove'],
      ['caution-fill-ink', 'caution-fill'],
      ['confirmed-ink', 'confirmed'],
      ['accent-ink', 'accent'],
      ['on-tone', 'incomplete'],
      ['on-tone', 'advisory'],
      ['rail-muted', 'rail'],
    ];
    const failing = pairs.filter(([ink, surface]) => contrast(token(ink), token(surface)) < 4.5).map(([ink, surface]) => `${ink} on ${surface}`);
    expect(failing).toEqual([]);
  });
});
