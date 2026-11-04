import { Camera } from 'lucide-react';
import StatusBadge from './StatusBadge.jsx';
import './UploadTile.css';

/**
 * state: 'empty' | 'reading' | 'read' | 'retake'
 * `progress` (0–1) shows while reading; `reason` explains a retake.
 */
export default function UploadTile({
  name,
  sublabel,
  state = 'empty',
  progress = 0,
  reason,
  onSelect,
  t = { add: 'Add photo', reading: 'Reading…', read: 'Read', retake: 'Retake' },
}) {
  const busy = state === 'reading';
  return (
    <button
      type="button"
      className={`ab-tile ab-tile--${state}`}
      onClick={onSelect}
      aria-busy={busy || undefined}
      disabled={busy}
    >
      <span className="ab-tile__thumb" aria-hidden="true">
        {state === 'empty' ? (
          <Camera size={32} strokeWidth={1.6} />
        ) : (
          <span className={['ab-doc', state === 'retake' && 'is-blur'].filter(Boolean).join(' ')}>
            <i /><i /><i /><i /><i />
          </span>
        )}
        {busy ? <span className="ab-tile__scan" /> : null}
      </span>
      <span className="ab-tile__name">
        {name}
        {sublabel ? <span className="ab-tile__sub">{sublabel}</span> : null}
      </span>
      <span className="ab-tile__foot">
        {state === 'empty' && <span className="ab-tile__add">{t.add}</span>}
        {state === 'reading' && (
          <>
            <span className="ab-tile__reading">{t.reading}</span>
            <span className="ab-meter" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
              <i style={{ width: `${Math.round(progress * 100)}%` }} />
            </span>
          </>
        )}
        {state === 'read' && <StatusBadge status="approved">{t.read}</StatusBadge>}
        {state === 'retake' && (
          <>
            <StatusBadge status="retake">{t.retake}</StatusBadge>
            {reason ? <span className="ab-tile__reason">{reason}</span> : null}
          </>
        )}
      </span>
    </button>
  );
}
