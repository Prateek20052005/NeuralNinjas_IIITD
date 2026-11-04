import { useEffect } from 'react';
import { CircleCheck } from 'lucide-react';
import './Toast.css';

/** Short confirmation that disappears on its own. Announced politely to screen readers. */
export default function Toast({ open, message, onDone, duration = 3000 }) {
  useEffect(() => {
    if (!open) return undefined;
    const t = setTimeout(() => onDone?.(), duration);
    return () => clearTimeout(t);
  }, [open, duration, onDone]);

  return (
    <div className="ab-toast-region" role="status" aria-live="polite">
      {open ? (
        <div className="ab-toast">
          <CircleCheck size={18} strokeWidth={1.75} aria-hidden="true" />
          {message}
        </div>
      ) : null}
    </div>
  );
}
