import { Check, RefreshCw, Clock, CircleX, CircleDashed } from 'lucide-react';
import './StatusBadge.css';

const ICONS = {
  approved: Check,
  retake: RefreshCw,
  review: Clock,
  rejected: CircleX,
  incomplete: CircleDashed,
};

const DEFAULT_LABELS = {
  approved: 'Approved',
  retake: 'Retake',
  review: 'Review',
  rejected: 'Rejected',
  incomplete: 'Incomplete',
};

/** Status is always icon + word, never colour alone. */
export default function StatusBadge({ status = 'incomplete', children }) {
  const Icon = ICONS[status] || CircleDashed;
  return (
    <span className={`ab-badge ab-badge--${status}`}>
      <Icon size={15} strokeWidth={2.2} aria-hidden="true" />
      {children ?? DEFAULT_LABELS[status]}
    </span>
  );
}
