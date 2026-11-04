import { useEffect, useState } from 'react';
import { FileText, Shield, Trash2 } from 'lucide-react';
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
    { title: tr('ui.step.consent_given'), at: at('consent_given') },
    { title: tr('ui.step.documents'), at: at('document_read') },
    { title: tr('ui.step.kyc'), at: decision === 'PASS' ? at('kyc_checked') : null,
      detail: decision && decision !== 'PASS' ? status.kyc.headline : null },
    { title: tr('ui.step.installation'), at: booked,
      detail: live ? tr('ui.step.installation_on', { date: longDate(live, lang) }) : null },
  ];
  const now = list.findIndex((s) => !s.at);
  return list.map((s, i) => ({
    title: s.title,
    detail: s.detail || (s.at ? shortTime(s.at, lang) : null),
    state: booked && i === list.length - 1 ? 'now' : s.at ? 'done' : i === now ? 'now' : 'todo',
  }));
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
                next={tr(`ui.next.${kyc.decision}`, { date: live ? longDate(live, lang) : '' })}
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
