import { useState } from 'react';
import { ArrowRight, MessagesSquare, ScanLine, Smartphone, Zap, History } from 'lucide-react';
import { api } from '../api.js';
import AppHeader from '../components/AppHeader.jsx';
import BrandMark from '../components/BrandMark.jsx';
import Button from '../components/Button.jsx';
import Note from '../components/Note.jsx';
import PhoneVerifySheet from '../components/PhoneVerifySheet.jsx';

export const LANGS = [
  { code: 'en', name: 'English', hello: 'Choose your language' },
  { code: 'hi', name: 'हिंदी', hello: 'अपनी भाषा चुनिए' },
  { code: 'mr', name: 'मराठी', hello: 'तुमची भाषा निवडा' },
  { code: 'gu', name: 'ગુજરાતી', hello: 'તમારી ભાષા પસંદ કરો' },
  { code: 'ta', name: 'தமிழ்', hello: 'மொழியைத் தேர்வு செய்யுங்கள்' },
  { code: 'te', name: 'తెలుగు', hello: 'మీ భాషను ఎంచుకోండి' },
  { code: 'kn', name: 'ಕನ್ನಡ', hello: 'ನಿಮ್ಮ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ' },
];

/** A shop counter: the router, a phone, a payment tablet. Flat, light, no image files. */
function CounterArt() {
  return (
    <svg className="home-art" viewBox="0 0 360 150" role="img" aria-hidden="true">
      <rect x="0" y="0" width="360" height="150" fill="var(--color-brand-tint)" />
      <circle cx="300" cy="34" r="16" fill="var(--color-accent)" opacity="0.9" />
      <rect x="0" y="112" width="360" height="38" fill="var(--color-brand)" opacity="0.16" />
      <rect x="28" y="96" width="304" height="18" rx="6" fill="var(--color-surface)" />
      {/* router with signal arcs */}
      <rect x="52" y="70" width="64" height="26" rx="8" fill="var(--color-trust)" />
      <circle cx="68" cy="83" r="3" fill="var(--color-accent)" />
      <circle cx="80" cy="83" r="3" fill="#fff" opacity="0.8" />
      <path d="M70 58q14-14 28 0M76 50q8-8 16 0" fill="none" stroke="var(--color-trust)" strokeWidth="4" strokeLinecap="round" />
      {/* payment tablet */}
      <rect x="150" y="48" width="74" height="48" rx="8" fill="var(--color-surface)" stroke="var(--color-hairline)" strokeWidth="2" />
      <rect x="158" y="56" width="58" height="22" rx="4" fill="var(--color-success)" opacity="0.18" />
      <path d="M176 67l6 6 12-12" fill="none" stroke="var(--color-success)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="158" y="84" width="34" height="5" rx="2.5" fill="var(--color-hairline)" />
      {/* phone */}
      <rect x="252" y="44" width="34" height="52" rx="7" fill="var(--color-ink)" />
      <rect x="256" y="50" width="26" height="38" rx="3" fill="var(--color-surface)" />
      <rect x="260" y="56" width="18" height="5" rx="2.5" fill="var(--color-brand)" />
      <rect x="260" y="65" width="12" height="5" rx="2.5" fill="var(--color-hairline)" />
    </svg>
  );
}

export default function Home({ tr, lang, setLang, saved, onStart, onResume, onResumed, actions }) {
  const [resuming, setResuming] = useState(false); // continue a saved application with the mobile number
  const [resumePhone, setResumePhone] = useState('');
  const steps = [
    { icon: MessagesSquare, title: tr('ui.home_step1_title'), body: tr('ui.home_step1') },
    { icon: ScanLine, title: tr('ui.home_step2_title'), body: tr('ui.home_step2') },
    { icon: Zap, title: tr('ui.home_step3_title'), body: tr('ui.home_step3') },
  ];
  return (
    <div className="app-shell" lang={lang}>
      <AppHeader title={<BrandMark size={28} />} actions={actions} />
      <main className="page screen-in">
        <section className="home-hero">
          <CounterArt />
          <h1 className="t-large-title">{tr('ui.promise')}</h1>
          <p className="lead">{tr('ui.tagline')}</p>
        </section>

        {saved && (
          <section className="card continue-card">
            <span className="continue-card__ic" aria-hidden="true"><History size={22} strokeWidth={1.75} /></span>
            <div>
              <p className="t-headline">{tr('ui.continue_title')}</p>
            </div>
            <Button size="sm" onClick={onResume}>{tr('ui.continue_go')}</Button>
          </section>
        )}

        <ol className="inset-group home-steps">
          {steps.map((s, i) => (
            <li className="home-step" key={i}>
              <span className="home-step__n" aria-hidden="true"><s.icon size={22} strokeWidth={1.75} /></span>
              <div>
                <p className="t-headline">{s.title}</p>
                <p className="t-callout t-secondary">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>

        <Button variant="secondary" block icon={Smartphone} onClick={() => setResuming(true)}>
          {tr('ui.resume_title')}
        </Button>

        <div className="stack">
          <Note tone="ok">{tr('ui.home_honest')}</Note>
          <Note tone="trust">{tr('ui.home_private')}</Note>
        </div>

        <section className="stack" aria-labelledby="lang-title">
          <h2 id="lang-title" className="section-label">{tr('ui.choose_language')}</h2>
          <div className="lang-grid">
            {LANGS.map((l) => (
              <button key={l.code} type="button" className="lang-card" lang={l.code} aria-pressed={lang === l.code}
                      onClick={() => setLang(l.code)}>
                <strong>{l.name}</strong>
                <span>{l.hello}</span>
              </button>
            ))}
          </div>
        </section>
      </main>
      <PhoneVerifySheet open={resuming} onClose={() => setResuming(false)} tr={tr} title={tr('ui.resume_title')}
                        why={tr('ui.resume_hint')} verifyLabel={tr('ui.resume_go')}
                        send={(phone) => { setResumePhone(phone); return api.resumeSend(phone, lang); }}
                        verify={async (code) => {
                          const snapshot = await api.resumeVerify(resumePhone, code, lang);
                          setResuming(false);
                          onResumed(snapshot);
                        }} />
      <div className="sticky-bar">
        <Button block onClick={onStart} icon={saved ? undefined : ArrowRight}>
          {saved ? tr('ui.new_chat') : tr('ui.start')}
        </Button>
      </div>
    </div>
  );
}
