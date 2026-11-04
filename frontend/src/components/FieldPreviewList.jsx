import { maskId } from '../lib/format.js';
import './FieldPreviewList.css';

/**
 * What we read from a document. fields: [{ label, value, masked?, node? }]
 * `masked: true` masks the value for display; `node` renders custom content (e.g. a badge).
 */
export default function FieldPreviewList({ title, fields, action, footnote }) {
  return (
    <section className="card ab-kv">
      {(title || action) && (
        <div className="ab-kv__head">
          {title ? <p className="t-headline">{title}</p> : <span />}
          {action}
        </div>
      )}
      <dl className="ab-kv__list">
        {fields.map((f, i) => (
          <div className="ab-kv__row" key={i}>
            <dt>{f.label}</dt>
            <dd className={f.masked ? 't-mono' : undefined}>{f.node ?? (f.masked ? maskId(f.value) : f.value)}</dd>
          </div>
        ))}
      </dl>
      {footnote ? <p className="t-footnote t-secondary">{footnote}</p> : null}
    </section>
  );
}
