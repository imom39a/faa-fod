import type { ActivityCategory } from '../lib/activity';
import { AgentIcon, ChatIcon, CheckCircleIcon, ClockIcon, CrossIcon, DashIcon, EyeIcon, QuestionIcon, ReportIcon, TaskIcon } from './icons';

const ICON: Record<ActivityCategory, React.ReactNode> = {
  inspection: <EyeIcon />,
  task: <TaskIcon />,
  report: <ReportIcon />,
  confirmation: <CheckCircleIcon />,
  refusal: <CrossIcon />,
  message: <ChatIcon />,
  proposal: <QuestionIcon />,
  timer: <ClockIcon />,
  agent: <AgentIcon />,
  system: <DashIcon />,
};

/** The icon of an activity entry's kind, shared by the Activity log and Crew and Tasks. */
export function ActivityCategoryIcon({ category }: { category: ActivityCategory }) {
  return <>{ICON[category]}</>;
}
