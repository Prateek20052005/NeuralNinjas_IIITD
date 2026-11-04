import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import './BottomSheet.css';

/** Modal bottom sheet built on <dialog>, so focus trapping and Esc come from the browser. */
export default function BottomSheet({ open, onClose, title, closeLabel = 'Close', children }) {
  const ref = useRef(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="ab-sheet"
      aria-labelledby="ab-sheet-title"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose?.();
      }}
    >
      <div className="ab-sheet__body">
        <span className="ab-sheet__grab" aria-hidden="true" />
        <div className="ab-sheet__head">
          <h2 id="ab-sheet-title" className="t-title">
            {title}
          </h2>
          <button type="button" className="ab-sheet__close" aria-label={closeLabel} onClick={onClose}>
            <X size={22} strokeWidth={1.75} aria-hidden="true" />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
