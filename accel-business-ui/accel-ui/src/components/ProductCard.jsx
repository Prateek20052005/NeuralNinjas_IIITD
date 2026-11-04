import { formatINR } from '../lib/format.js';
import './ProductCard.css';

/** One line of the plan: icon, name, quantity, one-line reason, monthly price. */
export default function ProductCard({ icon: Icon, name, quantity, reason, monthly, perLabel = 'a month' }) {
  return (
    <div className="ab-pc">
      <span className="ab-pc__ic" aria-hidden="true">
        {Icon ? <Icon size={24} strokeWidth={1.75} /> : null}
      </span>
      <div className="ab-pc__main">
        <p className="ab-pc__name">
          {name}
          {quantity > 1 ? <span className="ab-qty">×{quantity}</span> : null}
        </p>
        {reason ? <p className="ab-pc__why">{reason}</p> : null}
      </div>
      <p className="ab-pc__price">
        {formatINR(monthly)}
        <small>{perLabel}</small>
      </p>
    </div>
  );
}
