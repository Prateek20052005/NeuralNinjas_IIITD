import { Sparkles } from 'lucide-react';
import './TypingIndicator.css';

export default function TypingIndicator({ label = 'Advisor is typing' }) {
  return (
    <div className="ab-msg" role="status" aria-label={label}>
      <span className="ab-msg__av" aria-hidden="true">
        <Sparkles size={16} strokeWidth={2} />
      </span>
      <div className="ab-typing" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
    </div>
  );
}
