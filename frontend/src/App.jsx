import { useEffect, useState } from "react";
import { api } from "./api.js";
import { useStrings } from "./i18n.js";
import Chat from "./screens/Chat.jsx";
import Plan from "./screens/Plan.jsx";
import Consent from "./screens/Consent.jsx";
import Documents from "./screens/Documents.jsx";
import Tracker from "./screens/Tracker.jsx";

const SAVE_KEY = "accel-application";
const LANGS = [
  { code: "en", name: "English", hello: "Choose your language" },
  { code: "hi", name: "हिंदी", hello: "अपनी भाषा चुनिए" },
  { code: "mr", name: "मराठी", hello: "तुमची भाषा निवडा" },
  { code: "gu", name: "ગુજરાતી", hello: "તમારી ભાષા પસંદ કરો" },
  { code: "ta", name: "தமிழ்", hello: "மொழியைத் தேர்வு செய்யுங்கள்" },
  { code: "te", name: "తెలుగు", hello: "మీ భాషను ఎంచుకోండి" },
  { code: "kn", name: "ಕನ್ನಡ", hello: "ನಿಮ್ಮ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ" },
];

// Progress lives on the owner's own phone so a refresh doesn't lose the chat. Never required: the app
// works without it (private mode, storage blocked).
function load() {
  try {
    return JSON.parse(localStorage.getItem(SAVE_KEY)) || null;
  } catch {
    return null;
  }
}
function save(state) {
  try {
    if (state) localStorage.setItem(SAVE_KEY, JSON.stringify(state));
    else localStorage.removeItem(SAVE_KEY);
  } catch { /* storage unavailable: nothing to do */ }
}

export default function App() {
  const [state, setState] = useState(load);   // {id, lang, screen, messages, question, rec}
  const lang = state?.lang || "en";
  const tr = useStrings(lang);

  useEffect(() => save(state), [state]);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  useEffect(() => {   // a saved application the server no longer has (expired or deleted): start fresh
    if (state?.id) api.status(state.id).catch((e) => e.status === 404 && setState(null));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const update = (patch) => setState((s) => ({ ...s, ...patch }));
  const go = (screen) => update({ screen });

  async function start(code) {
    setState({ lang: code, screen: "chat", messages: [], question: null, starting: true });
    try {
      const out = await api.start(code);
      setState({ id: out.id, lang: code, screen: "chat", question: out.question,
                 messages: out.messages.map((text) => ({ from: "bot", text })) });
    } catch {
      setState({ lang: code, screen: "chat", messages: [], question: null, error: true });
    }
  }

  const reset = () => setState(null);
  const screen = state?.screen || "language";
  useEffect(() => {
    if (screen !== "chat") window.scrollTo(0, 0);   // each new screen starts at its top
  }, [screen]);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand" onClick={() => !state?.id && reset()}>
          <span className="logo" aria-hidden="true">A</span>
          <span>Accel Business</span>
        </div>
        {state?.id && state.screen !== "chat" && state.screen !== "tracker" && state.accepted && (
          <button className="link" onClick={() => go("tracker")}>{tr("ui.tracker_title")}</button>
        )}
      </header>

      {screen === "language" && (
        <main className="language">
          <h1>Accel Business</h1>
          <p className="muted">{tr("ui.tagline")}</p>
          <div className="lang-buttons">
            {LANGS.map((l) => (
              <button key={l.code} className="lang-btn" onClick={() => start(l.code)} lang={l.code}>
                <strong>{l.name}</strong>
                <span>{l.hello}</span>
              </button>
            ))}
          </div>
        </main>
      )}
      {screen === "chat" && (
        <Chat state={state} update={update} tr={tr} onRetry={() => start(lang)} />
      )}
      {screen === "plan" && <Plan state={state} update={update} tr={tr} />}
      {screen === "consent" && <Consent state={state} update={update} tr={tr} />}
      {screen === "documents" && <Documents state={state} update={update} tr={tr} />}
      {screen === "tracker" && (
        // deleting wipes the saved chat on this phone too: only the confirmation (no personal data) remains
        <Tracker state={state} update={update} tr={tr} onErased={(message) => setState({ lang, screen: "deleted", message })} />
      )}
      {screen === "deleted" && (
        <main className="page">
          <p className="notice ok">{state.message}</p>
          <button className="primary" onClick={reset}>{tr("ui.start_over")}</button>
        </main>
      )}
    </div>
  );
}
