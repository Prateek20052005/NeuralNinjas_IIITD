import { useEffect, useState } from 'react';
import { KeyRound, Send } from 'lucide-react';
import BottomSheet from './BottomSheet.jsx';
import Button from './Button.jsx';
import Checkbox from './Checkbox.jsx';
import Note from './Note.jsx';
import TextField from './TextField.jsx';

/**
 * Verify a mobile number with a one-time code: number -> code -> verified.
 * send(phone) resolves to {phone (masked), demo_code?}; verify(code, marketing) resolves when the code is right.
 * In demo mode (no SMS provider in the prototype) the server returns the code and it is shown here.
 * withMarketing: a separate, unticked box for offers and news (never required).
 */
export default function PhoneVerifySheet({ open, onClose, tr, title, why, withMarketing = false, send, verify, verifyLabel }) {
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(null); // {phone, demo_code}
  const [marketing, setMarketing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { // every opening starts clean
    if (open) { setCode(''); setSent(null); setError(''); setMarketing(false); }
  }, [open]);

  async function run(fn) {
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(e.message || tr(e.status === 0 ? 'ui.offline' : 'ui.error'));
    } finally {
      setBusy(false);
    }
  }

  const sendCode = () => run(async () => setSent(await send(phone)));
  const checkCode = () => run(async () => verify(code.trim(), marketing));

  return (
    <BottomSheet open={open} onClose={onClose} title={title || tr('ui.verify_title')} closeLabel={tr('ui.cancel')}>
      {why && <Note tone="trust">{why}</Note>}
      {!sent ? (
        <>
          <TextField label={tr('ui.phone_label')} type="tel" inputMode="tel" autoComplete="tel" placeholder="98765 43210"
                     value={phone} onChange={(e) => setPhone(e.target.value)} />
          {error && <Note tone="warn">{error}</Note>}
          <Button block icon={Send} onClick={sendCode} disabled={busy || phone.replace(/\D/g, '').length < 10}>
            {tr('ui.send_code')}
          </Button>
        </>
      ) : (
        <>
          <p className="t-footnote t-secondary">{tr('ui.otp_sent', { phone: sent.phone })}</p>
          {sent.demo_code && <Note tone="info">{tr('ui.otp_demo', { code: sent.demo_code })}</Note>}
          <TextField label={tr('ui.code_label')} inputMode="numeric" autoComplete="one-time-code" maxLength={6} mono
                     value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
          {withMarketing && (
            <div className="inset-group">
              <Checkbox checked={marketing} onChange={setMarketing} label={tr('ui.marketing_consent')} />
            </div>
          )}
          {error && <Note tone="warn">{error}</Note>}
          <Button block icon={KeyRound} onClick={checkCode} disabled={busy || code.length !== 6}>
            {verifyLabel || tr('ui.verify')}
          </Button>
          <Button variant="plain" block onClick={() => { setSent(null); setCode(''); setError(''); }} disabled={busy}>
            {tr('ui.change_number')}
          </Button>
        </>
      )}
    </BottomSheet>
  );
}
