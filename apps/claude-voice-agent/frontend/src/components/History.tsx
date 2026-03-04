import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { listSessions, deleteSession, type SessionSummary } from "../api.ts";

export function History() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchSessions = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listSessions();
      setSessions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sessions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleDelete = async (id: string) => {
    if (deleting) return;
    setDeleting(true);
    try {
      await deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      setConfirmDeleteId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete session");
    } finally {
      setDeleting(false);
    }
  };

  const modeLabel = (mode: string) =>
    mode === "claude_code" ? "CLAUDE" : "OPENAI";

  return (
    <div className="page-container">
      <div className="history-content">
        <header className="history-header">
          <h1 className="home-title">SESSION HISTORY</h1>
          <button
            type="button"
            className="home-btn"
            onClick={() => navigate("/")}
          >
            [HOME]
          </button>
        </header>

        {loading && <p className="home-subtitle">&gt; Loading sessions...</p>}
        {error && <p className="error-text">! {error}</p>}

        {!loading && sessions.length === 0 && (
          <p className="home-subtitle">&gt; No sessions found.</p>
        )}

        {!loading && sessions.length > 0 && (
          <div className="session-list">
            {sessions.map((s) => (
              <div key={s.id} className="session-item">
                <div
                  className="session-info"
                  onClick={() => navigate(`/chat/${s.id}`)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") navigate(`/chat/${s.id}`);
                  }}
                >
                  <span className="session-title">{s.title}</span>
                  <span className={`session-mode session-mode-${s.mode}`}>
                    [{modeLabel(s.mode)}]
                  </span>
                </div>

                {confirmDeleteId === s.id ? (
                  <div className="session-confirm-delete">
                    <span className="confirm-text">Delete?</span>
                    <button
                      type="button"
                      className="session-btn session-btn-danger"
                      disabled={deleting}
                      onClick={() => handleDelete(s.id)}
                    >
                      [Y]
                    </button>
                    <button
                      type="button"
                      className="session-btn"
                      disabled={deleting}
                      onClick={() => setConfirmDeleteId(null)}
                    >
                      [N]
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="session-btn session-btn-danger"
                    onClick={() => setConfirmDeleteId(s.id)}
                  >
                    [DEL]
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
