import { describe, expect, it } from 'vitest';
import { isDrawableBox, iou, rectCentre, scaleBox } from './boxes';

const HD = { width: 1600, height: 900 };

describe('scaleBox', () => {
  it('scales original-image pixels to the displayed size', () => {
    expect(scaleBox([400, 300, 800, 600], HD, { width: 800, height: 450 })).toEqual({ left: 200, top: 150, width: 200, height: 150 });
  });

  it('keeps the box centred on the debris at any display size', () => {
    const bolt: [number, number, number, number] = [943, 546, 977, 578];
    for (const width of [1200, 808, 261, 140]) {
      const display = { width, height: (width * 9) / 16 };
      const c = rectCentre(scaleBox(bolt, HD, display, 12));
      expect(c.x).toBeCloseTo((960 * width) / 1600, 6);
      expect(c.y).toBeCloseTo((562 * display.height) / 900, 6);
    }
  });

  it('handles a 4K original shown on a small thumbnail', () => {
    const r = scaleBox([1920, 1080, 1960, 1100], { width: 3840, height: 2160 }, { width: 192, height: 108 }, 12);
    expect(r.width).toBe(12);
    expect(r.height).toBe(12);
    expect(rectCentre(r)).toEqual({ x: 97, y: 54.5 });
  });

  it('pads a small box to the minimum on-screen size, per axis', () => {
    const r = scaleBox([100, 100, 110, 400], HD, { width: 800, height: 450 }, 32);
    expect(r.width).toBe(32);
    expect(r.height).toBe(150);
    expect(rectCentre(r).x).toBeCloseTo(52.5);
  });

  it('does not pad a box that is already large enough', () => {
    expect(scaleBox([0, 0, 800, 450], HD, { width: 800, height: 450 }, 32)).toEqual({ left: 0, top: 0, width: 400, height: 225 });
  });

  it('keeps a padded box inside the image at the edges', () => {
    const topLeft = scaleBox([0, 0, 4, 4], HD, { width: 800, height: 450 }, 32);
    expect(topLeft).toEqual({ left: 0, top: 0, width: 32, height: 32 });
    const bottomRight = scaleBox([1596, 896, 1600, 900], HD, { width: 800, height: 450 }, 32);
    expect(bottomRight.left + bottomRight.width).toBe(800);
    expect(bottomRight.top + bottomRight.height).toBe(450);
  });

  it('accepts corners in either order', () => {
    expect(scaleBox([800, 600, 400, 300], HD, { width: 800, height: 450 })).toEqual(scaleBox([400, 300, 800, 600], HD, { width: 800, height: 450 }));
  });

  it('returns an empty rect before the image has been measured', () => {
    expect(scaleBox([1, 2, 3, 4], HD, { width: 0, height: 0 }, 32)).toEqual({ left: 0, top: 0, width: 0, height: 0 });
  });
});

describe('isDrawableBox', () => {
  it('rejects empty and malformed boxes (dismissed Candidates may have none)', () => {
    expect(isDrawableBox([])).toBe(false);
    expect(isDrawableBox(null)).toBe(false);
    expect(isDrawableBox([1, 2, 1, 5])).toBe(false);
    expect(isDrawableBox([1, 2, Number.NaN, 5])).toBe(false);
    expect(isDrawableBox([1, 2, 3, 4])).toBe(true);
  });
});

describe('iou', () => {
  it('is 1 for the same box and 0 for disjoint boxes', () => {
    expect(iou([0, 0, 10, 10], [0, 0, 10, 10])).toBe(1);
    expect(iou([0, 0, 10, 10], [20, 20, 30, 30])).toBe(0);
    expect(iou([0, 0, 10, 10], [5, 0, 15, 10])).toBeCloseTo(1 / 3);
  });
});
