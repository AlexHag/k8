import {
  useState,
  useRef,
  useEffect,
  useCallback,
  type FormEvent,
} from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  useWebSocket,
  type AudioDelta,
  type TextDelta,
  type ToolUseMessage,
  type ToolResultMessage,
} from "../hooks/useWebSocket.ts";
import { useAudioPlayer } from "../hooks/useAudioPlayer.ts";
import { getSession, sendMessage, updateSession, type SessionWithMessages } from "../api.ts";

interface ChatMessage {
  role: "user" | "assistant" | "error" | "tool_use" | "tool_result";
  text: string;
  tool?: string;
  toolInput?: Record<string, unknown>;
  isError?: boolean;
}

const WS_BASE =
  import.meta.env.VITE_WS_URL ??
  `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws`;

function formatToolInput(input: Record<string, unknown>): string {
  if ("command" in input && typeof input.command === "string") {
    return input.command;
  }
  if ("file_path" in input) {
    return String(input.file_path);
  }
  if ("pattern" in input) {
    return String(input.pattern);
  }
  return JSON.stringify(input, null, 2);
}

function truncate(text: string, max = 500): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "\n... (truncated)";
}

// ---------------------------------------------------------------------------
// AudioVisualizer – shown above the chat input while the agent is speaking
// ---------------------------------------------------------------------------
function AudioVisualizer({
  analyserRef,
  onStop,
}: {
  analyserRef: { current: AnalyserNode | null };
  onStop: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Keep the canvas pixel buffer in sync with its CSS layout size
    const syncSize = () => {
      canvas.width = canvas.clientWidth;
      canvas.height = canvas.clientHeight;
    };
    syncSize();
    const ro = new ResizeObserver(syncSize);
    ro.observe(canvas);

    const draw = () => {
      animFrameRef.current = requestAnimationFrame(draw);

      const w = canvas.width;
      const h = canvas.height;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      ctx.clearRect(0, 0, w, h);

      const analyser = analyserRef.current;
      if (!analyser) {
        // Flat idle line
        ctx.strokeStyle = "rgba(0,204,51,0.4)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, h / 2);
        ctx.lineTo(w, h / 2);
        ctx.stroke();
        return;
      }

      const bufferLength = analyser.frequencyBinCount; // fftSize / 2 = 64
      const dataArray = new Uint8Array(bufferLength);
      analyser.getByteFrequencyData(dataArray);

      // Draw centred frequency bars – use lower 60 % of spectrum (voice range)
      const barCount = 40;
      const usableBins = Math.floor(bufferLength * 0.6);
      const gap = 2;
      const barWidth = Math.max(1, (w - gap * (barCount - 1)) / barCount);

      for (let i = 0; i < barCount; i++) {
        const binIdx = Math.floor((i / barCount) * usableBins);
        const value = dataArray[binIdx];
        const barH = Math.max(2, (value / 255) * h * 0.9);
        const x = i * (barWidth + gap);
        const y = (h - barH) / 2;

        // Brightness scales with amplitude
        const alpha = 0.35 + (value / 255) * 0.65;
        ctx.fillStyle = `rgba(0, 255, 65, ${alpha.toFixed(2)})`;
        ctx.fillRect(x, y, barWidth, barH);
      }
    };

    draw();

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      ro.disconnect();
    };
  }, [analyserRef]);

  return (
    <div className="audio-visualizer">
      <span className="audio-visualizer-label">◉ AUDIO</span>
      <canvas ref={canvasRef} className="audio-visualizer-canvas" />
      <button
        type="button"
        className="audio-stop-btn"
        onClick={onStop}
        title="Stop audio playback"
      >
        [STOP]
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------
export function Chat() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionData, setSessionData] = useState<SessionWithMessages | null>(
    null,
  );
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showTools, setShowTools] = useState(true);
  const [voiceMode, setVoiceMode] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const {
    playChunk,
    reset: resetAudio,
    ensureContext,
    analyserRef,
    stopAudio,
  } = useAudioPlayer();

  const mode = sessionData?.mode ?? "openai";

  const wsUrl =
    sessionData && sessionId ? `${WS_BASE}?session_id=${sessionId}` : null;

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(scrollToBottom, [messages, scrollToBottom]);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;

    (async () => {
      try {
        const data = await getSession(sessionId);
        if (cancelled) return;
        setSessionData(data);
        setVoiceMode(data.voice_mode);

        const loaded: ChatMessage[] = data.messages.map((m) => {
          if (m.role === "tool_use") {
            const toolInput = m.tool_input
              ? (JSON.parse(m.tool_input) as Record<string, unknown>)
              : {};
            return {
              role: "tool_use" as const,
              text: formatToolInput(toolInput),
              tool: m.tool_name ?? undefined,
              toolInput,
            };
          }
          if (m.role === "tool_result") {
            return {
              role: "tool_result" as const,
              text: m.text,
              isError: m.is_error,
            };
          }
          return {
            role: m.role as ChatMessage["role"],
            text: m.text,
          };
        });
        setMessages(loaded);
      } catch (err) {
        if (!cancelled) {
          setLoadError(
            err instanceof Error ? err.message : "Failed to load session",
          );
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const onAudioDelta = useCallback(
    (delta: AudioDelta) => {
      if (delta.transcript) {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === "assistant") {
            updated[updated.length - 1] = {
              ...last,
              text: last.text + delta.transcript,
            };
          } else {
            updated.push({ role: "assistant", text: delta.transcript! });
          }
          return updated;
        });
      }

      if (delta.data) {
        playChunk(delta.data);
      }
    },
    [playChunk],
  );

  const onTextDelta = useCallback((delta: TextDelta) => {
    setMessages((prev) => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      if (last && last.role === "assistant") {
        updated[updated.length - 1] = {
          ...last,
          text: last.text + delta.text,
        };
      } else {
        updated.push({ role: "assistant", text: delta.text });
      }
      return updated;
    });
  }, []);

  const onToolUse = useCallback((msg: ToolUseMessage) => {
    setMessages((prev) => [
      ...prev,
      {
        role: "tool_use",
        text: formatToolInput(msg.input),
        tool: msg.tool,
        toolInput: msg.input,
      },
    ]);
  }, []);

  const onToolResult = useCallback((msg: ToolResultMessage) => {
    setMessages((prev) => [
      ...prev,
      {
        role: "tool_result",
        text: msg.content,
        isError: msg.is_error,
      },
    ]);
  }, []);

  const onDone = useCallback(() => {
    setIsStreaming(false);
    inputRef.current?.focus();
  }, []);

  const onError = useCallback((message: string) => {
    setMessages((prev) => [...prev, { role: "error", text: message }]);
    setIsStreaming(false);
  }, []);

  const { status } = useWebSocket({
    url: wsUrl,
    onAudioDelta,
    onTextDelta,
    onToolUse,
    onToolResult,
    onDone,
    onError,
  });

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || isStreaming || status !== "connected" || !sessionId) return;

    if (voiceMode) {
      ensureContext();
      resetAudio();
    }

    setMessages((prev) => [
      ...prev,
      { role: "user", text },
      { role: "assistant", text: "" },
    ]);
    setInput("");
    setIsStreaming(true);

    try {
      await sendMessage(sessionId, text);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to send message";
      setMessages((prev) => [...prev, { role: "error", text: message }]);
      setIsStreaming(false);
    }
  };

  // Stop audio immediately and dismiss the visualizer
  const handleStopAudio = useCallback(() => {
    stopAudio();
    setIsStreaming(false);
    inputRef.current?.focus();
  }, [stopAudio]);

  const renderPrefix = (role: ChatMessage["role"], tool?: string) => {
    switch (role) {
      case "user":
        return "$ ";
      case "assistant":
        return "> ";
      case "tool_use":
        return `[${tool ?? "TOOL"}] `;
      case "tool_result":
        return "  => ";
      case "error":
        return "! ";
    }
  };

  if (loadError) {
    return (
      <div className="page-container">
        <div className="home-content">
          <p className="error-text">! {loadError}</p>
          <button
            type="button"
            className="home-btn"
            onClick={() => navigate("/")}
          >
            [HOME]
          </button>
        </div>
      </div>
    );
  }

  if (!sessionData) {
    return (
      <div className="page-container">
        <div className="home-content">
          <p className="home-subtitle">&gt; Loading session...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-container">
      <header className="chat-header">
        <button
          type="button"
          className="nav-btn"
          onClick={() => navigate("/")}
          title="Back to home"
        >
          [HOME]
        </button>
        <span className="header-title">{sessionData.title}</span>
        <span className={`mode-badge mode-badge-${mode}`}>
          {mode === "openai" ? "OPENAI" : "CLAUDE CODE"}
        </span>
        {mode === "claude_code" && (
          <button
            type="button"
            className={`tool-toggle-btn ${showTools ? "active" : ""}`}
            onClick={() => setShowTools((v) => !v)}
            title={showTools ? "Hide tool usage" : "Show tool usage"}
          >
            {showTools ? "[TOOLS ON]" : "[TOOLS OFF]"}
          </button>
        )}
        <span className={`status-indicator ${status}`}>
          [{status.toUpperCase()}]
        </span>
      </header>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="welcome-message">
            <p>{">"} Session initialized. Ready for input.</p>
            <p>{">"} Type a message and press ENTER to begin.</p>
            <p>
              {">"} Mode:{" "}
              <strong>{mode === "openai" ? "OpenAI Audio" : "Claude Code"}</strong>
            </p>
          </div>
        )}

        {messages.map((msg, i) => {
          if (
            !showTools &&
            (msg.role === "tool_use" || msg.role === "tool_result")
          )
            return null;

          return (
            <div
              key={i}
              className={`message message-${msg.role}${msg.isError ? " message-error" : ""}`}
            >
              <span className="message-prefix">
                {renderPrefix(msg.role, msg.tool)}
              </span>
              <span className="message-text">
                {msg.role === "tool_result" ? truncate(msg.text) : msg.text}
                {msg.role === "assistant" &&
                  isStreaming &&
                  i === messages.length - 1 && (
                    <span className="cursor-blink">_</span>
                  )}
              </span>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {/* Audio visualizer – always visible */}
      <AudioVisualizer analyserRef={analyserRef} onStop={handleStopAudio} />

      <div className="voice-toggle-row">
        <button
          type="button"
          className={`voice-toggle-btn ${voiceMode ? "active" : ""}`}
          onClick={() => {
            const next = !voiceMode;
            setVoiceMode(next);
            if (sessionId) {
              updateSession(sessionId, { voice_mode: next }).catch(() =>
                setVoiceMode(voiceMode),
              );
            }
          }}
          title={voiceMode ? "Disable voice mode" : "Enable voice mode"}
        >
          {voiceMode ? "[VOICE ON]" : "[VOICE OFF]"}
        </button>
      </div>

      <form className="chat-input-form" onSubmit={handleSubmit}>
        <span className="input-prompt">$</span>
        <input
          ref={inputRef}
          type="text"
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            status !== "connected"
              ? "Connecting..."
              : isStreaming
                ? "Receiving response..."
                : "Type your message..."
          }
          disabled={status !== "connected" || isStreaming}
          autoFocus
        />
      </form>
    </div>
  );
}
