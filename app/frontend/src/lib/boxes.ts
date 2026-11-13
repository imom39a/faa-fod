import type { BBox } from '../api/types';

export type Size = { width: number; height: number };
export type Rect = { left: number; top: number; width: number; height: number };

/**
 * Map a Finding box from original-image pixels to the displayed image.
 *
 * The image is assumed to fill the display area exactly (the frame takes the
 * image's aspect ratio). Boxes smaller than `minSize` on screen are grown
 * around their centre so a bolt in a 4K frame is still visible and tappable on
 * a thumbnail; the result is kept inside the display area.
 */
export function scaleBox(bbox: BBox, image: Size, display: Size, minSize = 0): Rect {
  if (image.width <= 0 || image.height <= 0 || display.width <= 0 || display.height <= 0) {
    return { left: 0, top: 0, width: 0, height: 0 };
  }
  const sx = display.width / image.width;
  const sy = display.height / image.height;
  const x1 = Math.min(bbox[0], bbox[2]) * sx;
  const x2 = Math.max(bbox[0], bbox[2]) * sx;
  const y1 = Math.min(bbox[1], bbox[3]) * sy;
  const y2 = Math.max(bbox[1], bbox[3]) * sy;

  const width = Math.min(Math.max(x2 - x1, minSize), display.width);
  const height = Math.min(Math.max(y2 - y1, minSize), display.height);
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;
  const left = clamp(cx - width / 2, 0, display.width - width);
  const top = clamp(cy - height / 2, 0, display.height - height);
  return { left, top, width, height };
}

/** Centre of a rect, used by tests and by label placement. */
export function rectCentre(r: Rect): { x: number; y: number } {
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}

/** True when a bbox has four finite numbers and a positive area. */
export function isDrawableBox(bbox: readonly number[] | null | undefined): bbox is BBox {
  return (
    Array.isArray(bbox) &&
    bbox.length === 4 &&
    bbox.every((n) => Number.isFinite(n)) &&
    bbox[0] !== bbox[2] &&
    bbox[1] !== bbox[3]
  );
}

/** Intersection over union of two boxes in the same pixel space. */
export function iou(a: BBox, b: BBox): number {
  const ix = Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0]));
  const iy = Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  const inter = ix * iy;
  const union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter;
  return union > 0 ? inter / union : 0;
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(Math.max(v, lo), Math.max(lo, hi));
}
