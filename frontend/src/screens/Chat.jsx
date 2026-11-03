import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

// Voice answers (languages the server lists in /api/health; English and Hindi for now).
// The recording goes to an AI service to become text, so: the owner is warned before the first recording, the GST
// question has no microphone, and the text comes back into the box to check and correct before it is sent.
let voiceLangsCache = null;
const MAX_RECORDING_MS = 30000;
const SPEECH_LOCALE = { en: "en-IN", hi: "hi-IN" };

const canRecord = () => typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

// Read bot replies aloud with the phone's own voices; skipped quietly if the phone has none for this language
function speak(texts, lang) {
  const synth = window.speechSynthesis;
  if (!synth || !texts.length) return;
  synth.cancel();
  const locale = SPEECH_LOCALE[lang] || "en-IN";
  const voices = synth.getVoices();
  const voice = voices.find((v) => v.lang === locale) || voices.find((v) => v.lang.startsWith(lang));
  if (!voice && lang !== "en") return;   // no Hindi voice on this phone: an English voice would garble it
  for (const t of texts) {
    const u = new SpeechSynthesisUtterance(t.replace(/\p{Extended_Pictographic}/gu, ""));
    u.lang = locale;
    if (voice) u.voice = voice;
    synth.speak(u);
  }
}

export default function Chat({ state, update, tr, onRetry }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(state.error ? "ui.offline" : "");   // a screen-text key
  const [errorText, setErrorText] = useState("");                         // a message already in the owner's language
  const [voiceLangs, setVoiceLangs] = useState(voiceLangsCache);
  const [mic, setMic] = useState("idle");                                  // idle | warn | recording | transcribing
  const [checkHint, setCheckHint] = useState(false);
  const recorder = useRef(null);
  const timer = useRef(null);
  const end = useRef(null);
  const { messages = [], question, rec } = state;

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, busy, mic]);

  useEffect(() => {
    if (!voiceLangsCache) {
      api.health().then((h) => setVoiceLangs((voiceLangsCache = h.voice_languages || []))).catch(() => setVoiceLangs([]));
    }
    return () => {   // leaving the chat: stop any recording and any reading aloud
      if (recorder.current?.state === "recording") recorder.current.stop();
      window.speechSynthesis?.cancel();
    };
  }, []);

  const voiceOn = !rec && (voiceLangs || []).includes(state.lang) && canRecord();
  const gstQuestion = question?.slot === "gstin";
  const micReady = voiceOn && !!state.id && !!question && !gstQuestion && !busy;

  async function send(msg, shown) {
    if (busy || !state.id) return;
    setBusy(true);
    setError("");
    setErrorText("");
    setCheckHint(false);
    window.speechSynthesis?.cancel();
    const before = [...messages, { from: "me", text: shown }];
    update({ messages: before, question: null });
    try {
      const out = await api.send(state.id, msg);
      const bot = out.messages.map((t) => ({ from: "bot", text: t }));
      const patch = { messages: [...before, ...bot], question: out.question };
      if (out.recommendation) {
        patch.rec = out.recommendation;
        patch.items = Object.fromEntries(out.recommendation.core.map((p) => [p.id, p.quantity]));
      }
      update(patch);
      if (state.voiceMode && !state.muted) speak(out.messages, state.lang);
    } catch (e) {
      update({ messages: before, question });   // put the question back so they can answer again
      setError(e.status === 0 ? "ui.offline" : "ui.error");
    } finally {
      setBusy(false);
    }
  }

  function submit(e) {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    setText("");
    send({ text: t }, t);
  }

  function tapMic() {
    if (mic === "recording") return recorder.current?.stop();
    if (!state.voiceWarned) return setMic("warn");   // privacy warning before the first recording
    startRecording();
  }

  async function startRecording() {
    setError("");
    setErrorText("");
    setCheckHint(false);
    window.speechSynthesis?.cancel();
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setMic("idle");
      setErrorText(tr("msg.mic_blocked"));
      return;
    }
    const chunks = [];
    const r = new MediaRecorder(stream);
    r.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    r.onstop = async () => {
      clearTimeout(timer.current);
      stream.getTracks().forEach((t) => t.stop());   // microphone light goes off straight away
      setMic("transcribing");
      try {
        const out = await api.voice(state.id, new Blob(chunks, { type: r.mimeType || "audio/webm" }));
        setText(out.text);                            // the owner checks and corrects it, then taps send
        setCheckHint(true);
        if (!state.voiceMode) update({ voiceMode: true });
      } catch (e) {
        setErrorText(e.message || tr("msg.voice_failed"));
      } finally {
        setMic("idle");
      }
    };
    recorder.current = r;
    r.start();
    setMic("recording");
    timer.current = setTimeout(() => r.state === "recording" && r.stop(), MAX_RECORDING_MS);
  }

  function acceptWarning() {
    update({ voiceWarned: true });
    startRecording();
  }

  function toggleMute() {
    if (!state.muted) window.speechSynthesis?.cancel();
    update({ muted: !state.muted });
  }

  const placeholder = mic === "recording" ? tr("ui.listening") : mic === "transcribing" ? tr("ui.transcribing")
    : tr("ui.type_message");

  return (
    <main className="chat">
      <div className="messages" aria-live="polite">
        {messages.map((m, i) => (
          <p key={i} className={`bubble ${m.from}`}>{m.text}</p>
        ))}
        {(busy || state.starting) && <p className="bubble bot typing">{tr("ui.thinking")}</p>}
        {(error || errorText) && (
          <div className="notice bad" role="alert">
            {errorText || tr(error)}{" "}
            {!state.id && <button className="link" onClick={onRetry}>{tr("ui.start_over")}</button>}
          </div>
        )}
        {question?.options?.length > 0 && !busy && (
          <div className="options">
            {question.options.map((o) => (
              <button key={o.value} className="chip"
                      onClick={() => send({ slot: question.slot, value: o.value }, o.label)}>
                {o.label}
              </button>
            ))}
          </div>
        )}
        {rec && (
          <button className="primary" onClick={() => update({ screen: "plan" })}>{tr("ui.your_plan")} →</button>
        )}
        {mic === "warn" && (
          <div className="notice info voice-warning" role="dialog" aria-label={tr("ui.mic_start")}>
            <p>{tr("ui.voice_warning")}</p>
            <div className="row">
              <button className="primary" onClick={acceptWarning}>{tr("ui.voice_ok")}</button>
              <button className="secondary" onClick={() => setMic("idle")} aria-label="✕">✕</button>
            </div>
          </div>
        )}
        {checkHint && <p className="muted small">{tr("ui.voice_check")}</p>}
        <div ref={end} style={{ scrollMarginBottom: 96 }} />   {/* keep the last item clear of the input bar */}
      </div>

      {!rec && (
        <form className="composer" onSubmit={submit}>
          {voiceOn && state.voiceMode && (
            <button type="button" className="icon-btn" onClick={toggleMute}
                    aria-label={tr(state.muted ? "ui.unmute" : "ui.mute")} title={tr(state.muted ? "ui.unmute" : "ui.mute")}>
              {state.muted ? "🔇" : "🔊"}
            </button>
          )}
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={500}
            placeholder={placeholder}
            inputMode={question?.input === "number" ? "numeric" : "text"}
            aria-label={tr("ui.type_message")}
            disabled={busy || !state.id || mic === "recording" || mic === "transcribing"}
          />
          {voiceOn && (
            <button type="button" className={`mic ${mic}`} onClick={tapMic}
                    disabled={mic === "transcribing" || (!micReady && mic !== "recording")}
                    aria-label={tr(mic === "recording" ? "ui.mic_stop" : "ui.mic_start")}
                    title={gstQuestion ? tr("msg.voice_type_gst") : tr(mic === "recording" ? "ui.mic_stop" : "ui.mic_start")}>
              {mic === "recording" ? "■" : "🎙️"}
            </button>
          )}
          <button type="submit" className="send" disabled={busy || !text.trim() || mic !== "idle"} aria-label={tr("ui.send")}>
            ➤
          </button>
        </form>
      )}
    </main>
  );
}
