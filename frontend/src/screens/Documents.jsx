import { useEffect, useState } from 'react';
import { Camera, ShieldCheck } from 'lucide-react';
import { api } from '../api.js';
import AppHeader from '../components/AppHeader.jsx';
import Button from '../components/Button.jsx';
import FieldPreviewList from '../components/FieldPreviewList.jsx';
import Note from '../components/Note.jsx';
import ProgressIndicator from '../components/ProgressIndicator.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import TextField from '../components/TextField.jsx';
import UploadTile from '../components/UploadTile.jsx';

const DOCS = ['gst_certificate', 'udyam_certificate', 'address_proof', 'signatory_id'];
// details shown back so the owner can see we read it right (IDs arrive masked from the server)
const PREVIEW = {
  gst_certificate: ['legal_name', 'trade_name', 'gstin'],
  udyam_certificate: ['enterprise_name', 'udyam_number'],
  address_proof: ['billed_to', 'bill_date'],
  signatory_id: ['name', 'valid_till'],
};
const MONO = new Set(['gstin', 'udyam_number']);
const MAX_SIDE = 2000;

// Phone photos are often 4000 px and several MB; the server reads 2000 px just as well. Shrinking here
// makes uploads fast on slow mobile data. Falls back to the original file if the browser can't do it.
async function shrink(file) {
  try {
    const img = await createImageBitmap(file);
    const scale = MAX_SIDE / Math.max(img.width, img.height);
    if (scale >= 1) return file;
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((ok) => canvas.toBlob(ok, 'image/jpeg', 0.9));
    return blob ? new File([blob], 'photo.jpg', { type: 'image/jpeg' }) : file;
  } catch {
    return file;
  }
}

export default function Documents({ state, update, tr, actions }) {
  const docs = state.docs || {};
  const [reading, setReading] = useState({});
  const [udyam, setUdyam] = useState('');
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const [last, setLast] = useState(null); // the document just read: its details are shown back
  // Which documents this owner needs: without GST only address proof and ID; GST and Udyam stay on screen as optional
  const [required, setRequired] = useState(null);
  useEffect(() => {
    api.status(state.id)
      .then((s) => {
        setRequired(Object.fromEntries(Object.entries(s.documents).map(([k, v]) => [k, v.required])));
        // The server is the record: after a reload or on another phone, show what it has already read
        const local = state.docs || {};
        const merged = { ...local };
        let changed = false;
        for (const [k, v] of Object.entries(s.documents)) {
          if (v.uploaded && (local[k]?.ok !== v.ok || !local[k])) {
            merged[k] = { ok: v.ok, fields: v.fields, message: v.ok ? '' : v.message };
            changed = true;
          }
        }
        const patch = {};
        if (changed) patch.docs = merged;
        if (s.udyam_number && !state.udyamSaved) patch.udyamSaved = s.udyam_number;
        if (Object.keys(patch).length) update(patch);
      })
      .catch(() => setRequired(null)); // unknown: every document counts
  }, [state.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const noGst = required && !required.gst_certificate;
  const needed = DOCS.filter((d) => !required || required[d]);
  const ready = needed.filter((d) => docs[d]?.ok || (d === 'udyam_certificate' && state.udyamSaved)).length;

  async function onFile(type, file) {
    setReading((r) => ({ ...r, [type]: true }));
    setError('');
    try {
      const out = await api.upload(state.id, type, await shrink(file));
      update({ docs: { ...(state.docs || {}), [type]: out } });
      setLast(type);
    } catch (e) {
      setError(e.message || tr(e.status === 0 ? 'ui.offline' : 'ui.error'));
    } finally {
      setReading((r) => ({ ...r, [type]: false }));
    }
  }

  async function saveUdyam() {
    try {
      const out = await api.udyamNumber(state.id, udyam);
      update({ udyamSaved: out.udyam_number });
    } catch (e) {
      setError(e.message || tr('ui.error'));
    }
  }

  async function check() {
    setChecking(true);
    setError('');
    try {
      const kyc = await api.checkKyc(state.id);
      update({ kyc, screen: 'tracker' });
    } catch (e) {
      setError(e.message || tr('ui.error'));
      setChecking(false);
    }
  }

  const tileState = (type) => (reading[type] ? 'reading' : !docs[type] ? 'empty' : docs[type].ok ? 'read' : 'retake');
  // the newest photo that needs retaking gets the big card: instant feedback is the point of this screen
  const retake = [last, ...DOCS].find((d) => d && docs[d] && !docs[d].ok && !reading[d]);
  const shown = last && docs[last]?.ok ? last : null;
  const anyReading = Object.values(reading).some(Boolean);

  return (
    <div className="app-shell" lang={state.lang}>
      <AppHeader title={tr('ui.documents_title')} onBack={() => update({ screen: 'tracker' })} backLabel={tr('ui.back')}
                 actions={actions}>
        <ProgressIndicator current={ready} total={needed.length}
                           formatLabel={(n, total) => tr('ui.docs_ready', { n, total })} />
      </AppHeader>
      <main className="page screen-in">
        <p className="lead">{tr('ui.documents_hint')}</p>
        {noGst && <Note>{tr('ui.no_gst_docs')}</Note>}

        {retake && (
          <section className="card ab-retake" role="alert">
            <StatusBadge status="retake">{tr('ui.retake')} · {tr(`doc.${retake}`)}</StatusBadge>
            <p className="t-headline" style={{ fontSize: '1.1875rem' }}>{docs[retake].message}</p>
            <p className="t-callout t-secondary">{tr('ui.retake_tip')}</p>
            <label className="ab-btn ab-btn--secondary ab-btn--block">
              <input type="file" accept="image/*" className="visually-hidden"
                     onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(retake, f); e.target.value = ''; }} />
              <Camera size={18} strokeWidth={1.75} aria-hidden="true" /> {tr('ui.retake')}
            </label>
          </section>
        )}

        <section className="ab-tiles" aria-label={tr('ui.documents_title')}>
          {DOCS.map((type) => (
            <UploadTile key={type} name={tr(`doc.${type}`)} state={tileState(type)}
                        reason={docs[type] && !docs[type].ok ? docs[type].message : ''}
                        tag={required && !required[type] ? tr('ui.optional') : null}
                        onFile={(f) => onFile(type, f)}
                        t={{ add: tr('ui.add_photo'), reading: tr('ui.reading_short'), read: tr('ui.read_ok'), retake: tr('ui.retake') }} />
          ))}
        </section>

        {!docs.udyam_certificate?.ok && (
          <section className="card stack">
            <TextField label={tr('ui.or_type_udyam')} placeholder="UDYAM-MH-00-0000000" mono autoComplete="off"
                       autoCapitalize="characters" hint={state.udyamSaved ? `${tr('ui.saved')}: ${state.udyamSaved}` : tr('ui.udyam_hint')}
                       value={udyam} onChange={(e) => setUdyam(e.target.value)} />
            <Button variant="secondary" disabled={udyam.trim().length < 10} onClick={saveUdyam}>
              {state.udyamSaved ? tr('ui.saved') : tr('ui.save')}
            </Button>
          </section>
        )}

        {shown && (
          <FieldPreviewList
            title={tr('ui.found_on', { doc: tr(`doc.${shown}`) })}
            fields={PREVIEW[shown].filter((k) => docs[shown].fields?.[k]).map((k) => ({
              label: tr(`field.${k}`),
              node: MONO.has(k) ? <span className="t-mono">{docs[shown].fields[k]}</span> : docs[shown].fields[k],
            }))}
            footnote={tr('ui.photo_gone')}
          />
        )}

        {error && <div role="alert"><Note tone="warn">{error}</Note></div>}
        <Note tone="trust">{tr('ui.privacy_line')}</Note>
      </main>
      <div className="ab-docs-bar">
        <Button block icon={checking ? undefined : ShieldCheck} onClick={check}
                disabled={checking || anyReading || (Object.keys(docs).length === 0 && !state.udyamSaved)}>
          {checking ? tr('ui.checking') : tr('ui.submit_documents')}
        </Button>
      </div>
    </div>
  );
}
