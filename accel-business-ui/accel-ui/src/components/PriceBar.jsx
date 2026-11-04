import { formatINR, withGST } from '../lib/format.js';
import Button from './Button.jsx';
import './PriceBar.css';

/**
 * Sticky bar at the bottom of the plan. Monthly price, GST shown separately,
 * one-time setup, contract length and go-live date, plus the one main action.
 * `t` holds the translated labels so it works in English, Hindi and Marathi.
 */
export default function PriceBar({
  monthly,
  setup,
  months = 12,
  liveBy,
  actionLabel,
  onAction,
  actionHref,
  t = {
    perMonth: '/month',
    gst: 'GST 18%',
    setup: 'Setup',
    once: 'once',
    months: 'months',
    liveBy: 'Live by',
  },
}) {
  const { gst, total } = withGST(monthly);
  return (
    <div className="ab-pbar">
      <div className="ab-pbar__top">
        <div>
          <p className="ab-pbar__total" aria-live="polite">
            {formatINR(monthly)} <small>{t.perMonth}</small>
          </p>
          <p className="ab-pbar__gst">
            + {t.gst} {formatINR(gst)} = <b>{formatINR(total)}</b>
          </p>
        </div>
        <p className="ab-pbar__meta">
          {t.setup} <b>{formatINR(setup)}</b> {t.once}
          <br />
          {months} {t.months} · {t.liveBy} <b>{liveBy}</b>
        </p>
      </div>
      <Button block href={actionHref} onClick={onAction}>
        {actionLabel}
      </Button>
    </div>
  );
}
