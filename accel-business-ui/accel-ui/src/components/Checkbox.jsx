import { useId } from 'react';
import './Checkbox.css';

/** Labelled checkbox row. Never pre-tick consent. */
export default function Checkbox({ checked, onChange, label, hint, required = false }) {
  const hintId = useId();
  return (
    <label className="ab-check">
      <input
        type="checkbox"
        className="ab-check__box"
        checked={checked}
        required={required}
        aria-describedby={hint ? hintId : undefined}
        onChange={(e) => onChange?.(e.target.checked)}
      />
      <span className="ab-check__text">
        <span className="t-headline">{label}</span>
        {hint ? (
          <span id={hintId} className="t-footnote t-secondary">
            {hint}
          </span>
        ) : null}
      </span>
    </label>
  );
}
