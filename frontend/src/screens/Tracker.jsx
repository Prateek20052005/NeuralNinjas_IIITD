import { useEffect, useState } from 'react';
import { CircleCheck, CircleDashed, Clock, FileText, Shield, Trash2 } from 'lucide-react';
import { api } from '../api.js';
import { longDate } from '../i18n.js';
import { OUTCOME, shortTime } from '../lib/ui.js';
import AppHeader from '../components/AppHeader.jsx';
import BottomSheet from '../components/BottomSheet.jsx';
import Button from '../components/Button.jsx';
import DecisionCard from '../components/DecisionCard.jsx';
import Note from '../components/Note.jsx';
import Timeline from '../components/Timeline.jsx';

function steps(status, tr, lang) {
  const at = (step) => status.timeline.filter((s) => s.step === step).pop()?.at;
  const decision = status.kyc?.decision;
  const live = status.quote?.expected_live;
  const booked = at('installation_booked');
  const list = [
    { title: tr('ui.step.quote_accepted'), at: at('quote_accepted') },
    ...(status.esign ? [{ title: tr('ui.step.signed'), at: status.esign.signed_at,
                          detail: tr('ui.step.signed_detail', { ref: status.esign.reference }) }] : []),
    { title: tr('ui.step.consent_given'), at: at('consent_given') },
    { title: tr('ui.step.documents'), at: at('document_read') || at('document_fetched') },
    { title: tr('ui.step.kyc'), at: decision === 'PASS' ? at('kyc_checked') : null,
      detail: decision && decision !== 'PASS' ? status.kyc.headline : null },
    { title: tr('ui.step.installation'), at: booked,
      detail: live ? tr('ui.step.installation_on', { date: longDate(live, lang) }) : null },
    { title: tr('ui.step.active'), at: at('activated') },
  ];
  const now = list.findIndex((s) => !s.at);
  return list.map((s, i) => ({
    title: s.title,
    detail: s.detail || (s.at ? shortTime(s.at, lang) : null),
    state: s.at ? 'done' : i === now ? 'now' : 'todo',
  }));
}

const SERVICE_ICON = { live: CircleCheck, installing: Clock, waiting: CircleDashed };

/** One row per product: waiting for KYC, being set up (ready-by date from its install time), or live. */
function Services({ products, tr, lang }) {
  return (
    <ul className="svc-list">
      {products.map((p) => {
        const Icon = SERVICE_ICON[p.status];
        const detail = p.status === 'live' ? tr('ui.product.live', { date: longDate(p.live_on, lang) })
          : p.status === 'installing' ? tr('ui.product.installing', { date: longDate(p.ready_by, lang) })
            : tr('ui.product.waiting');
        return (
          <li key={p.product_id}>
            <span>
              <span className="svc-name">{p.quantity > 1 ? `${p.name} × ${p.quantity}` : p.name}</span>
              <span className="svc-detail t-footnote t-secondary">{detail}</span>
            </span>
            <Icon size={22} strokeWidth={1.75} aria-hidden="true"
                  style={{ color: p.status === 'live' ? 'var(--color-success)' : 'var(--color-ink-2)', flex: 'none' }} />
          </li>
        );
      })}
    </ul>
  );
}

export default function Tracker({ state, update, tr, actions, go, onHome, onErased }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [erasing, setErasing] = useState(false);
  const lang = state.lang;

  useEffect(() => {
    api.status(state.id).then(setStatus).catch((e) => setError(e.status === 404 ? '' : tr('ui.offline')));
  }, [state.id, state.kyc]); // eslint-disable-line react-hooks/exhaustive-deps

  async function erase() {
    setErasing(true);
    try {
      const out = await api.erase(state.id);
      onErased(out.message);
    } catch {
      setError(tr('ui.error'));
      setErasing(false);
      setConfirm(false);
    }
  }

  const kyc = status?.kyc;
  const live = status?.quote?.expected_live;
  const fixable = kyc && ['RETAKE', 'INCOMPLETE'].includes(kyc.decision);

  return (
    <div className="app-shell" lang={lang}>
      <AppHeader title={tr('ui.tracker_title')} onBack={onHome} backLabel={tr('ui.back')} actions={actions} />
      <main className="page screen-in">
        {!status ? (
          <>
            <div className="skeleton" style={{ height: 150 }} />
            <div className="skeleton" style={{ height: 260 }} />
            {error && <Note tone="warn">{error}</Note>}
          </>
        ) : (
          <>
            {kyc ? (
              <DecisionCard
                outcome={OUTCOME[kyc.decision]}
                title={kyc.headline}
                body={kyc.issues.length > 0 ? (
                  <ul className="issue-list">{kyc.issues.map((i, n) => <li key={n}>{i.message}</li>)}</ul>
                ) : null}
                next={status.active ? tr('ui.next.ACTIVE')
                  : tr(`ui.next.${kyc.decision}`, { date: live ? longDate(live, lang) : '' })}
                action={fixable ? <Button block icon={FileText} onClick={() => update({ screen: 'documents' })}>{tr('ui.fix_docs')}</Button> : null}
              />
            ) : (
              <section className="card stack">
                <p className="t-headline">{tr('ui.next.NONE')}</p>
                <Button block onClick={() => update({ screen: status.consent ? 'documents' : 'consent' })}>
                  {status.consent ? tr('ui.documents_title') : tr('ui.consent_continue')}
                </Button>
              </section>
            )}

            {status.partner && (
              <Note tone="trust">{tr(status.partner.assisted ? 'ui.assisted_by' : 'ui.referred_by', { partner: status.partner.name })}</Note>
            )}

            {status.products?.length > 0 && (
              <section className="card">
                <h2 className="section-label" style={{ margin: '0 0 16px' }}>{tr('ui.products_title')}</h2>
                <Services products={status.products} tr={tr} lang={lang} />
                <p className="foot-note" style={{ marginTop: 16 }}>{tr('ui.billing_starts')}</p>
              </section>
            )}

            <section className="card">
              <h2 className="section-label" style={{ margin: '0 0 16px' }}>{tr('ui.progress')}</h2>
              <Timeline steps={steps(status, tr, lang)} label={tr('ui.progress')} />
            </section>

            {error && <Note tone="warn">{error}</Note>}
            <Button variant="plain" block icon={Shield} onClick={() => go('privacy')}>{tr('ui.privacy_open')}</Button>
            <Button variant="plain" block icon={Trash2} className="danger-btn" onClick={() => setConfirm(true)}>
              {tr('ui.delete_data')}
            </Button>
            <p className="foot-note">{tr('ui.delete_hint')}</p>
          </>
        )}
      </main>

      <BottomSheet open={confirm} onClose={() => setConfirm(false)} title={tr('ui.delete_title')} closeLabel={tr('ui.cancel')}>
        <p className="t-body t-secondary">{tr('ui.delete_confirm')}</p>
        <Button variant="destructive" block icon={Trash2} onClick={erase} disabled={erasing}>{tr('ui.delete_data')}</Button>
        <Button variant="secondary" block onClick={() => setConfirm(false)}>{tr('ui.cancel')}</Button>
      </BottomSheet>
    </div>
  );
}
