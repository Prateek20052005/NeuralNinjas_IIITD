import './ProgressIndicator.css';

/** Slim bar with "3 of 8". `formatLabel` lets Hindi/Marathi say "8 में से 3". */
export default function ProgressIndicator({ current, total, formatLabel = (c, t) => `${c} of ${t}` }) {
  const label = formatLabel(current, total);
  return (
    <div className="ab-prog">
      <div className="ab-prog__bar" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={current} aria-label={label}>
        <i style={{ width: `${(current / total) * 100}%` }} />
      </div>
      <span aria-hidden="true">{label}</span>
    </div>
  );
}
