import { Check, RefreshCw, Clock, CircleX, ArrowRight } from 'lucide-react';
import './DecisionCard.css';

const ICONS = { approved: Check, retake: RefreshCw, review: Clock, rejected: CircleX };

/**
 * outcome: 'approved' | 'retake' | 'review' | 'rejected'
 * Always says what happens next (`next`) and offers at most one action (`action`).
 */
export default function DecisionCard({ outcome = 'review', title, body, next, action }) {
  const Icon = ICONS[outcome] || Clock;
  return (
    <section className="ab-dcard" aria-live="polite">
      <div className="ab-dcard__head">
        <span className={`ab-dcard__ic ab-dcard__ic--${outcome}`} aria-hidden="true">
          <Icon size={28} strokeWidth={2.1} />
        </span>
        <div>
          <p className="ab-dcard__title">{title}</p>
          {body ? <p className="t-callout t-secondary">{body}</p> : null}
        </div>
      </div>
      {next ? (
        <div className="ab-dcard__next">
          <ArrowRight size={18} strokeWidth={1.75} aria-hidden="true" />
          <span>{next}</span>
        </div>
      ) : null}
      {action}
    </section>
  );
}
