import { useId } from 'react';
import { Minus, Plus } from 'lucide-react';
import './NumberField.css';

/** Stepper for small counts (people, sites). 48 px buttons either side. */
export default function NumberField({ label, value, onChange, min = 0, max = 999, step = 1 }) {
  const id = useId();
  const set = (v) => onChange?.(Math.min(max, Math.max(min, v)));
  return (
    <div className="ab-num" role="group" aria-labelledby={id}>
      <span id={id} className="ab-field__label">
        {label}
      </span>
      <div className="ab-num__box">
        <button type="button" aria-label={`One fewer, ${label}`} onClick={() => set(value - step)} disabled={value <= min}>
          <Minus size={22} strokeWidth={1.75} aria-hidden="true" />
        </button>
        <output aria-live="polite">{value}</output>
        <button type="button" aria-label={`One more, ${label}`} onClick={() => set(value + step)} disabled={value >= max}>
          <Plus size={22} strokeWidth={1.75} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
