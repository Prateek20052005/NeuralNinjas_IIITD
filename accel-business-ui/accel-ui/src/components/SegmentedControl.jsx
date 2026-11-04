import './SegmentedControl.css';

/**
 * options: [{ value, label, lang? }]
 * Behaves as a radio group: arrow keys move the selection.
 */
export default function SegmentedControl({ label, options, value, onChange }) {
  const idx = options.findIndex((o) => o.value === value);
  function onKeyDown(e) {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const step = e.key === 'ArrowRight' ? 1 : -1;
    const next = options[(idx + step + options.length) % options.length];
    onChange?.(next.value);
  }
  return (
    <div className="ab-seg" role="radiogroup" aria-label={label} onKeyDown={onKeyDown}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            lang={o.lang}
            className={on ? 'is-on' : undefined}
            onClick={() => onChange?.(o.value)}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
