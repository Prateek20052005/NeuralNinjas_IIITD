import { useEffect, useState } from "react";
import { api } from "../api.js";
import { longDate } from "../i18n.js";

const DECISION_STYLE = { PASS: "ok", REVIEW: "warn", INCOMPLETE: "bad", RETAKE: "bad", REJECT: "bad" };

function steps(status, tr, lang) {
  const done = new Set(status.timeline.map((s) => s.step));
  const decision = status.kyc?.decision;
  const live = status.quote?.expected_live;
  return [
    { label: tr("ui.step.quote_accepted"), state: done.has("quote_accepted") ? "done" : "todo" },
    { label: tr("ui.step.consent_given"), state: done.has("consent_given") ? "done" : "todo" },
    { label: tr("ui.step.documents"), state: done.has("document_read") ? "done" : "todo" },
    {
      label: tr("ui.step.kyc"),
      state: decision === "PASS" ? "done" : decision === "REVIEW" ? "warn" : decision ? "bad" : "todo",
      note: decision === "REVIEW" ? tr("ui.step.review") : decision && decision !== "PASS" ? status.kyc.headline : "",
    },
    {
      label: tr("ui.step.installation"),
      state: done.has("installation_booked") ? "current" : "todo",
      note: done.has("installation_booked") && live ? tr("ui.step.installation_on", { date: longDate(live, lang) }) : "",
    },
  ];
}

export default function Tracker({ state, update, tr, onErased }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.status(state.id).then(setStatus).catch((e) => setError(e.status === 404 ? "" : tr("ui.offline")));
  }, [state.id, state.kyc]); // eslint-disable-line react-hooks/exhaustive-deps

  async function erase() {
    if (!window.confirm(tr("ui.delete_confirm"))) return;
    try {
      const out = await api.erase(state.id);
      onErased(out.message);
    } catch {
      setError(tr("ui.error"));
    }
  }

  if (!status) return <main className="page">{error && <p className="notice bad">{error}</p>}</main>;

  const kyc = status.kyc;
  const next = !status.consent ? "consent" : !kyc || kyc.decision !== "PASS" ? "documents" : null;
  return (
    <main className="page tracker">
      <h1>{tr("ui.tracker_title")}</h1>

      {kyc && (
        <section className={`result ${DECISION_STYLE[kyc.decision]}`}>
          <p className="lead">{kyc.headline}</p>
          {kyc.issues.length > 0 && (
            <ul>
              {kyc.issues.map((i, n) => <li key={n}>{i.message}</li>)}
            </ul>
          )}
          {["RETAKE", "INCOMPLETE", "REJECT"].includes(kyc.decision) && (
            <p className="muted small">{tr("ui.fix_and_resubmit")}</p>
          )}
        </section>
      )}

      <ol className="steps">
        {steps(status, tr, state.lang).map((s, i) => (
          <li key={i} className={s.state}>
            <span className="dot" aria-hidden="true">{{ done: "✓", warn: "!", bad: "!", current: "●" }[s.state] || i + 1}</span>
            <div>
              <div>{s.label}</div>
              {s.note && <div className="muted small">{s.note}</div>}
            </div>
          </li>
        ))}
      </ol>

      {next && (
        <button className="primary" onClick={() => update({ screen: next })}>
          {next === "consent" ? tr("ui.consent_continue") : tr("ui.documents_title")}
        </button>
      )}
      {error && <p className="notice bad">{error}</p>}
      <button className="danger-link" onClick={erase}>{tr("ui.delete_data")}</button>
    </main>
  );
}
