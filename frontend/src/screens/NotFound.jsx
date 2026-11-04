import { House } from 'lucide-react';
import AppHeader from '../components/AppHeader.jsx';
import BrandMark from '../components/BrandMark.jsx';
import Button from '../components/Button.jsx';
import EmptyState from '../components/EmptyState.jsx';

function LostArt() {
  return (
    <svg viewBox="0 0 180 160" width="180" height="160" aria-hidden="true">
      <circle cx="90" cy="80" r="64" fill="var(--color-accent-tint)" />
      <path d="M52 108h76" stroke="var(--color-hairline)" strokeWidth="4" strokeLinecap="round" />
      <path d="M90 46v62" stroke="var(--color-ink-2)" strokeWidth="4" strokeLinecap="round" />
      <path d="M90 50h30l8 9-8 9H90z" fill="var(--color-brand)" />
      <path d="M90 72H64l-8 9 8 9h26z" fill="var(--color-trust)" opacity="0.85" />
    </svg>
  );
}

export default function NotFound({ tr, onHome }) {
  return (
    <div className="app-shell">
      <AppHeader title={<BrandMark size={26} />} />
      <main className="page">
        <EmptyState illustration={<LostArt />} title={tr('ui.not_found')}
                    action={<Button block icon={House} onClick={onHome}>{tr('ui.go_home')}</Button>} />
      </main>
    </div>
  );
}
