import type { ReactNode } from 'react';
import type { Severity } from '../api/types';
import type { Tone } from '../lib/gates';

type IconProps = { className?: string };

function Svg({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {children}
    </svg>
  );
}

/** HOLD: a stop octagon. */
export const HoldIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 2.5h8l5.5 5.5v8L16 21.5H8L2.5 16V8z" />
    <path d="M8 12h8" />
  </Svg>
);
/** REMOVE: a warning triangle. */
export const RemoveIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3 2.5 20h19z" />
    <path d="M12 10v4.5M12 17.4v.1" />
  </Svg>
);
/** ADVISORY: an information circle. */
export const AdvisoryIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9.5" />
    <path d="M12 11v6M12 7.4v.1" />
  </Svg>
);
export const CheckIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="m4.5 12.5 5 5 10-11" />
  </Svg>
);
export const CheckCircleIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9.5" />
    <path d="m7.5 12.5 3 3 6-6.5" />
  </Svg>
);
export const CrossIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="m6 6 12 12M18 6 6 18" />
  </Svg>
);
/** INCOMPLETE / unusable Angle: an eye with a slash. */
export const EyeOffIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
    <path d="m4 3.5 16 17" />
  </Svg>
);
export const EyeIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
    <circle cx="12" cy="12" r="2.8" />
  </Svg>
);
export const SpinnerIcon = ({ className }: IconProps) => (
  <Svg className={`spin ${className ?? ''}`}>
    <path d="M12 2.5a9.5 9.5 0 1 1-9.5 9.5" />
  </Svg>
);
export const ClockIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9.5" />
    <path d="M12 7v5.5l3.5 2" />
  </Svg>
);
export const PlaneIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10.5 3.5h2.2l3 6.5h4.300a1.800 1.800 0 0 1 0 4h-4.300l-3 6.500h-2.200l1.500-6.500H7.500L6 16H4l1-4-1-4h2l1.500 2H12z" />
  </Svg>
);
export const DashIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 12h12" />
  </Svg>
);
export const PenIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 20h4L20 8l-4-4L4 16z" />
  </Svg>
);
export const PlayIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 4.500v15l12-7.500z" />
  </Svg>
);
export const PauseIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 5v14M16 5v14" />
  </Svg>
);
export const ResetIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 12a8 8 0 1 0 2.500-5.800" />
    <path d="M4 4v5h5" />
  </Svg>
);

export function SeverityIcon({ severity, className }: { severity: Severity; className?: string }) {
  if (severity === 'HOLD') return <HoldIcon className={className} />;
  if (severity === 'REMOVE') return <RemoveIcon className={className} />;
  return <AdvisoryIcon className={className} />;
}

/** Icon for a Gate/queue tone, so colour is never the only signal. */
export function ToneIcon({ tone, className }: { tone: Tone; className?: string }) {
  switch (tone) {
    case 'hold':
      return <HoldIcon className={className} />;
    case 'remove':
      return <RemoveIcon className={className} />;
    case 'advisory':
      return <AdvisoryIcon className={className} />;
    case 'incomplete':
      return <EyeOffIcon className={className} />;
    case 'clear':
      return <CheckIcon className={className} />;
    case 'confirmed':
      return <CheckCircleIcon className={className} />;
    case 'busy':
      return <SpinnerIcon className={className} />;
    case 'await':
      return <PenIcon className={className} />;
    case 'onstand':
      return <PlaneIcon className={className} />;
    case 'waiting':
      return <ClockIcon className={className} />;
    default:
      return <DashIcon className={className} />;
  }
}
