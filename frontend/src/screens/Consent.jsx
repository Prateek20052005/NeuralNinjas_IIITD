import { useEffect, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { api } from '../api.js';
import AppHeader from '../components/AppHeader.jsx';
import Button from '../components/Button.jsx';
import Checkbox from '../components/Checkbox.jsx';
import Note from '../components/Note.jsx';

// DPDP Act: consent is asked before any document is read, per purpose, and nothing is pre-ticked.
export default function Consent({ state, update, tr, actions }) {
  const [text, setText] = useState(null);
  const [hours, setHours] = useState(72);
  const [chosen, setChosen] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.consentText(state.lang).then(setText).catch(() => setError(tr('ui.offline')));
    api.status(state.id).then((s) => s.retention_hours && setHours(s.retention_hours)).catch(() => {});
  }, [state.lang]); // eslint-disable-line react-hooks/exhaustive-deps

  async function agree() {
    setBusy(true);
    setError('');
    try {
      await api.consent(state.id, Object.keys(chosen).filter((k) => chosen[k]));
      update({ consented: true, screen: 'documents' });
    } catch (e) {
      setError(e.message || tr('ui.error'));
      setBusy(false);
    }
  }

  const ready = text && text.purposes.every((p) => !p.required || chosen[p.id]);

  return (
    <div className="app-shell" lang={state.lang}>
      <AppHeader title={tr('ui.tracker_title')} onBack={() => update({ screen: 'tracker' })} backLabel={tr('ui.back')}
                 actions={actions} />
      <main className="page screen-in">
        {!text ? (
          <>
            <div className="skeleton" style={{ height: 64, width: 64 }} />
            <div className="skeleton" style={{ height: 120 }} />
            {error && <Note tone="warn">{error}</Note>}
          </>
        ) : (
          <>
            <section className="trust-hero">
              <span className="trust-badge" aria-hidden="true"><ShieldCheck size={34} strokeWidth={1.75} /></span>
              <h1 className="t-large-title" style={{ fontSize: '1.875rem' }}>{text.title}</h1>
              <p className="consent-body">{text.body}</p>
            </section>
            <Note tone="trust">{tr('ui.consent_secure')}. {tr('ui.consent_kept', { hours })}</Note>
            <div className="inset-group">
              {text.purposes.map((p) => (
                <Checkbox key={p.id} checked={!!chosen[p.id]} onChange={(v) => setChosen({ ...chosen, [p.id]: v })}
                          label={<>{p.text}{p.required && <span className="req-mark" aria-hidden="true"> *</span>}</>}
                          hint={p.required ? null : tr('ui.optional')} required={p.required} />
              ))}
            </div>
            {error && <div role="alert"><Note tone="warn">{error}</Note></div>}
          </>
        )}
      </main>
      <div className="sticky-bar">
        <Button variant="trust" block disabled={!ready || busy} onClick={agree}>{text?.agree || tr('consent.agree')}</Button>
      </div>
    </div>
  );
}
