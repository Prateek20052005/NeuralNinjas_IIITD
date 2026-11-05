import { Fragment, useEffect, useState } from 'react';
import { ChevronDown, KeyRound, LogOut, Moon, Phone, RefreshCw, Sun } from 'lucide-react';
import { api } from '../api.js';
import { money } from '../lib/ui.js';
import BrandMark from '../components/BrandMark.jsx';
import Button from '../components/Button.jsx';
import Note from '../components/Note.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import TextField from '../components/TextField.jsx';

// Staff-only desktop view (English): statistics, who is buying, the conversion predictor (which leads to call), and
// the applications the app could not close on its own (KYC reviews, salesperson callbacks: the only place a full
// phone number is shown). Everything needs the back-office key.
const KEY = 'accel-office-key';
const BADGE = { PASS: 'approved', RETAKE: 'retake', REVIEW: 'review', REJECT: 'rejected', INCOMPLETE: 'incomplete' };
const STAGE = {
  chat_started: 'Chatting', quote_ready: 'Quote ready', price_pushback: 'Asked for a lower price', price_offer: 'Negotiating',
  price_handoff: 'Wants a lower price', sales_callback_requested: 'Callback requested', phone_verified: 'Mobile verified',
  quote_accepted: 'Plan accepted', consent_given: 'Consent given', document_read: 'Uploading documents',
  kyc_checked: 'KYC checked', installation_booked: 'Installation booked', resumed: 'Continued on another phone',
};
const KIND = { micro: 'Shop / service', prof: 'Office / clinic', multi: 'Multi-outlet', mfg: 'Factory', 'not yet': 'Not answered yet' };
const TABS = [['overview', 'Overview'], ['customers', 'Customers'], ['leads', 'Leads to call'], ['applications', 'Applications']];
const pct = (x) => `${Math.round(x * 100)}%`;

function readKey() {
  try { return sessionStorage.getItem(KEY) || ''; } catch { return ''; }
}
function saveKey(k) {
  try { if (k) sessionStorage.setItem(KEY, k); else sessionStorage.removeItem(KEY); } catch { /* not available */ }
}

/** One horizontal bar per row, one hue, the number written next to it (no legend needed for a single series). */
function Bars({ rows, of, unit = '' }) {
  const top = of ?? Math.max(1, ...rows.map((r) => r.count));
  return (
    <ul className="bars">
      {rows.map((r) => (
        <li key={r.label} title={`${r.label}: ${r.count}${unit}${of ? ` (${pct(r.count / top)} of ${of})` : ''}`}>
          <span className="bars__label">{r.label}</span>
          <span className="bars__track"><span className="bars__fill" style={{ width: `${(100 * r.count) / top}%` }} /></span>
          <span className="bars__value">{r.count}{unit}{of && r.count !== of ? <small> · {pct(r.count / top)}</small> : null}</span>
        </li>
      ))}
    </ul>
  );
}

/** Chance of activation as a small bar + number (the number carries the meaning, the bar helps scanning). */
function Chance({ score }) {
  if (score == null) return <span className="t-secondary">—</span>;
  return (
    <span className="chance" title={`${pct(score)} chance of activation, from past results`}>
      <span className="chance__track"><span className="chance__fill" style={{ width: `${Math.min(100, score * 200)}%` }} /></span>
      <b>{pct(score)}</b>
    </span>
  );
}

function Overview({ stats, rows }) {
  if (!stats) return <Note>Loading…</Note>;
  const tiles = [
    ['Applications', stats.funnel[0].count],
    ['Plans accepted', stats.funnel[2].count],
    ['Monthly value sold (incl. GST)', money(stats.money.monthly_with_gst)],
    ['Average plan', stats.money.average_monthly ? money(stats.money.average_monthly) : '—'],
    ['Callbacks to make', rows.filter((r) => r.sales_callback).length],
    ['KYC to review', rows.filter((r) => r.kyc && r.kyc.decision !== 'PASS').length],
  ];
  const live = stats.funnel.map((f) => ({ label: f.stage, count: f.count }));
  const past = stats.history.funnel.map((f) => ({ label: f.stage, count: f.count }));
  const counts = (obj, names = {}) => Object.entries(obj).sort((a, b) => b[1] - a[1]).map(([k, n]) => ({ label: names[k] || k, count: n }));
  const p = stats.predictor;
  return (
    <div className="stack">
      <div className="office__stats">
        {tiles.map(([label, value]) => <div className="stat" key={label}><b>{value}</b><span>{label}</span></div>)}
      </div>
      <div className="office-grid">
        <section className="card office-card">
          <h2 className="t-headline">In the app (live)</h2>
          <p className="t-footnote t-secondary">Applications from the last {72} hours of activity.</p>
          {live[0].count ? <Bars rows={live} of={live[0].count} /> : <Note>No applications yet.</Note>}
        </section>
        <section className="card office-card">
          <h2 className="t-headline">Before the app: sales-led, Apr–Jun 2026</h2>
          <p className="t-footnote t-secondary">{stats.history.funnel[0].count.toLocaleString('en-IN')} leads · {stats.history.avg_days_to_activate} days on average to activate.</p>
          <Bars rows={past} of={past[0].count} />
        </section>
        <section className="card office-card">
          <h2 className="t-headline">Offers and discounts</h2>
          <Bars rows={[
            { label: 'New-customer offer given', count: stats.offers.welcome },
            { label: 'Discount given in the chat', count: stats.offers.discounted },
            { label: 'Asked for a salesperson', count: stats.offers.callbacks },
            { label: 'Paying 3/6/12 months ahead', count: stats.offers.pay_ahead },
            { label: 'Agreed to offers and news', count: stats.offers.marketing_ok },
          ]} />
          <p className="t-footnote t-secondary">Setup fees still due on accepted plans: {money(stats.money.setup_due)}</p>
        </section>
        <section className="card office-card">
          <h2 className="t-headline">Who is applying</h2>
          {Object.keys(stats.languages).length ? (
            <>
              <h3 className="section-label">Language</h3>
              <Bars rows={counts(stats.languages)} />
              <h3 className="section-label">Kind of business</h3>
              <Bars rows={counts(stats.kinds, KIND)} />
            </>
          ) : <Note>No applications yet.</Note>}
        </section>
        <section className="card office-card">
          <h2 className="t-headline">Why leads dropped before the app</h2>
          <Bars rows={stats.history.top_drop_reasons.map((r) => ({ label: r.reason, count: r.count }))} />
        </section>
        <section className="card office-card">
          <h2 className="t-headline">What sells together</h2>
          <p className="t-footnote t-secondary">From what 368 past customers bought, per kind of business. The plan lists extras in this order and says how often similar businesses chose each.</p>
          <table className="office-table compact">
            <thead><tr><th>Kind</th><th>Customers with…</th><th>…also took</th><th className="num">Took it</th><th className="num">Usually</th></tr></thead>
            <tbody>
              {(stats.sells_together || []).map((r) => (
                <tr key={`${r.kind}-${r.if}-${r.then}`} title={`${r.pct}% of ${r.customers} ${KIND[r.kind] || r.kind} customers with ${r.if} also took ${r.then}, against ${r.usual_pct}% of all of them (${r.lift}× as likely)`}>
                  <td>{KIND[r.kind] || r.kind}</td><td>{r.if}</td><td>{r.then}</td>
                  <td className="num"><b>{r.pct}%</b></td><td className="num t-secondary">{r.usual_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="card office-card">
          <h2 className="t-headline">Conversion predictor</h2>
          {p ? (
            <>
              <p className="t-callout">On {p.test_leads.toLocaleString('en-IN')} past leads it never saw, the top 10% it picks
                activated at <b>{p.top10_activated_pct}%</b>, against {p.base_activated_pct}% on average
                ({(p.top10_activated_pct / p.base_activated_pct).toFixed(1)}× better). Ranking quality (AUC): <b>{p.auc}</b>.</p>
              <p className="t-footnote t-secondary">Strongest signals: {p.strongest.map((s) => `${s.factor} (${s.effect})`).join(', ')}.</p>
              <p className="t-footnote t-secondary">Left out: {p.left_out.join('; ')}.</p>
            </>
          ) : <Note>Starting up…</Note>}
        </section>
      </div>
    </div>
  );
}

function Customers({ customers }) {
  if (!customers) return <Note>Loading…</Note>;
  if (!customers.length) return <Note>No plans accepted yet.</Note>;
  return (
    <div className="office-scroll">
      <table className="office-table">
        <thead>
          <tr><th>Ref</th><th>Business</th><th>Plan</th><th className="num">Monthly</th><th>Terms</th><th>Offers</th>
            <th>Mobile</th><th>KYC</th><th>Accepted</th></tr>
        </thead>
        <tbody>
          {customers.map((c) => (
            <tr key={c.ref}>
              <td className="t-mono">{c.ref}</td>
              <td><b>{c.business || KIND[c.kind] || '—'}</b><br /><span className="t-footnote t-secondary">{[c.city, c.business && KIND[c.kind], c.language].filter(Boolean).join(' · ')}</span></td>
              <td className="t-footnote">{c.plan.join(', ')}</td>
              <td className="num">{money(c.monthly_with_gst)}</td>
              <td className="t-footnote">{c.contract_months}-month contract<br />
                {c.billing_months > 1 ? `pays every ${c.billing_months} months` : 'pays monthly'} · setup {money(c.setup_due)}</td>
              <td className="t-footnote">{[c.welcome && 'New-customer offer', c.discount_pct && `${c.discount_pct}% chat discount`]
                .filter(Boolean).join(', ') || '—'}</td>
              <td className="t-footnote"><span className="t-mono">{c.phone || '—'}</span>{c.marketing_consent ? <><br /><span className="t-secondary">OK to send offers</span></> : null}</td>
              <td>{c.kyc ? <StatusBadge status={BADGE[c.kyc]}>{c.kyc}</StatusBadge> : <span className="t-secondary">Pending</span>}</td>
              <td className="t-footnote">{c.accepted_at ? c.accepted_at.replace('T', ' ').slice(0, 16) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Leads({ leads, error }) {
  if (error) return <Note tone="warn">{error}</Note>;
  if (!leads) return <Note>Loading…</Note>;
  const m = leads.model;
  return (
    <div className="stack">
      <Note tone="info" title="Which past leads to call first">
        These leads dropped for a reason the app now answers (no visit needed, a clear price, mobile-only plans, no GST
        needed…). They are ranked by their chance of activating, learned from {m.leads.toLocaleString('en-IN')} past leads:
        the top 10% it picks activate {(m.top10_activated_pct / m.base_activated_pct).toFixed(1)}× more often than average.
        A score is a reason to call first, never a reason to treat anyone differently.
      </Note>
      <div className="office-scroll">
        <table className="office-table">
          <thead>
            <tr><th>Chance</th><th>Lead</th><th>Business</th><th>Came via</th><th>Dropped because</th>
              <th>What's different now</th><th>Why this score</th></tr>
          </thead>
          <tbody>
            {leads.leads.map((l) => (
              <tr key={l.lead_id}>
                <td><Chance score={l.score} /></td>
                <td className="t-footnote"><span className="t-mono">{l.lead_id}</span><br /><span className="t-secondary">{l.contact}</span></td>
                <td><b>{l.business}</b><br /><span className="t-footnote t-secondary">{l.type} · {l.city}</span></td>
                <td className="t-footnote">{l.source}</td>
                <td className="t-footnote">{l.drop_reason}<br /><span className="t-secondary">at “{l.stage}”</span></td>
                <td className="t-footnote">{l.now}</td>
                <td className="t-footnote">
                  {l.up.length ? <span className="why-up">+ {l.up.join(', ')}</span> : null}
                  {l.down.length ? <><br /><span className="why-down">− {l.down.join(', ')}</span></> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Applications({ rows, open, setOpen }) {
  const stage = (r) => STAGE[r.timeline.at(-1)?.step] || '—';
  if (!rows.length) {
    return <Note>No open applications right now. Applications are deleted automatically after 72 hours without activity.</Note>;
  }
  return (
    <div className="office-scroll">
      <table className="office-table">
        <thead>
          <tr>
            <th>Ref</th><th>Business</th><th>City</th><th>Kind</th><th className="num">Monthly</th>
            <th>Stage</th><th>Chance</th><th>KYC</th><th>Callback</th><th aria-label="Details" />
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
                  <td><b>{r.business || KIND[r.kind] || '—'}</b><br /><span className="t-footnote t-secondary t-mono">{r.gstin || 'No GST'}</span></td>
                  <td>{r.city || '—'}</td>
                  <td>{KIND[r.kind] || '—'}</td>
                  <td className="num">{r.monthly ? money(r.monthly) : '—'}</td>
                  <td>{stage(r)}{r.price?.discount_pct ? <><br /><span className="t-footnote t-secondary">{r.price.discount_pct}% off · {r.price.asks} asks</span></> : null}</td>
                  <td>{r.accepted ? <span className="t-footnote t-secondary">Accepted</span> : <Chance score={r.conversion?.score} />}</td>
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
                    <td colSpan={10}>
                      <div className="stack" style={{ paddingTop: 12 }}>
                        {r.conversion && (r.conversion.up.length || r.conversion.down.length) ? (
                          <p className="t-footnote">Chance of activating: {pct(r.conversion.score)}
                            {r.conversion.up.length ? <span className="why-up"> · + {r.conversion.up.join(', ')}</span> : null}
                            {r.conversion.down.length ? <span className="why-down"> · − {r.conversion.down.join(', ')}</span> : null}</p>
                        ) : null}
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
  );
}

export default function BackOffice({ theme, onTheme }) {
  const [key, setKey] = useState(readKey);
  const [draft, setDraft] = useState('');
  const [rows, setRows] = useState(null);
  const [stats, setStats] = useState(null);
  const [customers, setCustomers] = useState(null);
  const [leads, setLeads] = useState(null);
  const [leadsError, setLeadsError] = useState('');
  const [tab, setTab] = useState('overview');
  const [error, setError] = useState('');
  const [open, setOpen] = useState(null);
  const [loading, setLoading] = useState(false);

  async function load(k = key) {
    if (!k) return;
    setLoading(true);
    setError('');
    try {
      const [apps, st, cu] = await Promise.all([api.backoffice(k), api.officeStats(k), api.officeCustomers(k)]);
      setRows(apps);
      setStats(st);
      setCustomers(cu);
      saveKey(k);
      setKey(k);
      api.officeLeads(k).then((l) => { setLeads(l); setLeadsError(''); })
        .catch((e) => setLeadsError(e.message || 'Could not load the leads.'));   // may still be starting up
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
          <p className="t-callout t-secondary">Statistics, customers, which leads to call, and applications the app could not close on its own.</p>
          <TextField label="Back-office key" type="password" autoComplete="current-password" value={draft}
                     onChange={(e) => setDraft(e.target.value)} />
          {error && <Note tone="warn">{error}</Note>}
          <Button type="submit" variant="trust" icon={KeyRound} disabled={!draft.trim() || loading}>Open</Button>
        </form>
      </div>
    );
  }

  return (
    <div className="office">
      <div className="office__bar">
        <BrandMark size={28} />
        <span className="t-footnote t-secondary">Back office</span>
        <nav className="office-tabs" role="tablist" aria-label="Back office sections">
          {TABS.map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={tab === id} className="office-tab" onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
        <span className="grow" />
        <Button size="sm" variant="secondary" icon={RefreshCw} onClick={() => load()} disabled={loading}>Refresh</Button>
        <Button size="sm" variant="plain" icon={LogOut} onClick={() => { saveKey(''); setKey(''); setRows(null); }}>Sign out</Button>
        {themeBtn}
      </div>
      <main className="office__main" role="tabpanel">
        {error && <Note tone="warn">{error}</Note>}
        {tab === 'overview' && <Overview stats={stats} rows={rows} />}
        {tab === 'customers' && <Customers customers={customers} />}
        {tab === 'leads' && <Leads leads={leads} error={leadsError} />}
        {tab === 'applications' && <Applications rows={rows} open={open} setOpen={setOpen} />}
      </main>
    </div>
  );
}
