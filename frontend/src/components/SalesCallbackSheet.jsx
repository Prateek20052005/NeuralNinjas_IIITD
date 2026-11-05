import { useState } from 'react';
import { Phone } from 'lucide-react';
import { api } from '../api.js';
import BottomSheet from './BottomSheet.jsx';
import Button from './Button.jsx';
import Checkbox from './Checkbox.jsx';
import Note from './Note.jsx';
import TextField from './TextField.jsx';

// A salesperson calls the owner when they want a lower price than the chatbot may give. The number is used only for
// that call (consent tick required), shown only in the back office, masked elsewhere, and erased with the application.
export default function SalesCallbackSheet({ open, onClose, id, tr, onDone }) {
  const [phone, setPhone] = useState('');
  const [target, setTarget] = useState('');
  const [callOk, setCallOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function request() {
    setBusy(true);
    setError('');
    try {
      const out = await api.salesCallback(id, { phone, consent: callOk,
                                                target_monthly: Number(target.replace(/\D/g, '')) || null });
      onDone(out.message);
    } catch (e) {
      setError(e.message || tr(e.status === 0 ? 'ui.offline' : 'ui.error'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <BottomSheet open={open} onClose={onClose} title={tr('ui.ask_sales')} closeLabel={tr('ui.cancel')}>
      <TextField label={tr('ui.phone_label')} type="tel" inputMode="tel" autoComplete="tel" placeholder="98765 43210"
                 value={phone} onChange={(e) => setPhone(e.target.value)} />
      <TextField label={tr('ui.target_label')} inputMode="numeric" placeholder="₹" value={target}
                 onChange={(e) => setTarget(e.target.value)} />
      <div className="inset-group">
        <Checkbox checked={callOk} onChange={setCallOk} label={tr('ui.callback_consent')} />
      </div>
      {error && <Note tone="warn">{error}</Note>}
      <Button block icon={Phone} onClick={request} disabled={busy || !callOk || phone.replace(/\D/g, '').length < 10}>
        {tr('ui.request_call')}
      </Button>
    </BottomSheet>
  );
}
