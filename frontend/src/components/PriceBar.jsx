import Button from './Button.jsx';
import './PriceBar.css';

/**
 * Sticky bar at the bottom of the plan: monthly price, GST shown separately, setup, contract and go-live,
 * plus the one main action. All numbers and words come from the server's quote, already formatted.
 */
export default function PriceBar({ total, perMonth, gstLine, meta = [], actionLabel, onAction, disabled, extra }) {
  return (
    <div className="ab-pbar">
      <div className="ab-pbar__top">
        <div>
          <p className="ab-pbar__total" aria-live="polite">
            {total} <small>{perMonth}</small>
          </p>
          <p className="ab-pbar__gst">{gstLine}</p>
          {extra ? <p className="ab-pbar__extra">{extra}</p> : null}
        </div>
        <p className="ab-pbar__meta">
          {meta.map((m, i) => (
            <span key={i}>
              {m}
              {i < meta.length - 1 ? <br /> : null}
            </span>
          ))}
        </p>
      </div>
      <Button block onClick={onAction} disabled={disabled}>
        {actionLabel}
      </Button>
    </div>
  );
}
