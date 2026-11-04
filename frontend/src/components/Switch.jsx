import './Switch.css';

/** iOS-style switch. Always give it a label (visible via ToggleRow, or aria-label). */
export default function Switch({ checked, onChange, label, id, ...rest }) {
  return (
    <input
      id={id}
      type="checkbox"
      role="switch"
      className="ab-switch"
      checked={checked}
      aria-label={label}
      onChange={(e) => onChange?.(e.target.checked)}
      {...rest}
    />
  );
}
