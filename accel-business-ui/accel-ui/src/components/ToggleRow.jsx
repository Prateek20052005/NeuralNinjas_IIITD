import { useId } from 'react';
import Switch from './Switch.jsx';
import { formatINR } from '../lib/format.js';
import './ToggleRow.css';

/** An optional extra: icon, name, reason, monthly price and a switch. The whole row is the tap target. */
export default function ToggleRow({ icon: Icon, name, quantity, reason, monthly, checked, onChange }) {
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
      </span>
      <span className="ab-trow__end">
        <span className={['ab-trow__price', checked && 'is-on'].filter(Boolean).join(' ')}>{formatINR(monthly)}</span>
        <Switch id={id} checked={checked} onChange={onChange} aria-describedby={undefined} />
      </span>
    </label>
  );
}
