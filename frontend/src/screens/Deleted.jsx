import { RotateCcw } from 'lucide-react';
import AppHeader from '../components/AppHeader.jsx';
import BrandMark from '../components/BrandMark.jsx';
import Button from '../components/Button.jsx';
import EmptyState from '../components/EmptyState.jsx';

function ClearedArt() {
  return (
    <svg viewBox="0 0 180 160" width="180" height="160" aria-hidden="true">
      <circle cx="90" cy="80" r="64" fill="var(--color-trust-tint)" />
      <rect x="58" y="40" width="64" height="82" rx="10" fill="var(--color-surface)" stroke="var(--color-hairline)" strokeWidth="2" />
      <rect x="70" y="56" width="40" height="5" rx="2.5" fill="var(--color-hairline)" />
      <rect x="70" y="68" width="30" height="5" rx="2.5" fill="var(--color-hairline)" />
      <circle cx="118" cy="112" r="20" fill="var(--color-success)" />
      <path d="M109 112l6 6 12-12" fill="none" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** After "Delete my data": nothing personal remains, on the server or on this phone. */
export default function Deleted({ tr, message, onRestart, actions }) {
  return (
    <div className="app-shell">
      <AppHeader title={<BrandMark size={26} />} actions={actions} />
      <main className="page screen-in">
        <EmptyState illustration={<ClearedArt />} title={tr('ui.deleted_title')} body={message || tr('privacy.deleted')}
                    action={<Button block icon={RotateCcw} onClick={onRestart}>{tr('ui.start_over')}</Button>} />
      </main>
    </div>
  );
}
