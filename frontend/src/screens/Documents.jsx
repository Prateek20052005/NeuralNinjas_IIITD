import { useEffect, useState } from "react";
import { api } from "../api.js";

const DOCS = ["gst_certificate", "udyam_certificate", "address_proof", "signatory_id"];
// two details per document, shown back so the owner can see we read it right (IDs arrive masked)
const PREVIEW = {
  gst_certificate: ["trade_name", "gstin"],
  udyam_certificate: ["enterprise_name", "udyam_number"],
  address_proof: ["billed_to", "bill_date"],
  signatory_id: ["name", "valid_till"],
};
const MAX_SIDE = 2000;

// Phone photos are often 4000 px and several MB; the server reads 2000 px just as well. Shrinking here
// makes uploads fast on slow mobile data. Falls back to the original file if the browser can't do it.
async function shrink(file) {
  try {
    const img = await createImageBitmap(file);
    const scale = MAX_SIDE / Math.max(img.width, img.height);
    if (scale >= 1) return file;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((ok) => canvas.toBlob(ok, "image/jpeg", 0.9));
    return blob ? new File([blob], "photo.jpg", { type: "image/jpeg" }) : file;
  } catch {
    return file;
  }
}

function DocCard({ type, doc, reading, onFile, tr, optional, children }) {
  const status = reading ? "reading" : doc ? (doc.ok ? "ok" : "bad") : "empty";
  return (
    <li className={`doc ${status}`}>
      <div className="doc-head">
        <span className="doc-icon" aria-hidden="true">{{ ok: "✓", bad: "!", reading: "…", empty: "" }[status]}</span>
        <strong>{tr(`doc.${type}`)}</strong>
        {optional && <span className="muted small"> · {tr("ui.optional")}</span>}
      </div>
      {reading && <p className="muted">{tr("ui.reading")}</p>}
      {doc && !reading && (
        <>
          <p className={doc.ok ? "muted" : "bad-text"}>{doc.message}</p>
          {doc.ok && (
            <p className="read-back">
              {PREVIEW[type].map((k) => doc.fields[k]).filter(Boolean).join(" · ")}
            </p>
          )}
        </>
      )}
      <label className={`upload ${doc ? "secondary" : "primary"}`}>
        <input type="file" accept="image/*" disabled={reading}
               onChange={(e) => e.target.files[0] && onFile(type, e.target.files[0], e)} />
        {doc ? tr("ui.retake") : tr("ui.take_photo")}
      </label>
      {children}
    </li>
  );
}

export default function Documents({ state, update, tr }) {
  const docs = state.docs || {};
  const [reading, setReading] = useState({});
  const [udyam, setUdyam] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  // Which documents this owner needs: without GST only address proof and ID (Udyam optional, no GST card)
  const [required, setRequired] = useState(null);
  useEffect(() => {
    api.status(state.id)
      .then((s) => setRequired(Object.fromEntries(Object.entries(s.documents).map(([k, v]) => [k, v.required]))))
      .catch(() => setRequired(null));   // unknown: show every document, as before
  }, [state.id]);
  const noGst = required && !required.gst_certificate;
  const shown = DOCS.filter((type) => !(noGst && type === "gst_certificate"));

  async function onFile(type, file, event) {
    setReading((r) => ({ ...r, [type]: true }));
    setError("");
    try {
      const out = await api.upload(state.id, type, await shrink(file));
      update({ docs: { ...(state.docs || {}), [type]: out } });
    } catch (e) {
      setError(e.message || tr(e.status === 0 ? "ui.offline" : "ui.error"));
    } finally {
      event.target.value = "";   // same file can be picked again
      setReading((r) => ({ ...r, [type]: false }));
    }
  }

  async function saveUdyam() {
    try {
      const out = await api.udyamNumber(state.id, udyam);
      update({ udyamSaved: out.udyam_number });
    } catch (e) {
      setError(e.message || tr("ui.error"));
    }
  }

  async function check() {
    setChecking(true);
    setError("");
    try {
      const kyc = await api.checkKyc(state.id);
      update({ kyc, screen: "tracker" });
    } catch (e) {
      setError(e.message || tr("ui.error"));
      setChecking(false);
    }
  }

  const anyReading = Object.values(reading).some(Boolean);
  return (
    <main className="page documents">
      <h1>{tr("ui.documents_title")}</h1>
      <p className="muted">{tr("ui.documents_hint")}</p>
      {noGst && <p className="notice info">{tr("ui.no_gst_docs")}</p>}
      <ul className="doc-list">
        {shown.map((type) => (
          <DocCard key={type} type={type} doc={docs[type]} reading={reading[type]} onFile={onFile} tr={tr}
                   optional={required ? !required[type] : false}>
            {type === "udyam_certificate" && !docs[type]?.ok && (
              <div className="udyam-number">
                <label htmlFor="udyam">{tr("ui.or_type_udyam")}</label>
                <div className="row">
                  <input id="udyam" value={udyam} placeholder="UDYAM-MH-00-1234567" autoCapitalize="characters"
                         onChange={(e) => setUdyam(e.target.value)} />
                  <button className="secondary" disabled={udyam.trim().length < 10} onClick={saveUdyam}>
                    {state.udyamSaved ? tr("ui.saved") : tr("ui.save")}
                  </button>
                </div>
              </div>
            )}
          </DocCard>
        ))}
      </ul>
      {error && <p className="notice bad" role="alert">{error}</p>}
      <p className="muted small">🔒 {tr("ui.privacy_line")}</p>
      <button className="primary" onClick={check}
              disabled={checking || anyReading || (Object.keys(docs).length === 0 && !state.udyamSaved)}>
        {checking ? tr("ui.checking") : tr("ui.submit_documents")}
      </button>
    </main>
  );
}
