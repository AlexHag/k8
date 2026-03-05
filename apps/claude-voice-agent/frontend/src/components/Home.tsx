import { useState, useRef, useEffect, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createSession } from "../api.ts";

type Step = "idle" | "title" | "mode";
type Mode = "openai" | "claude_code";

export function Home() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("idle");
  const [title, setTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (step === "title") inputRef.current?.focus();
  }, [step]);

  const handleTitleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setStep("mode");
  };

  const handleModeSelect = async (mode: Mode) => {
    if (creating) return;
    setCreating(true);
    try {
      const session = await createSession(title.trim(), mode);
      navigate(`/chat/${session.id}`);
    } catch (err) {
      console.error("Failed to create session:", err);
      setCreating(false);
    }
  };

  const handleCancel = () => {
    setStep("idle");
    setTitle("");
  };

  return (
    <div className="page-container">
      <div className="home-content">
        <h1 className="home-title">Agent-M</h1>
        <p className="home-subtitle">&gt; Multi Agent Orchestration Tool</p>

        {step === "idle" && (
          <div className="home-actions">
            <button
              type="button"
              className="home-btn"
              onClick={() => setStep("title")}
            >
              [NEW CHAT]
            </button>
            <button
              type="button"
              className="home-btn"
              onClick={() => navigate("/history")}
            >
              [HISTORY]
            </button>
          </div>
        )}

        {step === "title" && (
          <form className="home-form" onSubmit={handleTitleSubmit}>
            <p className="home-prompt">&gt; Enter session title:</p>
            <div className="home-input-row">
              <span className="input-prompt">$</span>
              <input
                ref={inputRef}
                type="text"
                className="chat-input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="My session..."
                autoFocus
              />
            </div>
            <div className="home-form-actions">
              <button type="submit" className="home-btn" disabled={!title.trim()}>
                [CONFIRM]
              </button>
              <button type="button" className="home-btn home-btn-dim" onClick={handleCancel}>
                [CANCEL]
              </button>
            </div>
          </form>
        )}

        {step === "mode" && (
          <div className="home-mode-select">
            <p className="home-prompt">
              &gt; Session: <strong>{title}</strong>
            </p>
            <p className="home-prompt">&gt; Select mode:</p>
            <div className="home-actions">
              <button
                type="button"
                className="home-btn"
                disabled={creating}
                onClick={() => handleModeSelect("openai")}
              >
                [OPENAI]
              </button>
              <button
                type="button"
                className="home-btn"
                disabled={creating}
                onClick={() => handleModeSelect("claude_code")}
              >
                [CLAUDE CODE]
              </button>
            </div>
            <button
              type="button"
              className="home-btn home-btn-dim"
              onClick={() => setStep("title")}
              disabled={creating}
            >
              [BACK]
            </button>
            {creating && <p className="home-status">&gt; Creating session...</p>}
          </div>
        )}
      </div>
    </div>
  );
}
