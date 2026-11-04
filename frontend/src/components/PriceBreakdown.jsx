import { ChevronDown } from 'lucide-react';
import './PriceBreakdown.css';

/**
 * "How is this price worked out?" Native <details>, so it works without JS.
 * rows: [{ label, value, note?, kind?: 'sub' | 'total' | 'save' }], already formatted by the caller.
 */
export default function PriceBreakdown({ title, rows, footnote, defaultOpen = false }) {
  return (
    <details className="ab-bkd" open={defaultOpen}>
      <summary>
        {title}
        <ChevronDown size={22} strokeWidth={1.75} aria-hidden="true" />
      </summary>
      <dl className="ab-bkd__list">
        {rows.map((r, i) => (
          <div className={['ab-bkd__li', r.kind && `is-${r.kind}`].filter(Boolean).join(' ')} key={i}>
            <dt>
              {r.label}
              {r.note ? <span className="ab-bkd__note">{r.note}</span> : null}
            </dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
      {footnote ? <p className="ab-bkd__foot">{footnote}</p> : null}
    </details>
  );
}
