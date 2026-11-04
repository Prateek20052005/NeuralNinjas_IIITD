import { ChevronDown } from 'lucide-react';
import { formatINR, withGST } from '../lib/format.js';
import './PriceBreakdown.css';

/**
 * "How is this price worked out?" Native <details>, so it works without JS.
 * lines: [{ label, monthly }]
 */
export default function PriceBreakdown({
  lines,
  setup,
  months = 12,
  defaultOpen = false,
  t = {
    title: 'How is this price worked out?',
    subtotal: 'Monthly price',
    gst: 'GST 18%',
    total: 'You pay each month',
    setup: 'One-time setup, paid once',
    plusGst: '+ GST',
    contract: 'Contract',
    months: 'months',
  },
}) {
  const subtotal = lines.reduce((s, l) => s + l.monthly, 0);
  const { gst, total } = withGST(subtotal);
  return (
    <details className="ab-bkd" open={defaultOpen}>
      <summary>
        {t.title}
        <ChevronDown size={22} strokeWidth={1.75} aria-hidden="true" />
      </summary>
      <dl className="ab-bkd__list">
        {lines.map((l) => (
          <div className="ab-bkd__li" key={l.label}>
            <dt>{l.label}</dt>
            <dd>{formatINR(l.monthly)}</dd>
          </div>
        ))}
        <div className="ab-bkd__li is-sub">
          <dt>{t.subtotal}</dt>
          <dd>{formatINR(subtotal)}</dd>
        </div>
        <div className="ab-bkd__li">
          <dt>{t.gst}</dt>
          <dd>{formatINR(gst)}</dd>
        </div>
        <div className="ab-bkd__li is-total">
          <dt>{t.total}</dt>
          <dd>{formatINR(total)}</dd>
        </div>
        <div className="ab-bkd__li is-sub">
          <dt>{t.setup}</dt>
          <dd>
            {formatINR(setup)} {t.plusGst}
          </dd>
        </div>
        <div className="ab-bkd__li">
          <dt>{t.contract}</dt>
          <dd>
            {months} {t.months}
          </dd>
        </div>
      </dl>
    </details>
  );
}
