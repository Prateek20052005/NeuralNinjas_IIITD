import { useId } from 'react';
import { CircleAlert } from 'lucide-react';
import './TextField.css';

/** Labelled text input with optional hint and error. */
export default function TextField({ label, hint, error, mono = false, id, ...inputProps }) {
  const autoId = useId();
  const fieldId = id || autoId;
  const hintId = `${fieldId}-hint`;
  return (
    <div className="ab-field">
      <label htmlFor={fieldId} className="ab-field__label">
        {label}
      </label>
      <input
        id={fieldId}
        className={['ab-field__input', mono && 't-mono', error && 'is-bad'].filter(Boolean).join(' ')}
        aria-invalid={error ? true : undefined}
        aria-describedby={hint || error ? hintId : undefined}
        {...inputProps}
      />
      {error ? (
        <p id={hintId} className="ab-field__error">
          <CircleAlert size={15} strokeWidth={2} aria-hidden="true" />
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="ab-field__hint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
