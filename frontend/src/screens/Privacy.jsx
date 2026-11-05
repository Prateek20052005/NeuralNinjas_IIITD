import { useEffect, useState } from 'react';
import { Download, Trash2 } from 'lucide-react';
import { api } from '../api.js';
import { shortTime } from '../lib/ui.js';
import AppHeader from '../components/AppHeader.jsx';
import BottomSheet from '../components/BottomSheet.jsx';
import Button from '../components/Button.jsx';
import Checkbox from '../components/Checkbox.jsx';
import FieldPreviewList from '../components/FieldPreviewList.jsx';
import Note from '../components/Note.jsx';

const PREVIEW = ['legal_name', 'trade_name', 'gstin', 'enterprise_name', 'udyam_number', 'billed_to', 'bill_date',
                 'name', 'valid_till'];
const MONO = new Set(['gstin', 'udyam_number']);

/** DPDP: what we hold about this application, when it is deleted by itself, the consent given, and controls. */
export default function Privacy({ state, update, tr, onErased }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState(false);
  const lang = state.lang;

  useEffect(() => {
    api.status(state.id).then(setStatus).catch(() => setError(tr('ui.offline')));
  }, [state.id]); // eslint-disable-line react-hooks/exhaustive-deps

  function download() {
    const blob = new Blob([JSON.stringify(status, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `accel-my-data-${status.id.slice(0, 6)}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  async function setMarketing(on) {
    setError('');
    try {
      const out = await api.marketing(state.id, on);
      setStatus((s) => ({ ...s, marketing_consent: out.marketing_consent }));
    } catch {
      setError(tr('ui.error'));
    }
  }

  async function erase() {
    try {
      const out = await api.erase(state.id);
      onErased(out.message);
    } catch {
      setError(tr('ui.error'));
      setConfirm(false);
    }
  }

  const p = status?.profile;
  const held = p ? [
    ['business_name', p.business_name], ['gstin', p.gstin], ['kind', p.kind && tr(`segment.${p.kind}`)],
    ['city', p.city], ['employees', p.employees], ['sites', p.sites],
  ].filter(([, v]) => v !== null && v !== undefined && v !== '') : [];
  const read = status ? Object.entries(status.documents).filter(([, d]) => d.uploaded) : [];

  return (
    <div className="app-shell" lang={lang}>
      <AppHeader title={tr('ui.privacy_title')} onBack={() => update({ screen: state.back && state.back !== 'privacy' ? state.back : 'tracker' })}
                 backLabel={tr('ui.back')} />
      <main className="page screen-in">
        <p className="lead">{tr('ui.privacy_intro')}</p>
        {!status ? (
          <>
            <div className="skeleton" style={{ height: 180 }} />
            {error && <Note tone="warn">{error}</Note>}
          </>
        ) : (
          <>
            <Note tone="trust">{tr('ui.privacy_auto', { date: shortTime(status.delete_after, lang) })}</Note>

            {held.length > 0 && (
              <FieldPreviewList title={tr('ui.privacy_hold')} fields={held.map(([k, v]) => ({
                label: tr(`field.${k}`), node: MONO.has(k) ? <span className="t-mono">{v}</span> : String(v),
              }))} />
            )}

            <section className="card stack">
              <p className="t-headline">{tr('ui.privacy_phone')}</p>
              {status.phone_verified ? (
                <>
                  <p className="t-callout t-secondary">
                    {tr('ui.privacy_phone_verified', { phone: status.phone })}
                  </p>
                  <div className="inset-group">
                    <Checkbox checked={!!status.marketing_consent} onChange={setMarketing}
                              label={tr('ui.privacy_marketing')} hint={tr('ui.privacy_marketing_hint')} />
                  </div>
                </>
              ) : (
                <p className="t-callout t-secondary">{tr('ui.privacy_phone_none')}</p>
              )}
            </section>

            <section className="card stack">
              <p className="t-headline">{tr('ui.privacy_consent')}</p>
              {status.consent ? (
                <>
                  <p className="t-footnote t-secondary">
                    {tr('ui.privacy_given', { date: shortTime(status.consent.given_at, lang), version: status.consent.version })}
                  </p>
                  <ul className="purpose-list">
                    {status.consent.purposes.map((x) => <li key={x}>{tr(`consent.purpose.${x}`)}</li>)}
                  </ul>
                </>
              ) : (
                <p className="t-callout t-secondary">{tr('ui.privacy_consent_none')}</p>
              )}
            </section>

            <section className="stack">
              <h2 className="section-label">{tr('ui.privacy_docs')}</h2>
              {read.length === 0 && <p className="t-callout t-secondary">{tr('ui.privacy_docs_none')}</p>}
              {read.map(([type, d]) => (
                <FieldPreviewList key={type} title={tr(`doc.${type}`)} fields={PREVIEW.filter((k) => d.fields[k]).map((k) => ({
                  label: tr(`field.${k}`), node: MONO.has(k) ? <span className="t-mono">{d.fields[k]}</span> : d.fields[k],
                }))} />
              ))}
              <Note tone="ok">{tr('ui.privacy_photos')}</Note>
            </section>

            {error && <Note tone="warn">{error}</Note>}
            <Button variant="secondary" block icon={Download} onClick={download}>{tr('ui.privacy_download')}</Button>
            <Button variant="destructive" block icon={Trash2} onClick={() => setConfirm(true)}>{tr('ui.delete_data')}</Button>
            <p className="foot-note">{tr('ui.delete_hint')}</p>
          </>
        )}
      </main>
      <BottomSheet open={confirm} onClose={() => setConfirm(false)} title={tr('ui.delete_title')} closeLabel={tr('ui.cancel')}>
        <p className="t-body t-secondary">{tr('ui.delete_confirm')}</p>
        <Button variant="destructive" block icon={Trash2} onClick={erase}>{tr('ui.delete_data')}</Button>
        <Button variant="secondary" block onClick={() => setConfirm(false)}>{tr('ui.cancel')}</Button>
      </BottomSheet>
    </div>
  );
}
