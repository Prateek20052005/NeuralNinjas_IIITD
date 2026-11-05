import { useEffect, useState } from 'react';
import { WifiOff } from 'lucide-react';
import { api } from './api.js';
import { useStrings } from './i18n.js';
import HeaderActions from './components/HeaderActions.jsx';
import Toast from './components/Toast.jsx';
import Home from './screens/Home.jsx';
import Chat from './screens/Chat.jsx';
import Plan from './screens/Plan.jsx';
import Consent from './screens/Consent.jsx';
import Documents from './screens/Documents.jsx';
import Tracker from './screens/Tracker.jsx';
import Privacy from './screens/Privacy.jsx';
import Deleted from './screens/Deleted.jsx';
import NotFound from './screens/NotFound.jsx';
import BackOffice from './screens/BackOffice.jsx';

const SAVE_KEY = 'accel-application';
const THEME_KEY = 'accel-theme';

// Progress lives on the owner's own phone so a refresh doesn't lose the chat. Never required: the app works
// without it (private mode, storage blocked).
function read(key) {
  try {
    return JSON.parse(localStorage.getItem(key));
  } catch {
    return null;
  }
}
function write(key, value) {
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch { /* storage unavailable: nothing to do */ }
}

const osDark = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches;

function useHash() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return hash;
}

function useOnline() {
  const [online, setOnline] = useState(navigator.onLine !== false);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener('online', up);
    window.addEventListener('offline', down);
    return () => {
      window.removeEventListener('online', up);
      window.removeEventListener('offline', down);
    };
  }, []);
  return online;
}

export default function App() {
  const [state, setState] = useState(() => read(SAVE_KEY)); // {id, lang, screen, messages, question, rec, ...}
  const [homeLang, setHomeLang] = useState(state?.lang || 'en'); // language picked on the home screen
  const [chosenTheme, setChosenTheme] = useState(() => read(THEME_KEY)); // null = follow the phone
  const [toast, setToast] = useState(null);
  const hash = useHash();
  const online = useOnline();
  const screen = state?.screen || 'home';
  const lang = screen === 'home' ? homeLang : state?.lang || 'en';
  const tr = useStrings(lang);
  const theme = chosenTheme || (osDark() ? 'dark' : 'light');

  useEffect(() => write(SAVE_KEY, state && state.screen !== 'deleted' ? state : null), [state]);
  useEffect(() => {
    document.documentElement.lang = hash === '#/office' ? 'en' : lang; // the staff back office is English
  }, [lang, hash]);
  useEffect(() => {
    if (chosenTheme) document.documentElement.dataset.theme = chosenTheme;
    else delete document.documentElement.dataset.theme;
    write(THEME_KEY, chosenTheme);
  }, [chosenTheme]);
  useEffect(() => { // a saved application the server no longer has (expired or deleted): start fresh
    if (state?.id) api.status(state.id).catch((e) => e.status === 404 && setState(null));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (screen !== 'chat') window.scrollTo(0, 0); // each new screen starts at its top
  }, [screen]);

  const update = (patch) => setState((s) => ({ ...s, ...patch }));
  const go = (next) => update({ screen: next, back: screen });

  async function start(code) {
    setState({ lang: code, screen: 'chat', messages: [], question: null, starting: true });
    try {
      const out = await api.start(code);
      setState({ id: out.id, lang: code, screen: 'chat', question: out.question,
                 messages: out.messages.map((text) => ({ from: 'bot', text })) });
    } catch {
      setState({ lang: code, screen: 'chat', messages: [], question: null, error: true });
    }
  }

  // where "Continue" on the home screen takes the owner
  const resume = () => update({ screen: state?.accepted ? 'tracker' : state?.rec ? 'plan' : 'chat' });

  if (hash === '#/office') return <BackOffice theme={theme} onTheme={() => setChosenTheme(theme === 'dark' ? 'light' : 'dark')} />;

  const actions = (
    <HeaderActions tr={tr} theme={theme} onTheme={() => setChosenTheme(theme === 'dark' ? 'light' : 'dark')}
                   onPrivacy={state?.id && screen !== 'privacy' ? () => go('privacy') : null} />
  );
  const common = { state, update, tr, go, actions, toast: setToast };

  let body;
  if (hash && hash !== '#' && hash !== '#/') {
    body = <NotFound tr={tr} onHome={() => { window.location.hash = ''; }} />;
  } else if (screen === 'home') {
    body = <Home tr={tr} lang={homeLang} setLang={setHomeLang} saved={state?.id ? state : null}
                 onStart={() => start(homeLang)} onResume={resume} actions={actions}
                 onResumed={(snapshot) => { setHomeLang(snapshot.lang); setState(snapshot); }} />;
  } else if (screen === 'chat') {
    body = <Chat {...common} onRetry={() => start(lang)} onHome={() => update({ screen: 'home' })} />;
  } else if (screen === 'plan') {
    body = <Plan {...common} />;
  } else if (screen === 'consent') {
    body = <Consent {...common} />;
  } else if (screen === 'documents') {
    body = <Documents {...common} />;
  } else if (screen === 'tracker') {
    body = <Tracker {...common} onHome={() => update({ screen: 'home' })}
                    onErased={(message) => setState({ lang, screen: 'deleted', message })} />;
  } else if (screen === 'privacy') {
    body = <Privacy {...common} onErased={(message) => setState({ lang, screen: 'deleted', message })} />;
  } else {
    body = <Deleted tr={tr} message={state?.message} onRestart={() => setState(null)} actions={actions} />;
  }

  return (
    <>
      {!online && (
        <div className="offline-bar" role="status" lang={lang}>
          <WifiOff size={16} strokeWidth={2} aria-hidden="true" /> {tr('ui.offline')}
        </div>
      )}
      {body}
      <Toast open={!!toast} message={toast} onDone={() => setToast(null)} />
    </>
  );
}
