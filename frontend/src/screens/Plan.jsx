import { useEffect, useState } from "react";
import { api } from "../api.js";
import { longDate, rupees } from "../i18n.js";

let catalogueCache = null;

function ProductRow({ pick, on, product, price, busy, onToggle }) {
  return (
    <li className={`product ${on ? "on" : ""}`}>
      <div className="product-text">
        <div className="product-name">
          {product?.name || pick.id}
          {pick.quantity > 1 && <span className="qty"> × {pick.quantity}</span>}
        </div>
        <div className="reason">{pick.reason}</div>
      </div>
      <div className="product-side">
        {(price ?? product?.price) != null && <div className="price">₹{rupees((price ?? product.price) * pick.quantity)}</div>}
        <label className="switch">
          <input type="checkbox" checked={on} disabled={busy} onChange={(e) => onToggle(pick.id, e.target.checked)}
                 aria-label={product?.name || pick.id} />
          <span />
        </label>
      </div>
    </li>
  );
}

export default function Plan({ state, update, tr }) {
  const { rec, items = {}, lang } = state;
  const quote = state.quote || rec.quote;
  const [catalogue, setCatalogue] = useState(catalogueCache);
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState([]);
  const [error, setError] = useState("");
  const [plan, setPlan] = useState(state.plan || null);   // tiers, prices for the chosen contract
  // price negotiation: offers come from the server's rules; after the last one, a salesperson can call
  const neg = state.neg || {};
  const [phone, setPhone] = useState("");
  const [target, setTarget] = useState("");
  const [callOk, setCallOk] = useState(false);

  useEffect(() => {
    if (!catalogueCache) api.catalogue().then((c) => setCatalogue((catalogueCache = c))).catch(() => {});
    api.plan(state.id).then(show).catch(() => {});   // plan choices are extra: the quote works without them
  }, []);

  function show(out) {
    setPlan(out);
    update({ quote: out.quote, items: out.items, plan: out });
  }

  async function choose(choice) {
    setBusy(true);
    setError("");
    setNotes([]);
    try {
      show(await api.plan(state.id, choice));
    } catch (e) {
      setError(e.message || tr("ui.error"));
    } finally {
      setBusy(false);
    }
  }

  async function toggle(pid, on) {
    setBusy(true);
    setError("");
    try {
      const out = await api.switchProduct(state.id, pid, on);
      setNotes(out.notes);
      if (out.tiers) show(out);
      else update({ quote: out.quote, items: out.items });
    } catch (e) {
      setError(e.message || tr("ui.error"));
    } finally {
      setBusy(false);
    }
  }

  async function askPrice() {
    setBusy(true);
    setError("");
    try {
      const out = await api.priceRequest(state.id);
      show(out);
      update({ neg: { ...neg, status: out.status, message: out.message } });
    } catch (e) {
      setError(e.message || tr("ui.error"));
    } finally {
      setBusy(false);
    }
  }

  async function requestCall() {
    setBusy(true);
    setError("");
    try {
      const out = await api.salesCallback(state.id, { phone, consent: callOk,
                                                      target_monthly: Number(target.replace(/\D/g, "")) || null });
      update({ neg: { ...neg, status: "called", message: out.message } });
    } catch (e) {
      setError(e.message || tr("ui.error"));
    } finally {
      setBusy(false);
    }
  }

  async function accept() {
    setBusy(true);
    try {
      await api.accept(state.id);
      update({ accepted: true, screen: "consent" });
    } catch (e) {
      setError(e.message || tr("ui.error"));
      setBusy(false);
    }
  }

  const row = (pick) => (
    <ProductRow key={pick.id} pick={pick} on={pick.id in items} product={catalogue?.[pick.id]}
                price={plan?.unit_prices?.[pick.id]} busy={busy} onToggle={toggle} />
  );
  const contracts = quote.contract_options || [];
  const longest = contracts.length ? contracts[0].monthly_with_gst : 0;   // shortest contract costs the most
  const spreads = [1, 6, 12].filter((m) => m <= quote.contract_months);

  return (
    <main className="page plan">
      <h1>{tr("ui.your_plan")}</h1>
      <p className="lead">{rec.headline}</p>
      {rec.summary && <p>{rec.summary}</p>}

      {plan?.tiers?.length > 1 && (
        <>
          <h2>{tr("ui.choose_plan")}</h2>
          <div className="tiers" role="radiogroup" aria-label={tr("ui.choose_plan")}>
            {plan.tiers.map((tier) => (
              <button key={tier.id} role="radio" aria-checked={plan.tier === tier.id} disabled={busy}
                      className={`tier ${plan.tier === tier.id ? "on" : ""}`} onClick={() => choose({ tier: tier.id })}>
                <strong>{tr(`ui.tier.${tier.id}`)}</strong>
                <span className="muted small">{tr(`ui.tier.${tier.id}.hint`)} · {tr("ui.tier_products", { n: tier.count })}</span>
                <span className="tier-price">₹{rupees(tier.monthly_with_gst)}<span className="muted small"> {tr("ui.per_month_gst")}</span></span>
              </button>
            ))}
          </div>
          {plan.tier === "custom" && <p className="muted small">{tr("ui.tier.custom")}</p>}
        </>
      )}

      <h2>{tr("ui.included")}</h2>
      <ul className="products">{rec.core.map(row)}</ul>

      {rec.addons.length > 0 && (
        <>
          <h2>{tr("ui.extras")}</h2>
          <ul className="products">{rec.addons.map(row)}</ul>
        </>
      )}

      {[...rec.notes, ...notes].map((n, i) => <p key={i} className="notice info">{n}</p>)}
      {error && <p className="notice bad" role="alert">{error}</p>}

      <details className="details">
        <summary>{tr("ui.price_details")}</summary>
        <ul>
          {quote.lines.map((l) => (
            <li key={l.product_id}>
              <span>{l.name}</span>
              <span>{tr("ui.price_line", { price: rupees(l.unit_price), qty: l.quantity,
                                           min: rupees(l.price_range[0]), max: rupees(l.price_range[1]) })}</span>
            </li>
          ))}
        </ul>
        <p className="muted">{tr("ui.price_explain")}</p>
      </details>

      {contracts.length > 1 && (
        <section className="choice">
          <h2>{tr("ui.contract_title")}</h2>
          <div className="options" role="radiogroup" aria-label={tr("ui.contract_title")}>
            {contracts.map((c) => (
              <button key={c.months} role="radio" aria-checked={quote.contract_months === c.months} disabled={busy}
                      className={`chip ${quote.contract_months === c.months ? "on" : ""}`}
                      onClick={() => choose({ contract_months: c.months })}>
                {c.months === 1 ? tr("ui.month_to_month") : tr("ui.months", { n: c.months })}
                {" · ₹"}{rupees(c.monthly_with_gst)}
                {c.monthly_with_gst < longest && <span className="save"> · {tr("ui.saves", { amount: rupees(longest - c.monthly_with_gst) })}</span>}
              </button>
            ))}
          </div>
          <p className="muted small">{tr("ui.pricing_rule")}</p>
        </section>
      )}

      {quote.setup_total > 0 && spreads.length > 1 && (
        <section className="choice">
          <h2>{tr("ui.setup_title", { amount: rupees(quote.setup_total) })}</h2>
          <div className="options" role="radiogroup" aria-label={tr("ui.setup_title", { amount: rupees(quote.setup_total) })}>
            {spreads.map((m) => (
              <button key={m} role="radio" aria-checked={quote.setup_months === m} disabled={busy}
                      className={`chip ${quote.setup_months === m ? "on" : ""}`} onClick={() => choose({ setup_months: m })}>
                {m === 1 ? tr("ui.setup_now") : tr("ui.setup_spread", { amount: rupees(Math.ceil(quote.setup_total / m)), n: m })}
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="choice negotiate" aria-live="polite">
        {neg.message && <p className={`notice ${neg.status === "called" ? "ok" : "info"}`}>{neg.message}</p>}
        {neg.status === "handoff" ? (
          <div className="callback">
            <label htmlFor="phone">{tr("ui.phone_label")}</label>
            <input id="phone" type="tel" inputMode="tel" autoComplete="tel" value={phone}
                   placeholder="98765 43210" onChange={(e) => setPhone(e.target.value)} />
            <label htmlFor="target">{tr("ui.target_label")}</label>
            <input id="target" inputMode="numeric" value={target} placeholder="₹"
                   onChange={(e) => setTarget(e.target.value)} />
            <label className="check">
              <input type="checkbox" checked={callOk} onChange={(e) => setCallOk(e.target.checked)} />
              <span>{tr("ui.callback_consent")}</span>
            </label>
            <button className="secondary" onClick={requestCall}
                    disabled={busy || !callOk || phone.replace(/\D/g, "").length < 10}>
              {tr("ui.request_call")}
            </button>
          </div>
        ) : neg.status !== "called" && (
          <button className="secondary" onClick={askPrice} disabled={busy}>
            {tr(neg.status === "offer" ? "ui.ask_better" : neg.status === "final" ? "ui.ask_sales" : "ui.ask_lower")}
          </button>
        )}
      </section>

      <section className="price-box" aria-live="polite">
        <div className="total">
          <span className="amount">₹{rupees(quote.monthly_total)}</span>
          <span className="muted"> {tr("ui.per_month")}</span>
        </div>
        {quote.discount > 0 && (
          <div className="small save-line">{tr("ui.discount_line", { pct: quote.discount_pct, amount: rupees(quote.discount) })}</div>
        )}
        <div className="muted small">
          {tr("ui.plus_gst", { gst: rupees(quote.monthly_gst), total: rupees(quote.monthly_with_gst) })}
        </div>
        <div className="facts">
          <span>
            {quote.setup_months > 1
              ? tr("ui.setup_line", { amount: rupees(quote.setup_monthly), n: quote.setup_months })
              : `${tr("ui.setup_once")}: ₹${rupees(quote.setup_total)}`}
          </span>
          <span>{tr("ui.contract", { n: quote.contract_months })}</span>
          <span>{tr("ui.live_by", { date: longDate(quote.expected_live, lang) })}</span>
        </div>
        <button className="primary" onClick={accept} disabled={busy}>{tr("ui.accept")}</button>
      </section>
    </main>
  );
}
