import { useEffect, useState } from "react";
import { api } from "../api.js";

// DPDP Act: consent is asked before any document is read, per purpose, and nothing is pre-ticked.
export default function Consent({ state, update, tr }) {
  const [text, setText] = useState(null);
  const [chosen, setChosen] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.consentText(state.lang).then(setText).catch(() => setError(tr("ui.offline")));
  }, [state.lang]); // eslint-disable-line react-hooks/exhaustive-deps

  async function agree() {
    setBusy(true);
    try {
      await api.consent(state.id, Object.keys(chosen).filter((k) => chosen[k]));
      update({ consented: true, screen: "documents" });
    } catch (e) {
      setError(e.message || tr("ui.error"));
      setBusy(false);
    }
  }

  if (!text) return <main className="page">{error && <p className="notice bad">{error}</p>}</main>;
  const ready = text.purposes.every((p) => !p.required || chosen[p.id]);

  return (
    <main className="page consent">
      <h1>{text.title}</h1>
      <p>{text.body}</p>
      <div className="purposes">
        {text.purposes.map((p) => (
          <label key={p.id} className="check">
            <input type="checkbox" checked={!!chosen[p.id]}
                   onChange={(e) => setChosen({ ...chosen, [p.id]: e.target.checked })} />
            <span>{p.text}{p.required && <span className="required"> *</span>}</span>
          </label>
        ))}
      </div>
      {error && <p className="notice bad" role="alert">{error}</p>}
      <button className="primary" disabled={!ready || busy} onClick={agree}>{text.agree}</button>
    </main>
  );
}
