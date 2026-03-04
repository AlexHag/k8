import { useCallback, useEffect, useRef, useState } from "react";

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

export interface AudioDelta {
  type: "audio_delta";
  data?: string;
  transcript?: string;
}

export interface ToolUseMessage {
  type: "tool_use";
  tool: string;
  input: Record<string, unknown>;
}

export interface ToolResultMessage {
  type: "tool_result";
  tool_use_id: string;
  content: string;
  is_error?: boolean;
}

export interface DoneMessage {
  type: "done";
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

type ServerMessage =
  | AudioDelta
  | ToolUseMessage
  | ToolResultMessage
  | DoneMessage
  | ErrorMessage;

interface UseWebSocketOptions {
  url: string | null;
  onAudioDelta: (delta: AudioDelta) => void;
  onToolUse: (msg: ToolUseMessage) => void;
  onToolResult: (msg: ToolResultMessage) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

export function useWebSocket({
  url,
  onAudioDelta,
  onToolUse,
  onToolResult,
  onDone,
  onError,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const callbacksRef = useRef({
    onAudioDelta,
    onToolUse,
    onToolResult,
    onDone,
    onError,
  });
  callbacksRef.current = {
    onAudioDelta,
    onToolUse,
    onToolResult,
    onDone,
    onError,
  };

  useEffect(() => {
    if (!url) {
      setStatus("disconnected");
      return;
    }

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setStatus("connected");

    ws.onmessage = (event) => {
      const msg: ServerMessage = JSON.parse(event.data);
      switch (msg.type) {
        case "audio_delta":
          callbacksRef.current.onAudioDelta(msg);
          break;
        case "tool_use":
          callbacksRef.current.onToolUse(msg);
          break;
        case "tool_result":
          callbacksRef.current.onToolResult(msg);
          break;
        case "done":
          callbacksRef.current.onDone();
          break;
        case "error":
          callbacksRef.current.onError(msg.message);
          break;
      }
    };

    ws.onclose = () => setStatus("disconnected");
    ws.onerror = () => setStatus("disconnected");

    setStatus("connecting");

    return () => {
      ws.close();
    };
  }, [url]);

  const send = useCallback((text: string, mode: string = "openai") => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "message", text, mode }));
    }
  }, []);

  return { send, status };
}
