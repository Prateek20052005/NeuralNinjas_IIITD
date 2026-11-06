import { useEffect, useState } from 'react';
import { MessageCircle, Phone, Share2 } from 'lucide-react';
import { api } from '../api.js';
import { longDate } from '../i18n.js';
import { money, PRODUCT_ICONS } from '../lib/ui.js';
import AppHeader from '../components/AppHeader.jsx';
import Button from '../components/Button.jsx';
import Chip from '../components/Chip.jsx';
import ChipGroup from '../components/ChipGroup.jsx';
import Note from '../components/Note.jsx';
import PriceBar from '../components/PriceBar.jsx';
import PriceBreakdown from '../components/PriceBreakdown.jsx';
import ProductCard from '../components/ProductCard.jsx';
import ToggleRow from '../components/ToggleRow.jsx';
import PhoneVerifySheet from '../components/PhoneVerifySheet.jsx';
import SalesCallbackSheet from '../components/SalesCallbackSheet.jsx';
import TextField from '../components/TextField.jsx';

let catalogueCache = null;

export default function Plan({ state, update, tr, actions, toast }) {
  const { rec, items = {}, lang } = state;
  const quote = state.quote || rec.quote;
  const [catalogue, setCatalogue] = useState(catalogueCache);
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState([]);
  const [error, setError] = useState('');
  const [plan, setPlan] = useState(state.plan || null); // tiers and unit prices for the chosen contract
  const [who, setWho] = useState(null); // business name and city for the eyebrow
  // price talk happens in the chat (a discount only if the owner insists); this screen just shows the result
  const neg = state.neg || {};
  const [verifying, setVerifying] = useState(false); // mobile number + code, needed to accept
  const [partner, setPartner] = useState(state.partner || null); // referring partner, if any
  const [calling, setCalling] = useState(false); // "a specialist can plan this with you" call form
  const [spend, setSpend] = useState(''); // what the owner pays today, typed to compare (optional)

  useEffect(() => {
    if (!catalogueCache) api.catalogue().then((c) => setCatalogue((catalogueCache = c))).catch(() => {});
    api.plan(state.id).then(show).catch(() => {}); // plan choices are extra: the quote works without them
    api.status(state.id).then((s) => { setWho(s.profile); setPartner(s.partner); }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function show(out) {
    setPlan(out);
    update({ quote: out.quote, items: out.items, plan: out });
  }

  async function run(fn) {
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(e.message || tr(e.status === 0 ? 'ui.offline' : 'ui.error'));
    } finally {
      setBusy(false);
    }
  }

  const choose = (choice) => run(async () => {
    setNotes([]);
    show(await api.plan(state.id, choice));
  });

  const toggle = (pid, on) => run(async () => {
    const out = await api.switchProduct(state.id, pid, on);
    setNotes(out.notes || []);
    if (out.tiers) show(out);
    else update({ quote: out.quote, items: out.items });
  });

  // accepting needs a verified mobile number (order updates, installation visit): ask for it first if missing
  const accept = () => {
    if (!state.phoneVerified) return setVerifying(true);
    return run(async () => {
      try {
        await api.accept(state.id);
        update({ accepted: true, screen: 'consent' });
      } catch (e) {
        if (e.status === 409 && !state.phoneVerified) setVerifying(true);
        else throw e;
      }
    });
  };

  async function phoneVerified(code, marketing) {
    const out = await api.phoneVerify(state.id, code, marketing);
    update({ phoneVerified: true, phoneSaved: out.phone });
    setVerifying(false);
    await api.accept(state.id);
    update({ accepted: true, screen: 'consent' });
  }

  async function share() {
    const text = tr('ui.share_text', {
      items: quote.lines.map((l) => (l.quantity > 1 ? `${l.name} ×${l.quantity}` : l.name)).join(', '),
      total: money(quote.monthly_with_gst).slice(1), setup: money(quote.setup_total).slice(1), months: quote.contract_months,
    });
    try {
      if (navigator.share) {
        await navigator.share({ title: tr('ui.your_plan'), text });
        return;
      }
      await navigator.clipboard.writeText(text);
      toast(tr('ui.copied'));
    } catch (e) {
      if (e?.name !== 'AbortError') window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, '_blank', 'noopener');
    }
  }

  const compare = () => run(async () => {
    show(await api.plan(state.id, { current_spend: Number(spend.replace(/\D/g, '')) || 0 }));
  });

  // the plan against what the owner pays today: same within 5%, otherwise the difference
  function spendLine() {
    const now = plan?.current_spend;
    if (!now) return null;
    const diff = quote.monthly_with_gst - now;
    const n = quote.lines.length;
    if (Math.abs(diff) <= now * 0.05) return tr('ui.spend_same', { n });
    return tr(diff > 0 ? 'ui.spend_more' : 'ui.spend_less', { diff: money(Math.abs(diff)).slice(1), n });
  }

  const name = (pid) => catalogue?.[pid]?.name || quote.lines.find((l) => l.product_id === pid)?.name || pid;
  const unit = (pid) => plan?.unit_prices?.[pid] ?? catalogue?.[pid]?.price ?? 0;
  // in the plan: suggested products that are switched on; extras: every add-on, plus suggestions switched off
  const included = rec.core.filter((p) => p.id in items);
  const extras = [...rec.addons, ...rec.core.filter((p) => !(p.id in items))];
  const contracts = quote.contract_options || [];
  const dearest = contracts.length ? Math.max(...contracts.map((c) => c.monthly_with_gst)) : 0;
  const spreads = [1, 6, 12].filter((m) => m <= quote.contract_months);
  const welcome = quote.welcome; // first-time customers only
  const setupDue = quote.setup_due ?? quote.setup_total;
  const billing = quote.billing_options || [];
  const live = longDate(quote.expected_live, lang);

  const rows = [
    ...quote.lines.map((l) => ({
      label: l.quantity > 1 ? `${l.name} × ${l.quantity}` : l.name,
      note: tr('ui.price_line', { price: money(l.unit_price).slice(1), qty: l.quantity,
                                  min: money(l.price_range[0]).slice(1), max: money(l.price_range[1]).slice(1) }),
      value: money(l.monthly),
    })),
    ...(quote.discount > 0 ? [{ label: `${tr('ui.discount')} ${quote.discount_pct}%`, value: `−${money(quote.discount)}`, kind: 'save' }] : []),
    { label: tr('ui.monthly_price'), value: money(quote.monthly_total), kind: 'sub' },
    { label: tr('ui.gst18'), value: money(quote.monthly_gst) },
    { label: tr('ui.you_pay'), value: money(quote.monthly_with_gst), kind: 'total' },
    ...(welcome?.months_pct > 0 ? [{ label: tr('ui.first_months_price', { n: welcome.period_months }),
                     value: money(welcome.per_month_with_gst), kind: 'save',
                     note: tr('ui.welcome_title') }] : []),
    { label: tr('ui.setup_once'), value: money(quote.setup_total), kind: 'sub',
      note: quote.setup_months > 1 ? tr('ui.setup_line', { amount: money(quote.setup_monthly).slice(1), n: quote.setup_months }) : '' },
    ...(quote.setup_discount > 0 ? [{ label: tr('ui.setup_discount'), value: `−${money(quote.setup_discount)}`, kind: 'save' }] : []),
    { label: tr('ui.contract_title'), value: tr('ui.months', { n: quote.contract_months }) },
  ];

  return (
    <div className="app-shell" lang={lang}>
      <AppHeader
        title={tr('ui.your_plan')}
        onBack={() => update({ screen: 'chat' })}
        backLabel={tr('ui.back')}
        actions={
          <>
            <button type="button" className="ab-icon-btn" style={{ color: 'var(--color-brand-ink)' }}
                    aria-label={tr('ui.share')} title={tr('ui.share')} onClick={share}>
              <Share2 size={21} strokeWidth={1.75} aria-hidden="true" />
            </button>
            {actions}
          </>
        }
      />
      <main className="page screen-in">
        <section className="stack">
          {who && (who.business_name || who.city) && (
            <p className="eyebrow">{[who.business_name, who.city].filter(Boolean).join(' · ')}</p>
          )}
          <h1 className="t-large-title" style={{ fontSize: '1.875rem' }}>{rec.headline?.replace(/[:：]\s*$/, '')}</h1>
          {rec.summary && <p className="lead">{rec.summary}</p>}
        </section>

        {partner && (
          <Note tone="trust">{tr(partner.assisted ? 'ui.assisted_by' : 'ui.referred_by', { partner: partner.name })}</Note>
        )}

        {plan?.handoff?.length > 0 && (
          <Note tone="info" title={tr('ui.handoff_title')}>
            {plan.handoff.map((r) => <span key={r} className="welcome-line">{tr(`ui.handoff.${r}`)}</span>)}
            <span className="welcome-line">{tr('ui.handoff_body')}</span>
            {!plan.callback_requested && (
              <span className="note-action">
                <Button variant="secondary" size="sm" icon={Phone} onClick={() => setCalling(true)} disabled={busy}>
                  {tr('ui.call_me_btn')}
                </Button>
              </span>
            )}
          </Note>
        )}

        {welcome && (
          <Note tone="ok" title={tr('ui.welcome_title')}>
            {quote.setup_discount > 0 && (
              <span className="welcome-line">
                {welcome.setup_off_pct >= 100
                  ? tr('ui.welcome_setup_free', { amount: money(quote.setup_discount).slice(1) })
                  : tr('ui.welcome_setup_off', { pct: welcome.setup_off_pct, amount: money(quote.setup_discount).slice(1) })}
              </span>
            )}
            {welcome.months_pct > 0 && <span className="welcome-line">
              {quote.billing_months <= 3
                ? tr('ui.welcome_months', { pct: welcome.months_pct, n: welcome.period_months,
                                            total: money(welcome.per_month_with_gst).slice(1) })
                : tr('ui.welcome_first_bill', { pct: welcome.months_pct, n: quote.billing_months,
                                                total: money(welcome.first_bill_with_gst).slice(1) })}
            </span>}
            <span className="welcome-line">
              {tr('ui.welcome_saving', { amount: money(quote.setup_discount + welcome.saving_with_gst).slice(1) })}
            </span>
          </Note>
        )}

        {plan?.tiers?.length > 1 && (
          <section className="stack" aria-labelledby="tiers-title">
            <h2 id="tiers-title" className="section-label">{tr('ui.choose_plan')}</h2>
            <div className="tiers" role="radiogroup" aria-labelledby="tiers-title">
              {plan.tiers.map((tier) => (
                <button key={tier.id} type="button" role="radio" aria-checked={plan.tier === tier.id} disabled={busy}
                        className="tier" onClick={() => choose({ tier: tier.id })}>
                  <span className="tier__radio" aria-hidden="true" />
                  <span className="tier__text">
                    <strong>{tr(`ui.tier.${tier.id}`)}</strong>
                    <span className="tier__hint">{tr(`ui.tier.${tier.id}.hint`)} · {tr('ui.tier_products', { n: tier.count })}</span>
                  </span>
                  <span className="tier__price">{money(tier.monthly_with_gst)}<small>{tr('ui.per_month_gst')}</small></span>
                </button>
              ))}
            </div>
            {plan.tier === 'custom' && <p className="choice-hint">{tr('ui.tier.custom')}</p>}
          </section>
        )}

        {included.length > 0 && (
          <section className="stack" aria-labelledby="in-plan">
            <h2 id="in-plan" className="section-label">{tr('ui.included')}</h2>
            {rec.similar ? <p className="choice-hint">{tr('ui.based_on_similar', { n: rec.similar })}</p> : null}
            <div className="inset-group">
              {included.map((p) => (
                <ProductCard key={p.id} icon={PRODUCT_ICONS[p.id]} name={name(p.id)} reason={p.reason}
                             quantity={items[p.id] || p.quantity} monthly={unit(p.id) * (items[p.id] || p.quantity)}
                             perLabel={tr('ui.per_month')} />
              ))}
            </div>
          </section>
        )}

        {extras.length > 0 && (
          <section className="stack" aria-labelledby="extras">
            <h2 id="extras" className="section-label">{tr('ui.extras')}</h2>
            <div className="inset-group">
              {extras.map((p) => (
                <ToggleRow key={p.id} icon={PRODUCT_ICONS[p.id]} name={name(p.id)} reason={p.reason} quantity={p.quantity}
                           proof={p.popular ? (p.popular.with
                             ? tr('ui.popular_with', { pct: p.popular.pct, product: p.popular.with })
                             : tr('ui.popular', { pct: p.popular.pct })) : null}
                           monthly={unit(p.id) * p.quantity} checked={p.id in items}
                           onChange={(on) => !busy && toggle(p.id, on)} />
              ))}
            </div>
          </section>
        )}

        {[...rec.notes, ...notes].map((n, i) => <Note key={i}>{n}</Note>)}
        {error && <div role="alert"><Note tone="warn">{error}</Note></div>}

        {contracts.length > 1 && (
          <section className="stack" aria-labelledby="contract-title">
            <h2 id="contract-title" className="section-label">{tr('ui.contract_title')}</h2>
            <ChipGroup label={tr('ui.contract_title')}>
              {contracts.map((c) => (
                <Chip key={c.months} selected={quote.contract_months === c.months} disabled={busy}
                      onClick={() => choose({ contract_months: c.months })}>
                  {c.months === 1 ? tr('ui.month_to_month') : tr('ui.months', { n: c.months })} · {money(c.monthly_with_gst)}
                </Chip>
              ))}
            </ChipGroup>
            {contracts.some((c) => c.monthly_with_gst < dearest) && (
              <p className="choice-hint">
                {contracts.filter((c) => c.monthly_with_gst < dearest).map((c) => (
                  <span key={c.months} className="save-tag">
                    {tr('ui.months', { n: c.months })}: {tr('ui.saves', { amount: money(dearest - c.monthly_with_gst).slice(1) })}{' '}
                  </span>
                ))}
                <br />
                {tr('ui.pricing_rule')}
              </p>
            )}
          </section>
        )}

        {setupDue > 0 && spreads.length > 1 && (
          <section className="stack" aria-labelledby="setup-title">
            <h2 id="setup-title" className="section-label">{tr('ui.setup_title', { amount: money(setupDue).slice(1) })}</h2>
            <ChipGroup label={tr('ui.setup_title', { amount: money(setupDue).slice(1) })}>
              {spreads.map((m) => (
                <Chip key={m} selected={quote.setup_months === m} disabled={busy} onClick={() => choose({ setup_months: m })}>
                  {m === 1 ? tr('ui.setup_now') : tr('ui.setup_spread', { amount: money(Math.ceil(setupDue / m)).slice(1), n: m })}
                </Chip>
              ))}
            </ChipGroup>
          </section>
        )}

        {billing.length > 1 && (
          <section className="stack" aria-labelledby="billing-title">
            <h2 id="billing-title" className="section-label">{tr('ui.billing_title')}</h2>
            <ChipGroup label={tr('ui.billing_title')}>
              {billing.map((o) => (
                <Chip key={o.months} selected={quote.billing_months === o.months} disabled={busy}
                      onClick={() => choose({ billing_months: o.months })}>
                  {o.months === 1 ? tr('ui.billing_monthly') : tr('ui.billing_every', { n: o.months })}
                  {o.saving_pct > 0 ? ` · ${tr('ui.billing_save', { pct: o.saving_pct })}` : ''}
                </Chip>
              ))}
            </ChipGroup>
            {quote.billing_months > 1 && (
              <p className="choice-hint">{tr('ui.billing_bill', { total: money(quote.bill_with_gst).slice(1), n: quote.billing_months })}</p>
            )}
          </section>
        )}

        <section className="stack" aria-labelledby="spend-title">
          <h2 id="spend-title" className="section-label">{tr('ui.spend_title')}</h2>
          <form className="spend-row" onSubmit={(e) => { e.preventDefault(); compare(); }}>
            <TextField label={tr('ui.spend_label')} inputMode="numeric" placeholder="₹"
                       value={spend || (plan?.current_spend ? String(plan.current_spend) : '')}
                       onChange={(e) => setSpend(e.target.value)} />
            <Button type="submit" variant="secondary" size="sm" disabled={busy || !spend.replace(/\D/g, '')}>
              {tr('ui.spend_compare')}
            </Button>
          </form>
          {spendLine() ? <Note>{spendLine()}</Note> : <p className="choice-hint">{tr('ui.spend_hint')}</p>}
        </section>

        <PriceBreakdown title={tr('ui.price_how')} rows={rows} footnote={tr('ui.price_explain')} />

        {neg.status !== 'called' && (
          <Button variant="secondary" block icon={MessageCircle} onClick={() => update({ screen: 'chat' })} disabled={busy}>
            {tr('ui.chat_about_price')}
          </Button>
        )}
      </main>

      <PriceBar
        total={money(quote.monthly_total)}
        perMonth={tr('ui.per_month')}
        gstLine={tr('ui.plus_gst', { gst: money(quote.monthly_gst).slice(1), total: money(quote.monthly_with_gst).slice(1) })}
        extra={quote.discount > 0 ? tr('ui.discount_line', { pct: quote.discount_pct, amount: money(quote.discount).slice(1) }) : null}
        meta={[
          quote.setup_months > 1
            ? tr('ui.setup_line', { amount: money(quote.setup_monthly).slice(1), n: quote.setup_months })
            : `${tr('ui.setup_once')}: ${money(setupDue)}`,
          tr('ui.contract', { n: quote.contract_months }),
          ...(quote.billing_months > 1
            ? [tr('ui.billing_bill', { total: money(quote.bill_with_gst).slice(1), n: quote.billing_months })] : []),
          tr('ui.live_by', { date: live }),
        ]}
        actionLabel={tr('ui.accept')}
        onAction={accept}
        disabled={busy}
      />

      <SalesCallbackSheet open={calling} onClose={() => setCalling(false)} id={state.id} tr={tr}
                          reason={plan?.handoff?.[0] || 'leased_line'}
                          verifiedPhone={state.phoneVerified ? state.phoneSaved : null}
                          onDone={(message) => {
                            setCalling(false);
                            setPlan((p) => ({ ...p, callback_requested: true }));
                            toast(message);
                          }} />
      <PhoneVerifySheet open={verifying} onClose={() => setVerifying(false)} tr={tr} why={tr('ui.phone_why_order')}
                        withMarketing verifyLabel={tr('ui.accept')}
                        send={(phone) => api.phoneSend(state.id, phone)} verify={phoneVerified} />
    </div>
  );
}
