import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

export default function Chat({ state, update, tr, onRetry }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(state.error ? "ui.offline" : "");
  const end = useRef(null);
  const { messages = [], question, rec } = state;

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, busy]);

  async function send(msg, shown) {
    if (busy || !state.id) return;
    setBusy(true);
    setError("");
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

  return (
    <main className="chat">
      <div className="messages" aria-live="polite">
        {messages.map((m, i) => (
          <p key={i} className={`bubble ${m.from}`}>{m.text}</p>
        ))}
        {(busy || state.starting) && <p className="bubble bot typing">{tr("ui.thinking")}</p>}
        {error && (
          <div className="notice bad">
            {tr(error)}{" "}
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
        <div ref={end} />
      </div>

      {!rec && (
        <form className="composer" onSubmit={submit}>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={500}
            placeholder={tr("ui.type_message")}
            inputMode={question?.input === "number" ? "numeric" : "text"}
            aria-label={tr("ui.type_message")}
            disabled={busy || !state.id}
          />
          <button type="submit" className="send" disabled={busy || !text.trim()} aria-label={tr("ui.send")}>
            ➤
          </button>
        </form>
      )}
    </main>
  );
}
