import { useEffect, useState } from 'react';
import { BadgePercent, Phone, Share2 } from 'lucide-react';
import { api } from '../api.js';
import { longDate } from '../i18n.js';
import { money, PRODUCT_ICONS } from '../lib/ui.js';
import AppHeader from '../components/AppHeader.jsx';
import BottomSheet from '../components/BottomSheet.jsx';
import Button from '../components/Button.jsx';
import Checkbox from '../components/Checkbox.jsx';
import Chip from '../components/Chip.jsx';
import ChipGroup from '../components/ChipGroup.jsx';
import Note from '../components/Note.jsx';
import PriceBar from '../components/PriceBar.jsx';
import PriceBreakdown from '../components/PriceBreakdown.jsx';
import ProductCard from '../components/ProductCard.jsx';
import TextField from '../components/TextField.jsx';
import ToggleRow from '../components/ToggleRow.jsx';

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
  // price negotiation: offers come from the server's rules; after the last one, a salesperson can call
  const neg = state.neg || {};
  const [sheet, setSheet] = useState(false);
  const [phone, setPhone] = useState('');
  const [target, setTarget] = useState('');
  const [callOk, setCallOk] = useState(false);

  useEffect(() => {
    if (!catalogueCache) api.catalogue().then((c) => setCatalogue((catalogueCache = c))).catch(() => {});
    api.plan(state.id).then(show).catch(() => {}); // plan choices are extra: the quote works without them
    api.status(state.id).then((s) => setWho(s.profile)).catch(() => {});
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

  const askPrice = () => run(async () => {
    const out = await api.priceRequest(state.id);
    show(out);
    update({ neg: { ...neg, status: out.status, message: out.message } });
    if (out.status === 'handoff') setSheet(true);
  });

  const requestCall = () => run(async () => {
    const out = await api.salesCallback(state.id, { phone, consent: callOk,
                                                    target_monthly: Number(target.replace(/\D/g, '')) || null });
    update({ neg: { ...neg, status: 'called', message: out.message } });
    setSheet(false);
  });

  const accept = () => run(async () => {
    await api.accept(state.id);
    update({ accepted: true, screen: 'consent' });
  });

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

  const name = (pid) => catalogue?.[pid]?.name || quote.lines.find((l) => l.product_id === pid)?.name || pid;
  const unit = (pid) => plan?.unit_prices?.[pid] ?? catalogue?.[pid]?.price ?? 0;
  // in the plan: suggested products that are switched on; extras: every add-on, plus suggestions switched off
  const included = rec.core.filter((p) => p.id in items);
  const extras = [...rec.addons, ...rec.core.filter((p) => !(p.id in items))];
  const contracts = quote.contract_options || [];
  const dearest = contracts.length ? Math.max(...contracts.map((c) => c.monthly_with_gst)) : 0;
  const spreads = [1, 6, 12].filter((m) => m <= quote.contract_months);
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
    { label: tr('ui.setup_once'), value: money(quote.setup_total), kind: 'sub',
      note: quote.setup_months > 1 ? tr('ui.setup_line', { amount: money(quote.setup_monthly).slice(1), n: quote.setup_months }) : '' },
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

        {quote.setup_total > 0 && spreads.length > 1 && (
          <section className="stack" aria-labelledby="setup-title">
            <h2 id="setup-title" className="section-label">{tr('ui.setup_title', { amount: money(quote.setup_total).slice(1) })}</h2>
            <ChipGroup label={tr('ui.setup_title', { amount: money(quote.setup_total).slice(1) })}>
              {spreads.map((m) => (
                <Chip key={m} selected={quote.setup_months === m} disabled={busy} onClick={() => choose({ setup_months: m })}>
                  {m === 1 ? tr('ui.setup_now') : tr('ui.setup_spread', { amount: money(Math.ceil(quote.setup_total / m)).slice(1), n: m })}
                </Chip>
              ))}
            </ChipGroup>
          </section>
        )}

        <PriceBreakdown title={tr('ui.price_how')} rows={rows} footnote={tr('ui.price_explain')} />

        <section className="stack" aria-live="polite">
          {neg.message && <Note tone={neg.status === 'called' ? 'ok' : 'info'}>{neg.message}</Note>}
          {neg.status === 'handoff' && (
            <Button variant="secondary" block icon={Phone} onClick={() => setSheet(true)}>{tr('ui.request_call')}</Button>
          )}
          {!['handoff', 'called'].includes(neg.status) && (
            <Button variant="secondary" block icon={BadgePercent} onClick={askPrice} disabled={busy}>
              {tr(neg.status === 'offer' ? 'ui.ask_better' : neg.status === 'final' ? 'ui.ask_sales' : 'ui.ask_lower')}
            </Button>
          )}
        </section>
      </main>

      <PriceBar
        total={money(quote.monthly_total)}
        perMonth={tr('ui.per_month')}
        gstLine={tr('ui.plus_gst', { gst: money(quote.monthly_gst).slice(1), total: money(quote.monthly_with_gst).slice(1) })}
        extra={quote.discount > 0 ? tr('ui.discount_line', { pct: quote.discount_pct, amount: money(quote.discount).slice(1) }) : null}
        meta={[
          quote.setup_months > 1
            ? tr('ui.setup_line', { amount: money(quote.setup_monthly).slice(1), n: quote.setup_months })
            : `${tr('ui.setup_once')}: ${money(quote.setup_total)}`,
          tr('ui.contract', { n: quote.contract_months }),
          tr('ui.live_by', { date: live }),
        ]}
        actionLabel={tr('ui.accept')}
        onAction={accept}
        disabled={busy}
      />

      <BottomSheet open={sheet} onClose={() => setSheet(false)} title={tr('ui.ask_sales')} closeLabel={tr('ui.cancel')}>
        <TextField label={tr('ui.phone_label')} type="tel" inputMode="tel" autoComplete="tel" placeholder="98765 43210"
                   value={phone} onChange={(e) => setPhone(e.target.value)} />
        <TextField label={tr('ui.target_label')} inputMode="numeric" placeholder="₹" value={target}
                   onChange={(e) => setTarget(e.target.value)} />
        <div className="inset-group">
          <Checkbox checked={callOk} onChange={setCallOk} label={tr('ui.callback_consent')} />
        </div>
        {error && <Note tone="warn">{error}</Note>}
        <Button block icon={Phone} onClick={requestCall} disabled={busy || !callOk || phone.replace(/\D/g, '').length < 10}>
          {tr('ui.request_call')}
        </Button>
      </BottomSheet>
    </div>
  );
}
