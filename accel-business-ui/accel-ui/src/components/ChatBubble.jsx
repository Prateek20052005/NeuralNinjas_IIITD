import { Sparkles, Lightbulb } from 'lucide-react';
import './ChatBubble.css';

/**
 * from: 'assistant' | 'owner' | 'hint'
 * `avatar` shows the advisor mark on assistant bubbles (hide it on consecutive ones).
 */
export default function ChatBubble({ from = 'assistant', avatar = true, children }) {
  if (from === 'owner') {
    return (
      <div className="ab-msg ab-msg--me">
        <div className="ab-bub ab-bub--owner">{children}</div>
      </div>
    );
  }
  return (
    <div className="ab-msg">
      <span className={['ab-msg__av', !avatar && 'is-ghost'].filter(Boolean).join(' ')} aria-hidden="true">
        <Sparkles size={16} strokeWidth={2} />
      </span>
      {from === 'hint' ? (
        <div className="ab-bub ab-bub--hint" role="note">
          <Lightbulb size={18} strokeWidth={1.75} aria-hidden="true" />
          <span>{children}</span>
        </div>
      ) : (
        <div className="ab-bub ab-bub--assistant">{children}</div>
      )}
    </div>
  );
}
