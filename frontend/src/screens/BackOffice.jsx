import { Fragment, useEffect, useState } from 'react';
import { ChevronDown, KeyRound, LogOut, Moon, Phone, RefreshCw, Sun } from 'lucide-react';
import { api } from '../api.js';
import { money } from '../lib/ui.js';
import BrandMark from '../components/BrandMark.jsx';
import Button from '../components/Button.jsx';
import Note from '../components/Note.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import TextField from '../components/TextField.jsx';

// Staff-only desktop view (English). Shows what the chatbot could not close: KYC decisions with evidence,
// salesperson callbacks (the only place a full phone number is shown) and where each application is stuck.
const KEY = 'accel-office-key';
const BADGE = { PASS: 'approved', RETAKE: 'retake', REVIEW: 'review', REJECT: 'rejected', INCOMPLETE: 'incomplete' };
const STAGE = {
  chat_started: 'Chatting', quote_ready: 'Quote ready', price_offer: 'Negotiating', price_handoff: 'Wants a lower price',
  sales_callback_requested: 'Callback requested', quote_accepted: 'Plan accepted', consent_given: 'Consent given',
  document_read: 'Uploading documents', kyc_checked: 'KYC checked', installation_booked: 'Installation booked',
};
const KIND = { micro: 'Shop / service', prof: 'Office / clinic', multi: 'Multi-outlet', mfg: 'Factory' };

function readKey() {
  try { return sessionStorage.getItem(KEY) || ''; } catch { return ''; }
}
function saveKey(k) {
  try { if (k) sessionStorage.setItem(KEY, k); else sessionStorage.removeItem(KEY); } catch { /* not available */ }
}

export default function BackOffice({ theme, onTheme }) {
  const [key, setKey] = useState(readKey);
  const [draft, setDraft] = useState('');
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(null);
  const [loading, setLoading] = useState(false);

  async function load(k = key) {
    if (!k) return;
    setLoading(true);
    setError('');
    try {
      setRows(await api.backoffice(k));
      saveKey(k);
      setKey(k);
    } catch (e) {
      if (e.status === 401) {
        saveKey('');
        setKey('');
        setError('That key is not right. Ask the admin for the back-office key.');
      } else setError(e.status === 0 ? "Can't reach the server." : 'Something went wrong. Try again.');
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const themeBtn = (
    <button type="button" className="ab-icon-btn" aria-label={theme === 'dark' ? 'Use light mode' : 'Use dark mode'} onClick={onTheme}>
      {theme === 'dark' ? <Sun size={21} strokeWidth={1.75} aria-hidden="true" /> : <Moon size={21} strokeWidth={1.75} aria-hidden="true" />}
    </button>
  );

  if (!key || rows === null) {
    return (
      <div className="office">
        <div className="office__bar"><BrandMark size={28} /><span className="t-footnote t-secondary">Back office</span><span className="grow" />{themeBtn}</div>
        <form className="card office-login" onSubmit={(e) => { e.preventDefault(); load(draft.trim()); }}>
          <h1 className="t-title">Sales & partner back office</h1>
          <p className="t-callout t-secondary">Applications the app could not close on its own: KYC reviews, callbacks and stuck orders.</p>
          <TextField label="Back-office key" type="password" autoComplete="current-password" value={draft}
                     onChange={(e) => setDraft(e.target.value)} />
          {error && <Note tone="warn">{error}</Note>}
          <Button type="submit" variant="trust" icon={KeyRound} disabled={!draft.trim() || loading}>Open</Button>
        </form>
      </div>
    );
  }

  const stage = (r) => STAGE[r.timeline.at(-1)?.step] || '—';
  const stats = [
    ['Applications', rows.length],
    ['Callbacks to make', rows.filter((r) => r.sales_callback).length],
    ['KYC to review', rows.filter((r) => r.kyc && r.kyc.decision !== 'PASS').length],
    ['Approved', rows.filter((r) => r.kyc?.decision === 'PASS').length],
    ['Monthly value (incl. GST)', money(rows.reduce((s, r) => s + (r.monthly || 0), 0))],
  ];

  return (
    <div className="office">
      <div className="office__bar">
        <BrandMark size={28} />
        <span className="t-footnote t-secondary">Back office</span>
        <span className="grow" />
        <Button size="sm" variant="secondary" icon={RefreshCw} onClick={() => load()} disabled={loading}>Refresh</Button>
        <Button size="sm" variant="plain" icon={LogOut} onClick={() => { saveKey(''); setKey(''); setRows(null); }}>Sign out</Button>
        {themeBtn}
      </div>
      <main className="office__main">
        <div className="office__stats">
          {stats.map(([label, value]) => <div className="stat" key={label}><b>{value}</b><span>{label}</span></div>)}
        </div>
        {error && <Note tone="warn">{error}</Note>}
        {rows.length === 0 ? (
          <Note>No open applications right now. Applications are deleted automatically after 72 hours without activity.</Note>
        ) : (
          <div className="office-scroll">
            <table className="office-table">
              <thead>
                <tr>
                  <th>Ref</th><th>Business</th><th>City</th><th>Kind</th><th className="num">Monthly</th>
                  <th>Stage</th><th>KYC</th><th>Callback</th><th aria-label="Details" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const isOpen = open === r.id;
                  const cb = r.sales_callback;
                  return (
                    <Fragment key={r.id}>
                      <tr className={`office-row ${isOpen ? 'is-open' : ''}`} onClick={() => setOpen(isOpen ? null : r.id)}>
                        <td className="t-mono">{r.id.toUpperCase()}</td>
                        <td><b>{r.business || '—'}</b><br /><span className="t-footnote t-secondary t-mono">{r.gstin || 'No GST'}</span></td>
                        <td>{r.city || '—'}</td>
                        <td>{KIND[r.kind] || '—'}</td>
                        <td className="num">{r.monthly ? money(r.monthly) : '—'}</td>
                        <td>{stage(r)}{r.price?.discount_pct ? <><br /><span className="t-footnote t-secondary">{r.price.discount_pct}% off · {r.price.asks} asks</span></> : null}</td>
                        <td>{r.kyc ? <StatusBadge status={BADGE[r.kyc.decision]}>{r.kyc.decision}</StatusBadge> : <span className="t-secondary">—</span>}</td>
                        <td>
                          {cb ? (
                            <a href={`tel:+91${cb.phone}`} onClick={(e) => e.stopPropagation()} className="row-gap">
                              <Phone size={15} strokeWidth={2} aria-hidden="true" /> {cb.phone}
                            </a>
                          ) : '—'}
                          {cb?.target_monthly ? <div className="t-footnote t-secondary">wants {money(cb.target_monthly)}/mo</div> : null}
                        </td>
                        <td>
                          <button type="button" className="ab-icon-btn" aria-expanded={isOpen} aria-label={`Details for ${r.id}`}
                                  onClick={(e) => { e.stopPropagation(); setOpen(isOpen ? null : r.id); }}>
                            <ChevronDown size={20} strokeWidth={1.75} aria-hidden="true"
                                         style={{ transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 200ms' }} />
                          </button>
                        </td>
                      </tr>
                      {isOpen && (
                        <tr className="office-detail">
                          <td colSpan={9}>
                            <div className="stack" style={{ paddingTop: 12 }}>
                              {r.kyc?.evidence?.length ? (
                                <ul className="evidence">
                                  {r.kyc.evidence.map((ev, i) => (
                                    <li key={i}>
                                      <StatusBadge status={BADGE[ev.decision] || 'incomplete'}>{ev.decision}</StatusBadge>
                                      <code>{ev.code}</code>
                                      <span>{ev.evidence}</span>
                                    </li>
                                  ))}
                                </ul>
                              ) : <p className="t-callout t-secondary">No KYC evidence yet.</p>}
                              {r.kyc?.lead_id && <p className="t-footnote t-secondary">Matched lead: <span className="t-mono">{r.kyc.lead_id}</span></p>}
                              {cb && (
                                <p className="t-footnote t-secondary">
                                  Callback reference <b className="t-mono">{cb.reference}</b> · requested {cb.requested_at} in {cb.language} ·
                                  offered {cb.offered_monthly ? money(cb.offered_monthly) : '—'}/mo
                                </p>
                              )}
                              <p className="t-footnote t-secondary">
                                Timeline: {r.timeline.map((s) => STAGE[s.step] || s.step).filter((v, i, a) => a.indexOf(v) === i).join(' → ')}
                              </p>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
