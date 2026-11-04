import { Camera } from 'lucide-react';
import StatusBadge from './StatusBadge.jsx';
import './UploadTile.css';

/**
 * One document. state: 'empty' | 'reading' | 'read' | 'retake'.
 * The whole tile is a label for a hidden file input, so tapping it opens the camera or the gallery.
 * `reason` explains a retake; `tag` adds a small word such as "Optional".
 */
export default function UploadTile({ name, sublabel, state = 'empty', reason, onFile, tag, t }) {
  const busy = state === 'reading';
  return (
    <label className={`ab-tile ab-tile--${state}`} aria-busy={busy || undefined}>
      <input
        type="file"
        accept="image/*"
        className="visually-hidden"
        disabled={busy}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile?.(file);
          e.target.value = ''; // the same photo can be picked again after a retake
        }}
      />
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
        {tag ? <span className="ab-tile__tag">{tag}</span> : null}
        {state === 'empty' && <span className="ab-tile__add">{t.add}</span>}
        {state === 'reading' && (
          <>
            <span className="ab-tile__reading">{t.reading}</span>
            <span className="ab-meter ab-meter--busy" role="progressbar" aria-label={t.reading}>
              <i />
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
    </label>
  );
}
