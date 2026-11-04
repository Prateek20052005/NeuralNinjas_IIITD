import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import ChatScreen from './screens/ChatScreen.jsx';
import PlanScreen from './screens/PlanScreen.jsx';
import DocumentsScreen from './screens/DocumentsScreen.jsx';
import TrackerScreen from './screens/TrackerScreen.jsx';
import LanguageSwitcher from './components/LanguageSwitcher.jsx';
import Toast from './components/Toast.jsx';
import SegmentedControl from './components/SegmentedControl.jsx';

/**
 * Demo harness: walks Chat → Plan → Documents → Tracker.
 * Replace with your router; every screen takes plain callbacks.
 */
export default function App() {
  const [screen, setScreen] = useState('plan');
  const [lang, setLang] = useState('en');
  const [theme, setTheme] = useState('light');
  const [decision, setDecision] = useState('approved');
  const [toast, setToast] = useState(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.lang = lang;
  }, [theme, lang]);

  const themeBtn = (
    <button
      type="button"
      className="ab-icon-btn"
      aria-label={theme === 'dark' ? 'Use light mode' : 'Use dark mode'}
      onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
    >
      {theme === 'dark' ? <Sun size={22} strokeWidth={1.75} aria-hidden="true" /> : <Moon size={22} strokeWidth={1.75} aria-hidden="true" />}
    </button>
  );
  const headerActions = (
    <>
      <LanguageSwitcher value={lang} onChange={setLang} />
      {themeBtn}
    </>
  );

  return (
    <>
      <nav className="demo-nav" aria-label="Demo screens">
        <SegmentedControl
          label="Screen"
          value={screen}
          onChange={setScreen}
          options={[
            { value: 'chat', label: 'Chat' },
            { value: 'plan', label: 'Plan' },
            { value: 'docs', label: 'Docs' },
            { value: 'tracker', label: 'Tracker' },
          ]}
        />
        {screen === 'tracker' ? (
          <SegmentedControl
            label="Decision"
            value={decision}
            onChange={setDecision}
            options={[
              { value: 'approved', label: 'OK' },
              { value: 'retake', label: 'Retake' },
              { value: 'review', label: 'Review' },
              { value: 'rejected', label: 'No' },
            ]}
          />
        ) : null}
      </nav>

      {screen === 'chat' && <ChatScreen headerActions={headerActions} onAnswer={() => {}} />}
      {screen === 'plan' && (
        <PlanScreen lang={lang} onBack={() => setScreen('chat')} onAccept={() => setScreen('docs')} onShare={() => setToast('Quote saved as PDF')} />
      )}
      {screen === 'docs' && <DocumentsScreen onBack={() => setScreen('plan')} onContinue={() => setScreen('tracker')} />}
      {screen === 'tracker' && (
        <TrackerScreen decision={decision} headerActions={headerActions} onBack={() => setScreen('docs')} onDelete={() => setToast('Your data is deleted')} />
      )}

      <Toast open={!!toast} message={toast} onDone={() => setToast(null)} />
    </>
  );
}
