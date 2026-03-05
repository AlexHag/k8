const API_BASE = 'http://localhost:5000';
  // import.meta.env.VITE_API_URL ?? `${window.location.origin}`;

export interface SessionSummary {
  id: string;
  title: string;
  mode: "openai" | "claude_code";
  claude_session_id: string | null;
  voice_mode: boolean;
  created_at: string;
  updated_at: string;
}

export interface MessageData {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "tool_use" | "tool_result" | "error";
  text: string;
  tool_name: string | null;
  tool_input: string | null;
  is_error: boolean;
  created_at: string;
  sequence: number;
}

export interface SessionWithMessages extends SessionSummary {
  messages: MessageData[];
}

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function createSession(
  title: string,
  mode: "openai" | "claude_code",
): Promise<SessionSummary> {
  return request<SessionSummary>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title, mode }),
  });
}

export function listSessions(): Promise<SessionSummary[]> {
  return request<SessionSummary[]>("/api/sessions");
}

export function getSession(id: string): Promise<SessionWithMessages> {
  return request<SessionWithMessages>(`/api/sessions/${id}`);
}

export function updateSession(
  id: string,
  fields: { title?: string; voice_mode?: boolean },
): Promise<SessionSummary> {
  return request<SessionSummary>(`/api/sessions/${id}`, {
    method: "PATCH",
    body: JSON.stringify(fields),
  });
}

export function deleteSession(id: string): Promise<void> {
  return request<void>(`/api/sessions/${id}`, { method: "DELETE" });
}

export interface SendMessageResponse {
  message_id: string;
  session: SessionSummary;
}

export function sendMessage(
  sessionId: string,
  text: string,
): Promise<SendMessageResponse> {
  return request<SendMessageResponse>(`/api/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}
