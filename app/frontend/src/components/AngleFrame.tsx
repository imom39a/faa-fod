import { useLayoutEffect, useRef, useState } from 'react';
import type { Finding, ReportAngle } from '../api/types';
import { isDrawableBox, scaleBox, type Size } from '../lib/boxes';
import { severityTone } from '../lib/gates';
import { unusableReasonLabel } from '../lib/labels';
import { isFindingOpen } from '../lib/report';
import { EyeIcon, EyeOffIcon } from './icons';

export type NumberedFinding = { finding: Finding; number: number };

/** Smallest on-screen box edge, so a small item stays visible and tappable. */
export const MIN_BOX_LARGE = 32;
export const MIN_BOX_THUMB = 12;

function useElementSize<T extends HTMLElement>(): [React.RefObject<T | null>, Size] {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const r = el.getBoundingClientRect();
      setSize((prev) => (prev.width === r.width && prev.height === r.height ? prev : { width: r.width, height: r.height }));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size];
}

type Props = {
  angle: ReportAngle;
  findings: NumberedFinding[];
  variant: 'large' | 'thumb';
  selectedId?: string | null;
  hotId?: string | null;
  onHover?: (findingId: string | null) => void;
  onSelect?: (findingId: string) => void;
};

/**
 * One Angle image with its Finding boxes. Boxes are positioned in pixels of the
 * displayed image, scaled from original-image pixels, so they sit on the debris
 * at any size. In the large viewer each box is a button linked to the list.
 */
export function AngleFrame({ angle, findings, variant, selectedId, hotId, onHover, onSelect }: Props) {
  const [ref, display] = useElementSize<HTMLDivElement>();
  const image: Size = { width: angle.width || 16, height: angle.height || 9 };
  const unusable = angle.status === 'unusable';
  const minBox = variant === 'large' ? MIN_BOX_LARGE : MIN_BOX_THUMB;

  return (
    <div
      ref={ref}
      className={`frame ${variant}${unusable ? ' unusable' : ''}`}
      style={{ aspectRatio: `${image.width} / ${image.height}` }}
    >
      {angle.image_url ? (
        <img src={angle.image_url} alt={`${angle.angle} Angle camera frame`} draggable={false} />
      ) : (
        <div className="noimg">No image</div>
      )}
      {display.width > 0 &&
        findings.map(({ finding, number }) => {
          if (!isDrawableBox(finding.bbox)) return null;
          const r = scaleBox(finding.bbox, image, display, minBox);
          const open = isFindingOpen(finding);
          const cls = [
            'fbox',
            `tone-${severityTone(finding.severity)}`,
            open ? '' : 'closed',
            finding.finding_id === selectedId ? 'selected' : '',
            finding.finding_id === hotId ? 'hot' : '',
            r.top < 26 ? 'low' : '',
          ].join(' ');
          const style = { left: r.left, top: r.top, width: r.width, height: r.height };
          if (variant === 'thumb') {
            return <div key={finding.finding_id} className={cls} style={style} data-finding-box={finding.finding_id} />;
          }
          return (
            <button
              key={finding.finding_id}
              type="button"
              className={cls}
              style={style}
              data-finding-box={finding.finding_id}
              aria-label={`Finding ${number}: ${finding.severity}${open ? '' : ' (confirmed)'}, ${finding.description}`}
              aria-pressed={finding.finding_id === selectedId}
              onMouseEnter={() => onHover?.(finding.finding_id)}
              onMouseLeave={() => onHover?.(null)}
              onFocus={() => onHover?.(finding.finding_id)}
              onBlur={() => onHover?.(null)}
              onClick={() => onSelect?.(finding.finding_id)}
            >
              <span className="n">
                {number} {finding.severity}
              </span>
            </button>
          );
        })}
      {unusable &&
        (angle.checked_by_eye ? (
          <div className="stamp eye">
            <EyeIcon />
            {variant === 'large'
              ? `Unusable (${unusableReasonLabel(angle.unusable_reason)}): checked by eye by ${angle.checked_by_eye.by.name}`
              : 'By eye'}
          </div>
        ) : (
          <div className="stamp">
            <EyeOffIcon />
            {variant === 'large' ? `Unusable: ${unusableReasonLabel(angle.unusable_reason)}` : unusableReasonLabel(angle.unusable_reason)}
          </div>
        ))}
    </div>
  );
}
