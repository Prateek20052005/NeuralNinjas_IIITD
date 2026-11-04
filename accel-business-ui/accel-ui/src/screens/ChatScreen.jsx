import { useState } from 'react';
import { Mic, ArrowUp } from 'lucide-react';
import AppHeader from '../components/AppHeader.jsx';
import ProgressIndicator from '../components/ProgressIndicator.jsx';
import ChatBubble from '../components/ChatBubble.jsx';
import TypingIndicator from '../components/TypingIndicator.jsx';
import Chip from '../components/Chip.jsx';
import ChipGroup from '../components/ChipGroup.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import './ChatScreen.css';

const KINDS = ['Shop', 'Workshop or factory', 'Clinic', 'Office', 'Restaurant', 'Something else'];

/** Advisor chat, one question at a time. Wire `onAnswer` to your conversation engine. */
export default function ChatScreen({ onBack, onAnswer, headerActions }) {
  const [picked, setPicked] = useState(null);
  const [draft, setDraft] = useState('');

  function answer(text) {
    setPicked(text);
    onAnswer?.(text);
  }

  return (
    <div className="app-shell">
      <AppHeader title="Advisor" subtitle="Answers in seconds" onBack={onBack} actions={headerActions}>
        <ProgressIndicator current={3} total={8} />
      </AppHeader>

      <main className="ab-chat" aria-live="polite">
        <ChatBubble>Namaste! A few quick questions and I'll suggest the right plan. What's your GST number? I can fill in your details from it.</ChatBubble>
        <ChatBubble from="owner"><span className="t-mono">27XUI******1ZP</span></ChatBubble>
        <ChatBubble>
          Is this your business?
          <span className="ab-chat__card">
            <span>
              <b>Ganesh Woodcraft</b>
              <br />
              <span className="t-footnote t-secondary">Nagpur, Maharashtra</span>
            </span>
            <StatusBadge status="approved">GST active</StatusBadge>
          </span>
        </ChatBubble>
        <ChatBubble from="owner">Yes, that's us</ChatBubble>
        <ChatBubble>Great. What kind of business is it?</ChatBubble>
        <ChatBubble from="owner">both</ChatBubble>
        <ChatBubble from="hint" avatar={false}>
          Sorry, I didn't catch that. Tap the closest option below, or tell me what you make or sell.
        </ChatBubble>
        {picked ? (
          <>
            <ChatBubble from="owner">{picked}</ChatBubble>
            <TypingIndicator />
          </>
        ) : null}
      </main>

      <footer className="ab-composer">
        <ChipGroup label="Kind of business">
          {KINDS.map((k) => (
            <Chip key={k} selected={picked === k} onClick={() => answer(k)}>
              {k}
            </Chip>
          ))}
        </ChipGroup>
        <form
          className="ab-composer__row"
          onSubmit={(e) => {
            e.preventDefault();
            if (draft.trim()) answer(draft.trim());
            setDraft('');
          }}
        >
          <label htmlFor="chat-input" className="visually-hidden">
            Your answer
          </label>
          <input id="chat-input" className="ab-composer__input" placeholder="Type your answer or a question" value={draft} onChange={(e) => setDraft(e.target.value)} />
          <button type="button" className="ab-composer__mic" aria-label="Speak your answer">
            <Mic size={22} strokeWidth={1.75} aria-hidden="true" />
          </button>
          <button type="submit" className="ab-composer__send" aria-label="Send">
            <ArrowUp size={22} strokeWidth={2.2} aria-hidden="true" />
          </button>
        </form>
      </footer>
    </div>
  );
}
