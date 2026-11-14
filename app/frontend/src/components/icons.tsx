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

/** Product mark: the corners of a stand with a check inside. */
export const BrandMark = ({ className }: IconProps) => (
  <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
    <path d="M4 11V4h7M21 4h7v7M28 21v7h-7M11 28H4v-7" />
    <path d="M10 16.5l4.2 4.2L22.5 12" />
  </svg>
);

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

export const ChatIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 5h16v11H10l-5 4v-4H4z" />
  </Svg>
);
export const ListIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 6h12M8 12h12M8 18h12M3.5 6h.1M3.5 12h.1M3.5 18h.1" />
  </Svg>
);
export const GridIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" />
  </Svg>
);
export const UserIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21c0-4.4 3.600-7 8-7s8 2.600 8 7" />
  </Svg>
);
/** Escalation: a double chevron pointing up. */
export const EscalationIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="m5 12 7-7 7 7M5 19l7-7 7 7" />
  </Svg>
);
export const CameraIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 8h4l2-3h6l2 3h4v11H3z" />
    <circle cx="12" cy="13" r="3.500" />
  </Svg>
);
export const SendIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M21 3 10 14M21 3l-7 18-4-7-7-4z" />
  </Svg>
);
export const QuestionIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9.500" />
    <path d="M9.200 9.500a2.900 2.900 0 1 1 4.300 2.500c-.900.500-1.500 1.100-1.500 2.200M12 17.400v.1" />
  </Svg>
);
/** A Report: a speech note. Never used for a Confirmation. */
export const ReportIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 3h10l4 4v14H5z" />
    <path d="M9 10h6M9 14h6M9 18h3" />
  </Svg>
);
export const TaskIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 4H5v17h14V4h-3" />
    <path d="M8 2.500h8v4H8zM8.500 13l2.500 2.500 4.500-5" />
  </Svg>
);
export const AgentIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 8h14v11H5zM12 8V4M9 13v1.500M15 13v1.500M2.500 12v4M21.500 12v4" />
    <circle cx="12" cy="3.500" r="1" />
  </Svg>
);
export const ArrowRightIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 12h15M13 6l6 6-6 6" />
  </Svg>
);
/** Settings: a slider panel. */
export const SettingsIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
    <circle cx="15" cy="7" r="2" />
    <circle cx="9" cy="17" r="2" />
  </Svg>
);
export const SignOutIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M14 4h5v16h-5M10 8l-4 4 4 4M6 12h9" />
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
