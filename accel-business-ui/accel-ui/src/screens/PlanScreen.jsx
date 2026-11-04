import { useState } from 'react';
import { Wifi, Smartphone, Mail, ShieldCheck, Signal, Video, MessageCircle, Share2 } from 'lucide-react';
import AppHeader from '../components/AppHeader.jsx';
import ProductCard from '../components/ProductCard.jsx';
import ToggleRow from '../components/ToggleRow.jsx';
import Note from '../components/Note.jsx';
import PriceBreakdown from '../components/PriceBreakdown.jsx';
import PriceBar from '../components/PriceBar.jsx';
import { planStrings } from '../i18n/plan.js';

// Prices from the brief's clinic example. Camera and WhatsApp prices are placeholders.
const BASE = [
  { key: 'fibre', icon: Wifi, qty: 1, monthly: 1649 },
  { key: 'postpaid', icon: Smartphone, qty: 2, monthly: 1398 },
  { key: 'email', icon: Mail, qty: 5, monthly: 690 },
  { key: 'security', icon: ShieldCheck, qty: 5, monthly: 620 },
];
const EXTRAS = [
  { key: 'backup', icon: Signal, qty: 1, monthly: 549, on: true },
  { key: 'cameras', icon: Video, qty: 2, monthly: 398, on: false },
  { key: 'whatsapp', icon: MessageCircle, qty: 1, monthly: 149, on: false },
];
const SETUP = 1500;

export default function PlanScreen({ lang = 'en', onBack, onAccept, onShare }) {
  const t = planStrings[lang] || planStrings.en;
  const [extras, setExtras] = useState(() => Object.fromEntries(EXTRAS.map((e) => [e.key, e.on])));

  const chosen = [...BASE, ...EXTRAS.filter((e) => extras[e.key])];
  const monthly = chosen.reduce((s, p) => s + p.monthly, 0);
  const lines = chosen.map((p) => ({ label: t.products[p.key][0] + (p.qty > 1 ? ` × ${p.qty}` : ''), monthly: p.monthly }));

  return (
    <div className="app-shell" lang={lang}>
      <AppHeader
        title={t.title}
        onBack={onBack}
        actions={
          <button type="button" className="ab-icon-btn" style={{ color: 'var(--color-brand-ink)' }} aria-label="Share or save this quote" onClick={onShare}>
            <Share2 size={22} strokeWidth={1.75} aria-hidden="true" />
          </button>
        }
      />
      <main className="page" style={{ gap: 20, paddingTop: 16 }}>
        <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <p className="t-footnote t-secondary" style={{ fontWeight: 600 }}>{t.eyebrow}</p>
          <h1 className="t-large-title" style={{ fontSize: lang === 'en' ? '1.875rem' : undefined }}>{t.headline}</h1>
          <p className="t-body t-secondary">{t.summary}</p>
        </section>

        <section aria-labelledby="in-plan" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <h2 id="in-plan" className="section-label">{t.inPlan}</h2>
          <div className="inset-group">
            {BASE.map((p) => (
              <ProductCard key={p.key} icon={p.icon} name={t.products[p.key][0]} reason={t.products[p.key][1]} quantity={p.qty} monthly={p.monthly} perLabel={t.perMonth} />
            ))}
          </div>
        </section>

        <section aria-labelledby="extras" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <h2 id="extras" className="section-label">{t.extras}</h2>
          <div className="inset-group">
            {EXTRAS.map((e) => (
              <ToggleRow
                key={e.key}
                icon={e.icon}
                name={t.products[e.key][0]}
                reason={t.products[e.key][1]}
                quantity={e.qty}
                monthly={e.monthly}
                checked={extras[e.key]}
                onChange={(v) => setExtras((x) => ({ ...x, [e.key]: v }))}
              />
            ))}
          </div>
        </section>

        <Note title={t.whyNot}>{t.whyNotBody}</Note>

        <PriceBreakdown lines={lines} setup={SETUP} t={t.breakdown} />
      </main>

      <PriceBar monthly={monthly} setup={SETUP} months={12} liveBy={t.liveBy} actionLabel={t.accept} onAction={onAccept} t={t.bar} />
    </div>
  );
}
