import { useId } from 'react';
import { Users } from 'lucide-react';
import Switch from './Switch.jsx';
import { formatINR } from '../lib/format.js';
import './ToggleRow.css';

/** An optional extra: icon, name, reason, an optional proof line (how often similar businesses chose it), monthly
 * price and a switch. The whole row is the tap target. */
export default function ToggleRow({ icon: Icon, name, quantity, reason, proof, monthly, checked, onChange }) {
  const id = useId();
  return (
    <label className="ab-trow" htmlFor={id}>
      <span className="ab-trow__ic" aria-hidden="true">
        {Icon ? <Icon size={24} strokeWidth={1.75} /> : null}
      </span>
      <span className="ab-trow__main">
        <span className="t-headline">
          {name}
          {quantity > 1 ? <span className="ab-qty">×{quantity}</span> : null}
        </span>
        {reason ? <span className="t-callout t-secondary">{reason}</span> : null}
        {proof ? (
          <span className="ab-trow__proof t-footnote">
            <Users size={14} strokeWidth={2} aria-hidden="true" /> {proof}
          </span>
        ) : null}
      </span>
      <span className="ab-trow__end">
        <span className={['ab-trow__price', checked && 'is-on'].filter(Boolean).join(' ')}>{formatINR(monthly)}</span>
        <Switch id={id} checked={checked} onChange={onChange} aria-describedby={undefined} />
      </span>
    </label>
  );
}
