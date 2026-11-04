import { Check } from 'lucide-react';
import './Timeline.css';

/**
 * steps: [{ title, detail, state: 'done' | 'now' | 'todo' }]
 * State is carried by icon, weight and words as well as colour.
 */
export default function Timeline({ steps, label = 'Order progress' }) {
  return (
    <ol className="ab-tl" aria-label={label}>
      {steps.map((s, i) => (
        <li key={i} className={`ab-tl__step is-${s.state}`} aria-current={s.state === 'now' ? 'step' : undefined}>
          <span className="ab-tl__dot" aria-hidden="true">
            {s.state === 'done' ? <Check size={15} strokeWidth={2.6} /> : null}
            {s.state === 'now' ? <i /> : null}
          </span>
          <div>
            <p className="ab-tl__title">{s.title}</p>
            {s.detail ? <p className="ab-tl__detail">{s.detail}</p> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
