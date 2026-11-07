import { useEffect, useRef, useState } from 'react';
import { ArrowRight, ArrowUp, BookmarkCheck, BookmarkPlus, Lock, Mic, Phone, Square, Volume2, VolumeX } from 'lucide-react';
import { api } from '../api.js';
import AppHeader from '../components/AppHeader.jsx';
import BottomSheet from '../components/BottomSheet.jsx';
import Button from '../components/Button.jsx';
import ChatBubble from '../components/ChatBubble.jsx';
import Chip from '../components/Chip.jsx';
import ChipGroup from '../components/ChipGroup.jsx';
import Note from '../components/Note.jsx';
import ProgressIndicator from '../components/ProgressIndicator.jsx';
import SalesCallbackSheet from '../components/SalesCallbackSheet.jsx';
import PhoneVerifySheet from '../components/PhoneVerifySheet.jsx';
import TypingIndicator from '../components/TypingIndicator.jsx';

// Voice answers (languages the server lists in /api/health; English and Hindi for now).
// The recording goes to an AI service to become text, so: the owner is warned before the first recording, the GST
// question has no microphone, and the text comes back into the box to check and correct before it is sent.
let voiceLangsCache = null;
const MAX_RECORDING_MS = 30000;
const SPEECH_LOCALE = { en: 'en-IN', hi: 'hi-IN' };

const canRecord = () => typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;

// Read bot replies aloud with the phone's own voices; skipped quietly if the phone has none for this language
function speak(texts, lang) {
  const synth = window.speechSynthesis;
  if (!synth || !texts.length) return;
  synth.cancel();
  const locale = SPEECH_LOCALE[lang] || 'en-IN';
  const voices = synth.getVoices();
  const voice = voices.find((v) => v.lang === locale) || voices.find((v) => v.lang.startsWith(lang));
  if (!voice && lang !== 'en') return; // no Hindi voice on this phone: an English voice would garble it
  for (const t of texts) {
    const u = new SpeechSynthesisUtterance(t.replace(/\p{Extended_Pictographic}/gu, ''));
    u.lang = locale;
    if (voice) u.voice = voice;
    synth.speak(u);
  }
}

export default function Chat({ state, update, tr, actions, onRetry, onHome, toast }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(state.error ? 'ui.offline' : ''); // a screen-text key
  const [errorText, setErrorText] = useState(''); // a message already in the owner's language
  const [voiceLangs, setVoiceLangs] = useState(voiceLangsCache);
  const [mic, setMic] = useState('idle'); // idle | warn | recording | transcribing
  const [checkHint, setCheckHint] = useState(false);
  const [business, setBusiness] = useState(null); // the GST registry's answer, shown as a card
  const [sheet, setSheet] = useState(false); // call-me form: price, help with GST, or a chat that isn't working
  const [sheetReason, setSheetReason] = useState('price');
  const neg = state.neg || {}; // price talk after the plan: pushback | offer | final | handoff | called
  const [saving, setSaving] = useState(false); // "save my progress" sheet
  const recorder = useRef(null);
  const timer = useRef(null);
  const end = useRef(null);
  const dock = useRef(null);
  const { messages = [], question, rec, lang } = state;

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, busy, mic, question?.slot]);

  // The composer sticks to the bottom and grows when answer chips appear: keep the newest message above it.
  useEffect(() => {
    const el = dock.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(() => {
      if (!end.current) return;
      end.current.style.scrollMarginBottom = `${el.offsetHeight + 8}px`;
      end.current.scrollIntoView({ block: 'end' });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [rec]);

  useEffect(() => {
    if (!voiceLangsCache) {
      api.health().then((h) => setVoiceLangs((voiceLangsCache = h.voice_languages || []))).catch(() => setVoiceLangs([]));
    }
    return () => { // leaving the chat: stop any recording and any reading aloud
      if (recorder.current?.state === 'recording') recorder.current.stop();
      window.speechSynthesis?.cancel();
    };
  }, []);

  // "Is this your business?": show what the registry returned (name, city, masked GSTIN) as a card
  useEffect(() => {
    if (question?.slot !== 'gst_confirm' || !state.id) return;
    api.status(state.id).then((s) => setBusiness(s.profile)).catch(() => {});
  }, [question?.slot, state.id]);

  // after the plan the chat stays open for questions and price talk (until the plan is accepted)
  const talking = !!rec && !state.accepted;
  const voiceOn = (voiceLangs || []).includes(lang) && canRecord() && (!rec || talking);
  const gstQuestion = question?.slot === 'gstin';
  const micReady = voiceOn && !!state.id && (!!question || talking) && !gstQuestion && !busy;
  const progress = question?.steps ? { n: question.step, total: question.steps } : state.progress;

  async function send(msg, shown) {
    if (busy || !state.id) return;
    setBusy(true);
    setError('');
    setErrorText('');
    setCheckHint(false);
    window.speechSynthesis?.cancel();
    const before = [...messages, { from: 'me', text: shown }];
    update({ messages: before, question: null, progress });
    try {
      const out = await api.send(state.id, msg);
      const bot = out.messages.map((t) => ({ from: 'bot', text: t }));
      const patch = { messages: [...before, ...bot], question: out.question };
      if (out.recommendation) {
        patch.rec = out.recommendation;
        patch.items = Object.fromEntries(out.recommendation.core.map((p) => [p.id, p.quantity]));
        patch.progress = progress && { n: progress.total, total: progress.total };
      }
      if (out.quote) patch.quote = out.quote; // a discount given in the chat shows on the plan screen too
      if (out.negotiation) patch.neg = { status: out.negotiation.status };
      if (out.handoff && !state.handoffCalled) patch.handoff = out.handoff; // gst_help | unclear: offer a person
      update(patch);
      if (out.negotiation?.status === 'handoff') {
        setSheetReason('price');
        setSheet(true);
      }
      if (state.voiceMode && !state.muted) speak(out.messages, lang);
    } catch (e) {
      update({ messages: before.slice(0, -1), question }); // put the question back so they can answer again
      setText(msg.text || '');
      setError(e.status === 0 ? 'ui.offline' : 'ui.error');
    } finally {
      setBusy(false);
    }
  }

  function submit(e) {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    setText('');
    send({ text: t }, t);
  }

  function tapMic() {
    if (mic === 'recording') return recorder.current?.stop();
    if (!state.voiceWarned) return setMic('warn'); // privacy warning before the first recording
    startRecording();
  }

  async function startRecording() {
    setError('');
    setErrorText('');
    setCheckHint(false);
    window.speechSynthesis?.cancel();
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setMic('idle');
      setErrorText(tr('msg.mic_blocked'));
      return;
    }
    const chunks = [];
    const r = new MediaRecorder(stream);
    r.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    r.onstop = async () => {
      clearTimeout(timer.current);
      setMic('transcribing');
      // iPhone Safari delivers the last piece of audio just after "stop": wait for it before sending
      await new Promise((ok) => setTimeout(ok, 300));
      stream.getTracks().forEach((t) => t.stop()); // then the microphone light goes off
      const audio = new Blob(chunks, { type: r.mimeType || 'audio/webm' });
      if (audio.size < 1000) { // nothing recorded: say so instead of sending an empty file
        setErrorText(tr('msg.voice_failed'));
        setMic('idle');
        return;
      }
      try {
        const out = await api.voice(state.id, audio);
        setText(out.text); // the owner checks and corrects it, then taps send
        setCheckHint(true);
        if (!state.voiceMode) update({ voiceMode: true });
      } catch (e) {
        setErrorText(e.message || tr('msg.voice_failed'));
      } finally {
        setMic('idle');
      }
    };
    recorder.current = r;
    r.start(250); // audio arrives in small pieces while recording (needed on iPhone Safari)
    setMic('recording');
    timer.current = setTimeout(() => r.state === 'recording' && r.stop(), MAX_RECORDING_MS);
  }

  function acceptWarning() {
    update({ voiceWarned: true });
    startRecording();
  }

  function toggleMute() {
    if (!state.muted) window.speechSynthesis?.cancel();
    update({ muted: !state.muted });
  }

  const hints = new Set([tr('msg.yes_no_hint'), tr('msg.pick_option')].filter(Boolean));
  const notice = tr('msg.ai_notice');
  const placeholder = mic === 'recording' ? tr('ui.listening') : mic === 'transcribing' ? tr('ui.transcribing')
    : rec ? tr('ui.ask_about_plan') : tr('ui.type_message');

  function callRequested(message) {
    setSheet(false);
    const said = [...messages, { from: 'bot', text: message }];
    if (sheetReason === 'price') update({ messages: said, neg: { status: 'called' } });
    else update({ messages: said, handoffCalled: true, handoff: null });
  }
  const askCall = (reason) => {
    setSheetReason(reason);
    setSheet(true);
  };
  const numeric = question?.input === 'number';

  function bubble(m, i) {
    if (m.from === 'me') return <ChatBubble key={i} from="owner">{m.text}</ChatBubble>;
    if (notice && m.text === notice) { // the privacy notice about the AI: a quiet trust note, not a chat line
      return (
        <p key={i} className="bub-note" role="note">
          <Lock size={16} strokeWidth={1.9} aria-hidden="true" />
          <span>{m.text.replace(/^\p{Extended_Pictographic}\s*/u, '')}</span>
        </p>
      );
    }
    const next = messages[i + 1];
    const lastInRun = !next || next.from !== 'bot' || next.text === notice;
    return <ChatBubble key={i} from={hints.has(m.text) ? 'hint' : 'assistant'} avatar={lastInRun}>{m.text}</ChatBubble>;
  }

  // optional: save progress with a verified mobile number, to continue on any phone
  const saveBtn = state.id ? (
    <button type="button" className="ab-icon-btn"
            aria-label={state.phoneVerified ? tr('ui.progress_saved', { phone: state.phoneSaved }) : tr('ui.save_progress')}
            title={state.phoneVerified ? tr('ui.progress_saved', { phone: state.phoneSaved }) : tr('ui.save_progress')}
            onClick={() => (state.phoneVerified ? toast?.(tr('ui.progress_saved', { phone: state.phoneSaved })) : setSaving(true))}>
      {state.phoneVerified
        ? <BookmarkCheck size={21} strokeWidth={1.75} aria-hidden="true" />
        : <BookmarkPlus size={21} strokeWidth={1.75} aria-hidden="true" />}
    </button>
  ) : null;

  const muteBtn = voiceOn && state.voiceMode ? (
    <button type="button" className="ab-icon-btn" onClick={toggleMute}
            aria-label={tr(state.muted ? 'ui.unmute' : 'ui.mute')} title={tr(state.muted ? 'ui.unmute' : 'ui.mute')}>
      {state.muted ? <VolumeX size={21} strokeWidth={1.75} aria-hidden="true" /> : <Volume2 size={21} strokeWidth={1.75} aria-hidden="true" />}
    </button>
  ) : null;

  return (
    <div className="app-shell" lang={lang}>
      <AppHeader title={tr('ui.advisor')} subtitle={tr('ui.advisor_sub')} onBack={onHome} backLabel={tr('ui.back')}
                 actions={<>{saveBtn}{muteBtn}{actions}</>}>
        {progress ? (
          <ProgressIndicator current={progress.n} total={progress.total}
                             formatLabel={(n, total) => tr('ui.step_of', { n, total })} />
        ) : null}
      </AppHeader>

      <main className="ab-chat" aria-live="polite">
        {state.partner && (
          <Note tone="trust">{tr(state.partner.assisted ? 'ui.assisted_by' : 'ui.referred_by', { partner: state.partner.name })}</Note>
        )}
        {messages.map(bubble)}
        {question?.slot === 'gst_confirm' && business?.business_name && !busy && (
          <ChatBubble avatar={false}>
            <span className="ab-chat__card biz-card" style={{ marginTop: 0 }}>
              <b>{business.business_name}</b>
              <span className="t-footnote t-secondary">{business.city}</span>
              <span className="t-mono t-footnote t-secondary">GSTIN {business.gstin}</span>
            </span>
          </ChatBubble>
        )}
        {(busy || state.starting) && <TypingIndicator label={tr('ui.thinking')} />}
        {(error || errorText) && (
          <div role="alert" className="stack">
            <Note tone="warn">{errorText || tr(error)}</Note>
            {!state.id && <Button variant="secondary" onClick={onRetry}>{tr('ui.start_over')}</Button>}
          </div>
        )}
        <div ref={end} className="ab-chat__end" />
      </main>

      <footer className={`ab-composer ${rec ? 'chat-done' : ''}`} ref={dock}>
        {!rec && question?.options?.length > 0 && !busy && (
          <ChipGroup label={question.text}>
            {question.options.map((o) => (
              <Chip key={o.value} numeric={numeric} onClick={() => send({ slot: question.slot, value: o.value }, o.label)}>
                {o.label}
              </Chip>
            ))}
          </ChipGroup>
        )}
        {rec && neg.status === 'handoff' && (
          <Button variant="secondary" block icon={Phone} onClick={() => askCall('price')}>{tr('ui.request_call')}</Button>
        )}
        {!rec && state.handoff && !busy && (
          <Button variant="secondary" size="sm" block icon={Phone} onClick={() => askCall(state.handoff)}>
            {tr(state.handoff === 'gst_help' ? 'ui.gst_help_btn' : 'ui.call_me_btn')}
          </Button>
        )}
        {rec && <Button block icon={ArrowRight} onClick={() => update({ screen: 'plan' })}>{tr('ui.your_plan')}</Button>}
        {checkHint && <p className="ab-composer__hint">{tr('ui.voice_check')}</p>}
        {(!rec || talking) && (
          <form className="ab-composer__row" onSubmit={submit}>
            <label htmlFor="chat-input" className="visually-hidden">{tr('ui.type_message')}</label>
            <input
              id="chat-input"
              className="ab-composer__input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={500}
              placeholder={placeholder}
              inputMode={numeric ? 'numeric' : 'text'}
              autoComplete="off"
              disabled={busy || !state.id || mic === 'recording' || mic === 'transcribing'}
            />
            {voiceOn && (
              <button type="button" className={`ab-composer__mic ${mic === 'recording' ? 'is-recording' : ''}`} onClick={tapMic}
                      disabled={mic === 'transcribing' || (!micReady && mic !== 'recording')}
                      aria-label={tr(mic === 'recording' ? 'ui.mic_stop' : 'ui.mic_start')}
                      title={gstQuestion ? tr('msg.voice_type_gst') : tr(mic === 'recording' ? 'ui.mic_stop' : 'ui.mic_start')}>
                {mic === 'recording'
                  ? <Square size={18} strokeWidth={2.4} fill="currentColor" aria-hidden="true" />
                  : <Mic size={22} strokeWidth={1.75} aria-hidden="true" />}
              </button>
            )}
            <button type="submit" className="ab-composer__send" disabled={busy || !text.trim() || mic !== 'idle'}
                    aria-label={tr('ui.send')}>
              <ArrowUp size={22} strokeWidth={2.2} aria-hidden="true" />
            </button>
          </form>
        )}
      </footer>

      <SalesCallbackSheet open={sheet} onClose={() => setSheet(false)} id={state.id} tr={tr} onDone={callRequested}
                          reason={sheetReason}
                          verifiedPhone={state.phoneVerified ? state.phoneSaved : null} />
      <PhoneVerifySheet open={saving} onClose={() => setSaving(false)} tr={tr} title={tr('ui.save_progress')}
                        why={tr('ui.phone_why_save')}
                        send={(phone) => api.phoneSend(state.id, phone)}
                        verify={async (code) => {
                          const out = await api.phoneVerify(state.id, code, false);
                          update({ phoneVerified: true, phoneSaved: out.phone });
                          setSaving(false);
                          toast?.(tr('ui.progress_saved', { phone: out.phone }));
                        }} />

      {/* closing the sheet because recording started must not cancel the recording */}
      <BottomSheet open={mic === 'warn'} onClose={() => setMic((m) => (m === 'warn' ? 'idle' : m))}
                   title={tr('ui.mic_start')} closeLabel={tr('ui.cancel')}>
        <Note tone="trust">{tr('ui.voice_warning').replace(/^\p{Extended_Pictographic}\s*/u, '')}</Note>
        <Button block icon={Mic} onClick={acceptWarning}>{tr('ui.voice_ok')}</Button>
      </BottomSheet>
    </div>
  );
}
