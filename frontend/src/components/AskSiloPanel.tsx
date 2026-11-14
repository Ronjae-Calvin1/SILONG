import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import { Icon } from "./icons";
import siloBot from "../assets/silo-bot-icon.png"; // the Silo umbrella + bot art (white on transparent)
import "./AskSiloPanel.css";

type Props = {
  open: boolean;
  onClose: () => void;
};

const MAX_LENGTH = 200; // longest question, shown as the "0 / 200" counter

const SUGGESTIONS = [
  "What should I do during a flood?",
  "When should I evacuate?",
  "What should I pack in a go-bag?",
  "How do I report a flooded road?",
];

// If the backend answers with one of these, the chatbot route is not there yet. Trying again will not help.
const NOT_AVAILABLE_STATUSES = [404, 405, 501];

// Everything on screen is one of these. Each question stands alone: only the question text
// is sent to the backend, never the earlier messages.
type Message =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "silo"; kind: "pending" }
  | { id: number; role: "silo"; kind: "answer"; text: string; topic: string | null }
  | { id: number; role: "silo"; kind: "problem"; title: string; detail: string; question: string; canRetry: boolean };

// Plain-language message for something that went wrong. Never shows a made-up answer.
function describeProblem(err: unknown): { title: string; detail: string; canRetry: boolean } {
  if (!navigator.onLine) {
    return { title: "I can’t answer without the internet.", detail: "Please check your connection and try again.", canRetry: true };
  }
  if (err instanceof ApiError) {
    if (err.status === 0) {
      return { title: "I can’t reach the SILONG server.", detail: "Please check your connection and try again.", canRetry: true };
    }
    if (NOT_AVAILABLE_STATUSES.includes(err.status)) {
      return {
        title: "Silo is not available yet.",
        detail: "For now, follow the official advisories from PAGASA, NDRRMC and the city.",
        canRetry: false,
      };
    }
    return { title: "Silo could not answer that.", detail: err.message, canRetry: true };
  }
  return { title: "Silo could not answer that.", detail: "Something went wrong. Please try again.", canRetry: true };
}

// The Silo picture in a round blue badge. Used in the header and beside every Silo message.
function SiloAvatar({ large = false }: { large?: boolean }) {
  return (
    <span className={`silo-avatar${large ? " silo-avatar-lg" : ""}`} aria-hidden="true">
      <img src={siloBot} alt="" />
    </span>
  );
}

export function AskSiloPanel({ open, onClose }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [optionsOpen, setOptionsOpen] = useState(false); // the "Chat options" sheet
  const [online, setOnline] = useState(() => navigator.onLine);

  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const moreRef = useRef<HTMLButtonElement>(null);
  const sheetCloseRef = useRef<HTMLButtonElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);
  const runId = useRef(0); // goes up when the chat is cleared, so an answer that arrives late is dropped

  const pending = messages.some((m) => m.role === "silo" && m.kind === "pending");
  const started = messages.length > 0;
  const canSend = online && !pending && draft.trim().length > 0;

  // Focus the close button when the panel opens; forget the options sheet when it closes.
  useEffect(() => {
    if (open) closeRef.current?.focus({ preventScroll: true });
    else setOptionsOpen(false);
  }, [open]);

  // Escape closes the options sheet first, then the panel.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      if (optionsOpen) closeOptions();
      else onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, optionsOpen, onClose]);

  // Move focus into the options sheet when it opens.
  useEffect(() => {
    if (optionsOpen) sheetCloseRef.current?.focus({ preventScroll: true });
  }, [optionsOpen]);

  // Online / offline: the input is switched off while there is no connection.
  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  // Always show the newest message. With no messages yet, stay at the top so the welcome card is fully visible.
  useEffect(() => {
    const el = threadRef.current;
    if (!el) return;
    if (messages.length === 0) {
      el.scrollTop = 0;
      return;
    }
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ top: el.scrollHeight, behavior: calm ? "auto" : "smooth" });
  }, [messages]);

  // Phones: when the on-screen keyboard opens, shrink the panel to the visible part of the screen
  // so the input and the send button are never hidden behind the keyboard.
  useEffect(() => {
    const panel = panelRef.current;
    const vv = window.visualViewport;
    if (!open || !panel || !vv) return;
    function sync() {
      panel!.style.setProperty("--silo-vv-h", `${vv!.height}px`);
      panel!.style.setProperty("--silo-vv-top", `${vv!.offsetTop}px`);
      const el = threadRef.current;
      if (el && el.dataset.started === "true") el.scrollTop = el.scrollHeight;
    }
    sync();
    vv.addEventListener("resize", sync);
    vv.addEventListener("scroll", sync);
    return () => {
      vv.removeEventListener("resize", sync);
      vv.removeEventListener("scroll", sync);
      panel.style.removeProperty("--silo-vv-h");
      panel.style.removeProperty("--silo-vv-top");
    };
  }, [open]);

  function closeOptions() {
    setOptionsOpen(false);
    // The rest of the panel is switched off while the sheet is open, so wait one frame before giving focus back.
    requestAnimationFrame(() => moreRef.current?.focus({ preventScroll: true }));
  }

  // Sends one question to the existing chatbot service (api.askSilo). If retryId is given, that
  // "could not answer" card is replaced instead of adding the question a second time.
  async function ask(question: string, retryId?: number) {
    const q = question.trim();
    if (!q || pending) return;
    const run = runId.current;
    const pendingId = nextId.current++;
    const userId = retryId === undefined ? nextId.current++ : null;

    setMessages((prev) => {
      const base: Message[] =
        userId === null ? prev.filter((m) => m.id !== retryId) : [...prev, { id: userId, role: "user", text: q }];
      return [...base, { id: pendingId, role: "silo", kind: "pending" }];
    });
    if (retryId === undefined) setDraft("");

    let reply: Message;
    try {
      if (!navigator.onLine) throw new ApiError(0, "offline");
      const result = await api.askSilo(q);
      const text = result.answer?.trim();
      if (!text) throw new Error("empty answer");
      reply = { id: pendingId, role: "silo", kind: "answer", text, topic: result.topic ?? null };
    } catch (err) {
      reply = { id: pendingId, role: "silo", kind: "problem", question: q, ...describeProblem(err) };
    }

    if (run !== runId.current) return; // the chat was cleared while waiting
    setMessages((prev) => prev.map((m) => (m.id === pendingId ? reply : m)));
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (canSend) void ask(draft);
  }

  // "Clear this answer": removes the questions and answers on screen. Nothing else is touched
  // (what is typed in the box, the map, saved reports and places all stay as they are).
  function clearChat() {
    runId.current += 1;
    setMessages([]);
    closeOptions();
  }

  return (
    <section
      ref={panelRef}
      className={`silo-panel${open ? " silo-panel-open" : ""}`}
      role="dialog"
      aria-labelledby="silo-title"
      inert={!open}
    >
      {/* While the options sheet is open, everything behind it is switched off (no tabbing into it). */}
      <div className="silo-main" inert={optionsOpen}>
        <header className="silo-header">
          <SiloAvatar large />
          <div className="silo-header-text">
            <h2 className="silo-title" id="silo-title">
              SILONG Bot Assistant
            </h2>
            <p className="silo-subtitle">One question in, one short answer out.</p>
          </div>
          <div className="silo-header-actions">
            <button
              ref={moreRef}
              type="button"
              className="silo-icon-btn"
              aria-label="Chat options"
              aria-haspopup="dialog"
              onClick={() => setOptionsOpen(true)}
            >
              <Icon name="dots" size={22} />
            </button>
            <button ref={closeRef} type="button" className="silo-icon-btn" aria-label="Close Ask Silo" onClick={onClose}>
              <Icon name="close" size={22} />
            </button>
          </div>
        </header>

        <div className="silo-call">
          <p className="silo-call-text">In danger? Call 911 first.</p>
          <a className="silo-call-btn" href="tel:911" aria-label="Call 911, the national emergency number">
            <Icon name="phone" size={20} />
            <span>Call 911</span>
          </a>
        </div>

        {!online && (
          <div className="silo-offline" role="status">
            <Icon name="wifiOff" size={20} />
            <p>You’re offline. Silo needs the internet to answer.</p>
          </div>
        )}

        <div ref={threadRef} className="silo-thread" data-started={started} role="log" aria-live="polite" aria-relevant="additions">
          {!started && (
            <>
              <div className="silo-row">
                <SiloAvatar />
                <div className="silo-card">
                  <p className="silo-welcome-title">Hello! I’m Silo. How can I help you today?</p>
                  <p className="silo-welcome-text">
                    Ask me one question and I’ll give one short answer from the SILONG guide.
                  </p>
                </div>
              </div>

              <section className="silo-suggest" aria-labelledby="silo-suggest-title">
                <h3 className="silo-suggest-title" id="silo-suggest-title">
                  Try asking
                </h3>
                <ul className="silo-suggest-list">
                  {SUGGESTIONS.map((q) => (
                    <li key={q}>
                      <button type="button" className="silo-suggest-btn" disabled={!online || pending} onClick={() => void ask(q)}>
                        {q}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}

          {messages.map((m) => {
            if (m.role === "user") {
              return (
                <div key={m.id} className="silo-row silo-row-user">
                  <p className="silo-bubble-user">{m.text}</p>
                </div>
              );
            }
            return (
              <div key={m.id} className="silo-row">
                <SiloAvatar />
                {m.kind === "pending" && (
                  <div className="silo-card silo-typing" role="status">
                    <span className="silo-sr">Silo is looking for an answer</span>
                    <span className="silo-dot" aria-hidden="true" />
                    <span className="silo-dot" aria-hidden="true" />
                    <span className="silo-dot" aria-hidden="true" />
                  </div>
                )}
                {m.kind === "answer" && (
                  <div className="silo-card">
                    {m.topic && <span className="silo-topic">{m.topic}</span>}
                    <p className="silo-answer-text">{m.text}</p>
                    {m.topic && <p className="silo-source">From the SILONG guide · {m.topic}</p>}
                  </div>
                )}
                {m.kind === "problem" && (
                  <div className="silo-card">
                    <p className="silo-answer-text">{m.title}</p>
                    <p className="silo-welcome-text">{m.detail}</p>
                    {m.canRetry && (
                      <button type="button" className="silo-retry" disabled={pending || !online} onClick={() => void ask(m.question, m.id)}>
                        <Icon name="refresh" size={18} />
                        <span>Try again</span>
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <form className="silo-composer" onSubmit={onSubmit}>
          <div className="silo-input-wrap">
            <input
              className="silo-input"
              type="text"
              value={draft}
              maxLength={MAX_LENGTH}
              placeholder={online ? (started ? "Ask a new question" : "Ask one question...") : "Ask when you’re back online"}
              aria-label="Your question"
              aria-describedby="silo-counter"
              autoComplete="off"
              enterKeyHint="send"
              disabled={!online}
              onChange={(e) => setDraft(e.target.value)}
            />
            <button type="submit" className="silo-send" aria-label="Send question" disabled={!canSend}>
              <Icon name="send" size={20} />
            </button>
          </div>
          <div className="silo-foot">
            <p className="silo-disclaimer">
              {online ? "AI-generated. Follow official advisories first." : "Call 911 still works without internet."}
            </p>
            {online && (
              <p className="silo-counter" id="silo-counter">
                {draft.length} / {MAX_LENGTH}
              </p>
            )}
          </div>
        </form>
      </div>

      {optionsOpen && (
        <>
          <button type="button" className="silo-backdrop" aria-label="Close chat options" tabIndex={-1} onClick={closeOptions} />
          <div className="silo-sheet" role="dialog" aria-modal="true" aria-labelledby="silo-options-title">
            <button type="button" className="silo-sheet-handle-btn" aria-label="Close chat options" tabIndex={-1} onClick={closeOptions}>
              <span className="silo-sheet-handle" aria-hidden="true" />
            </button>
            <div className="silo-sheet-head">
              <h3 className="silo-sheet-title" id="silo-options-title">
                Chat options
              </h3>
              <button ref={sheetCloseRef} type="button" className="silo-icon-btn silo-icon-btn-soft" aria-label="Close chat options" onClick={closeOptions}>
                <Icon name="close" size={22} />
              </button>
            </div>

            <h4 className="silo-howto-title">How Silo answers</h4>
            <p className="silo-howto-text">
              Silo answers from a checked guide based on official advisories (PAGASA, NDRRMC and your city). It can be
              wrong, so follow official advisories first.
            </p>

            <ul className="silo-menu">
              <li>
                {/* Not wired: there is no wrong-answer endpoint in the project yet, so this does nothing and says so. */}
                <button type="button" className="silo-menu-item" disabled>
                  <Icon name="flag" size={22} />
                  <span>
                    Report a wrong answer
                    <small className="silo-menu-hint">Not available yet</small>
                  </span>
                </button>
              </li>
              <li>
                <button type="button" className="silo-menu-item silo-menu-danger" disabled={!started} onClick={clearChat}>
                  <Icon name="trash" size={22} />
                  <span>Clear this answer</span>
                </button>
              </li>
            </ul>
          </div>
        </>
      )}
    </section>
  );
}