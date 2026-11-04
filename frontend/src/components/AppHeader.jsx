import { ChevronLeft } from 'lucide-react';
import './AppHeader.css';

/** Sticky frosted header: back button, centred title (+ optional subtitle), trailing actions. */
export default function AppHeader({ title, subtitle, onBack, backLabel = 'Back', actions, children }) {
  return (
    <header className="ab-hdr">
      <div className="ab-hdr__row">
        {onBack ? (
          <button type="button" className="ab-icon-btn" aria-label={backLabel} onClick={onBack}>
            <ChevronLeft size={26} strokeWidth={1.75} aria-hidden="true" />
          </button>
        ) : (
          <span />
        )}
        <div className="ab-hdr__title">
          {title}
          {subtitle ? <span className="ab-hdr__sub">{subtitle}</span> : null}
        </div>
        <div className="ab-hdr__end">{actions}</div>
      </div>
      {children}
    </header>
  );
}
