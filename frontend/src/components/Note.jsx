import { Info, TriangleAlert, CircleCheck, ShieldCheck } from 'lucide-react';
import './Note.css';

const ICONS = { info: Info, warn: TriangleAlert, ok: CircleCheck, trust: ShieldCheck };

/** Inline explanation, e.g. why a product couldn't be offered. tone: 'info' | 'warn' | 'ok' | 'trust' */
export default function Note({ tone = 'info', title, children }) {
  const Icon = ICONS[tone] || Info;
  return (
    <div className={`ab-note ab-note--${tone}`}>
      <Icon size={22} strokeWidth={1.75} aria-hidden="true" />
      <p>
        {title ? <strong>{title} </strong> : null}
        {children}
      </p>
    </div>
  );
}
