import { useEffect, useState } from "react";
import { api } from "../api.js";
import { longDate, rupees } from "../i18n.js";

let catalogueCache = null;

function ProductRow({ pick, on, product, busy, onToggle }) {
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
        {product && <div className="price">₹{rupees(product.price * pick.quantity)}</div>}
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

  useEffect(() => {
    if (!catalogueCache) api.catalogue().then((c) => setCatalogue((catalogueCache = c))).catch(() => {});
  }, []);

  async function toggle(pid, on) {
    setBusy(true);
    setError("");
    try {
      const out = await api.switchProduct(state.id, pid, on);
      setNotes(out.notes);
      update({ quote: out.quote, items: out.items });
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
                busy={busy} onToggle={toggle} />
  );

  return (
    <main className="page plan">
      <h1>{tr("ui.your_plan")}</h1>
      <p className="lead">{rec.headline}</p>
      {rec.summary && <p>{rec.summary}</p>}

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

      <section className="price-box" aria-live="polite">
        <div className="total">
          <span className="amount">₹{rupees(quote.monthly_total)}</span>
          <span className="muted"> {tr("ui.per_month")}</span>
        </div>
        <div className="muted small">
          {tr("ui.plus_gst", { gst: rupees(quote.monthly_gst), total: rupees(quote.monthly_with_gst) })}
        </div>
        <div className="facts">
          <span>{tr("ui.setup_once")}: ₹{rupees(quote.setup_total)}</span>
          <span>{tr("ui.contract", { n: quote.contract_months })}</span>
          <span>{tr("ui.live_by", { date: longDate(quote.expected_live, lang) })}</span>
        </div>
        <button className="primary" onClick={accept} disabled={busy}>{tr("ui.accept")}</button>
      </section>
    </main>
  );
}
