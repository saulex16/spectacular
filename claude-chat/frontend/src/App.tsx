import { useEffect, useRef, useState } from "react";
import {
  createSession,
  deleteSession,
  fetchPendingIntercept,
  listMessages,
  listSessions,
  listSubagents,
  openSocket,
  resolveIntercept,
} from "./api";
import { MarkdownMessage } from "./MarkdownMessage";
import type { Intercept, Message, Session, Subagent } from "./types";

type WsState = "closed" | "connecting" | "open";

type StreamEvent = {
  type: string;
  message?: { content?: unknown };
  [k: string]: unknown;
};

function extractStreamDelta(ev: StreamEvent): string {
  if (ev.type !== "stream_event") return "";
  const inner = (ev as { event?: { type?: string; delta?: { type?: string; text?: string } } }).event;
  if (!inner || inner.type !== "content_block_delta") return "";
  const delta = inner.delta;
  if (!delta || delta.type !== "text_delta") return "";
  return delta.text ?? "";
}

type ToolUse = { name: string; input: unknown };

function extractToolUses(ev: StreamEvent): ToolUse[] {
  if (ev.type !== "assistant" || !ev.message) return [];
  const content = (ev.message as { content?: unknown }).content;
  if (!Array.isArray(content)) return [];
  return content
    .filter((b: { type?: string }) => b.type === "tool_use")
    .map((b: { name?: string; input?: unknown }) => ({
      name: b.name ?? "tool",
      input: b.input,
    }));
}

function toolDetail(name: string, input: unknown): string {
  if (!input || typeof input !== "object") return "";
  const inp = input as Record<string, unknown>;
  switch (name) {
    case "Read":      return String(inp.file_path ?? "");
    case "Write":     return String(inp.file_path ?? "");
    case "Edit":      return String(inp.file_path ?? "");
    case "Bash":      return String(inp.command ?? "").split("\n")[0].slice(0, 120);
    case "Glob":      return String(inp.pattern ?? "");
    case "Grep":      return `${inp.pattern ?? ""} ${inp.path ?? ""}`.trim();
    case "WebFetch":  return String(inp.url ?? "").slice(0, 100);
    case "WebSearch": return String(inp.query ?? "");
    default: {
      const first = Object.values(inp)[0];
      return first != null ? String(first).slice(0, 100) : "";
    }
  }
}

function isToolResult(ev: StreamEvent): boolean {
  if (ev.type !== "user" || !ev.message) return false;
  const content = (ev.message as { content?: unknown }).content;
  if (!Array.isArray(content)) return false;
  return content.some((b: { type?: string }) => b.type === "tool_result");
}

type ActiveTab = { kind: "parent" } | { kind: "subagent"; id: number };

export function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [subagents, setSubagents] = useState<Subagent[]>([]);
  const [activeTab, setActiveTab] = useState<ActiveTab>({ kind: "parent" });
  // Live per-subagent streaming state (ephemeral, not persisted)
  const [subagentStreams, setSubagentStreams] = useState<
    Record<number, { text: string; events: string[] }>
  >({});
  const [intercept, setIntercept] = useState<Intercept | null>(null);
  const [interceptPrompt, setInterceptPrompt] = useState("");
  const [streaming, setStreaming] = useState("");
  const [events, setEvents] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [wsState, setWsState] = useState<WsState>("closed");
  const wsRef = useRef<WebSocket | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  // Buffered streaming: deltas land in the ref, a rAF callback flushes them
  // into React state at most once per animation frame to avoid render storms.
  const streamingBufRef = useRef("");
  const streamingFlushScheduledRef = useRef(false);
  // Per-subagent streaming buffers (keyed by subagent id)
  const subagentBufRef = useRef<Record<number, string>>({});

  function flushStreaming() {
    setStreaming(streamingBufRef.current);
    streamingFlushScheduledRef.current = false;
  }

  function appendStreaming(delta: string) {
    streamingBufRef.current += delta;
    if (!streamingFlushScheduledRef.current) {
      streamingFlushScheduledRef.current = true;
      requestAnimationFrame(flushStreaming);
    }
  }

  function resetStreaming() {
    streamingBufRef.current = "";
    streamingFlushScheduledRef.current = false;
    setStreaming("");
  }

  useEffect(() => {
    void refresh();
  }, []);

  // Poll for pending intercepts while a turn is in progress.
  useEffect(() => {
    if (!activeId || !busy) {
      setIntercept(null);
      return;
    }
    let alive = true;
    const poll = async () => {
      while (alive) {
        const pending = await fetchPendingIntercept(activeId);
        if (!alive) break;
        if (pending && pending.status === "pending") {
          setIntercept((cur) => (cur?.id === pending.id ? cur : pending));
          setInterceptPrompt(String(pending.original_input.prompt ?? ""));
        } else {
          setIntercept(null);
        }
        await new Promise((r) => setTimeout(r, 600));
      }
    };
    void poll();
    return () => { alive = false; };
  }, [activeId, busy]);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight });
  }, [messages, streaming, events]);

  useEffect(() => {
    if (!activeId) {
      wsRef.current?.close();
      wsRef.current = null;
      setMessages([]);
      setSubagents([]);
      setSubagentStreams({});
      subagentBufRef.current = {};
      setActiveTab({ kind: "parent" });
      resetStreaming();
      setEvents([]);
      setBusy(false);
      setInput("");
      setWsState("closed");
      return;
    }

    // Reset all per-session state immediately.
    setMessages([]);
    setSubagents([]);
    setSubagentStreams({});
    subagentBufRef.current = {};
    setActiveTab({ kind: "parent" });
    resetStreaming();
    setEvents([]);
    setBusy(false);
    setInput("");
    setWsState("connecting");

    void loadMessages(activeId);
    void loadSubagents(activeId);
    const ws = openSocket(activeId);
    wsRef.current = ws;
    let cancelled = false;

    ws.onopen = () => {
      if (cancelled) return;
      setWsState("open");
    };

    ws.onmessage = (e) => {
      if (cancelled) return;
      const ev: StreamEvent = JSON.parse(e.data);

      // Protocol events from our backend.
      if (ev.type === "user_message_saved" || ev.type === "ready") return;
      if (ev.type === "subagent_started" || ev.type === "subagent_completed") {
        const sub = (ev as { subagent?: Subagent }).subagent;
        if (sub) {
          setSubagents((cur) => {
            const idx = cur.findIndex((s) => s.id === sub.id);
            if (idx === -1) return [...cur, sub];
            const next = cur.slice();
            next[idx] = sub;
            return next;
          });
        }
        return;
      }
      if (ev.type === "subagent_event") {
        const subId = (ev as { subagent_id?: number }).subagent_id;
        const inner = (ev as { event?: StreamEvent }).event;
        if (subId == null || !inner) return;

        const delta = extractStreamDelta(inner);
        if (delta) {
          if (!subagentBufRef.current[subId]) subagentBufRef.current[subId] = "";
          subagentBufRef.current[subId] += delta;
          requestAnimationFrame(() => {
            const text = subagentBufRef.current[subId] ?? "";
            setSubagentStreams((cur) => ({
              ...cur,
              [subId]: { text, events: cur[subId]?.events ?? [] },
            }));
          });
          return;
        }
        if (inner.type === "assistant") {
          const tools = extractToolUses(inner);
          const entries = tools
            .filter((t) => t.name !== "Task" && t.name !== "Agent")
            .map((t) => {
              const detail = toolDetail(t.name, t.input);
              return detail ? `🔧 ${t.name}  ${detail}` : `🔧 ${t.name}`;
            });
          if (entries.length > 0) {
            setSubagentStreams((cur) => ({
              ...cur,
              [subId]: {
                text: cur[subId]?.text ?? "",
                events: [...(cur[subId]?.events ?? []), ...entries],
              },
            }));
          }
        }
        return;
      }
      if (ev.type === "turn_complete") {
        setBusy(false);
        resetStreaming();
        setEvents([]);
        void loadMessages(activeId);
        void refresh();
        return;
      }
      if (ev.type === "process_died") {
        setBusy(false);
        resetStreaming();
        setEvents((es) => [...es, "[process died — next message will respawn]"]);
        return;
      }

      // CLI meta events: noisy, hide from chat view.
      if (ev.type === "system" || ev.type === "result" || ev.type === "raw") {
        return;
      }

      // Tool results come paired with the assistant follow-up; hide them.
      if (isToolResult(ev)) return;

      // Token-by-token streaming deltas — buffered via rAF.
      const delta = extractStreamDelta(ev);
      if (delta) {
        appendStreaming(delta);
        return;
      }

      // Full `assistant` event arrives at the end of each message — text is
      // already accumulated via deltas, but tool_use entries appear here.
      if (ev.type === "assistant") {
        const tools = extractToolUses(ev);
        const regular: string[] = [];
        let subagentLaunches = 0;
        for (const t of tools) {
          if (t.name === "Task" || t.name === "Agent") {
            subagentLaunches++;
          } else {
            regular.push(`🔧 ${t.name}`);
          }
        }
        const next: string[] = [];
        if (subagentLaunches > 0) {
          next.push(`🤖 subagent launched${subagentLaunches > 1 ? ` ×${subagentLaunches}` : ""}`);
        }
        // Only show regular tools when no subagent is running — otherwise the
        // flood of Bash/Read calls from inside the subagent pollutes the parent.
        if (subagents.length === 0 && regular.length > 0) {
          next.push(...regular);
        }
        if (next.length > 0) {
          setEvents((es) => [...es, ...next]);
        }
      }
    };

    ws.onclose = () => {
      if (cancelled) return;
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
      setWsState("closed");
      setBusy(false);
    };

    ws.onerror = () => {
      if (cancelled) return;
      setWsState("closed");
      setBusy(false);
    };

    return () => {
      cancelled = true;
      ws.close();
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
    };
  }, [activeId]);

  async function refresh() {
    setSessions(await listSessions());
  }

  async function loadMessages(id: string) {
    setMessages(await listMessages(id));
  }

  async function loadSubagents(id: string) {
    setSubagents(await listSubagents(id));
  }

  async function onNewSession() {
    const s = await createSession();
    await refresh();
    setActiveId(s.id);
  }

  async function onDelete(id: string) {
    await deleteSession(id);
    if (activeId === id) setActiveId(null);
    await refresh();
  }

  function onSend() {
    const ws = wsRef.current;
    const text = input.trim();
    if (!text || busy || wsState !== "open" || !ws) return;
    ws.send(JSON.stringify({ prompt: text }));
    // Optimistic append: show the user's message immediately. It will be replaced
    // by the canonical row from the DB when turn_complete triggers loadMessages.
    setMessages((ms) => [
      ...ms,
      {
        id: -Date.now(),
        role: "user",
        content: text,
        created_at: new Date().toISOString(),
      },
    ]);
    setBusy(true);
    setInput("");
  }

  async function onApproveIntercept() {
    if (!intercept) return;
    await resolveIntercept(intercept.id, "approved", interceptPrompt);
    setIntercept(null);
  }

  async function onRejectIntercept() {
    if (!intercept) return;
    await resolveIntercept(intercept.id, "rejected");
    setIntercept(null);
  }

  const onParentTab = activeTab.kind === "parent";
  const activeSubagent =
    activeTab.kind === "subagent"
      ? subagents.find((s) => s.id === activeTab.id) ?? null
      : null;
  const canSend =
    !!activeId &&
    onParentTab &&
    wsState === "open" &&
    !busy &&
    input.trim().length > 0;
  const sendDisabled = !activeId || !onParentTab || wsState !== "open" || busy;

  return (
    <div className="app">
      <aside className="sidebar">
        <header>
          <h1>Sessions</h1>
          <button className="btn" onClick={onNewSession}>+ New</button>
        </header>
        <div className="session-list">
          {sessions.length === 0 && (
            <div style={{ padding: 16, color: "var(--muted)", fontSize: 13 }}>
              No sessions yet
            </div>
          )}
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`session-item ${activeId === s.id ? "active" : ""}`}
              onClick={() => setActiveId(s.id)}
            >
              <div className="title">
                <div>{s.title}</div>
                <div className="meta">{new Date(s.updated_at).toLocaleString()}</div>
              </div>
              <button
                className="btn danger"
                onClick={(e) => {
                  e.stopPropagation();
                  void onDelete(s.id);
                }}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </aside>

      <main className="chat">
        {!activeId ? (
          <div className="empty">Select or create a session</div>
        ) : (
          <>
            <header>
              <span>session {activeId.slice(0, 8)}…</span>
              <span className={`ws-pill ws-${wsState}`}>{wsState}</span>
            </header>
            <div className="tabs">
              <button
                className={`tab ${onParentTab ? "active" : ""}`}
                onClick={() => setActiveTab({ kind: "parent" })}
              >
                parent
              </button>
              {subagents.map((s) => (
                <button
                  key={s.id}
                  className={`tab ${
                    activeTab.kind === "subagent" && activeTab.id === s.id
                      ? "active"
                      : ""
                  }`}
                  onClick={() => setActiveTab({ kind: "subagent", id: s.id })}
                  title={s.subagent_type || "subagent"}
                >
                  <span className={`tab-dot status-${s.status}`} />
                  {s.name || "subagent"}
                </button>
              ))}
            </div>
            {onParentTab ? (
              <div className="messages" ref={scrollerRef}>
                {messages.map((m) => (
                  <div key={m.id} className={`msg ${m.role}`}>
                    <MarkdownMessage content={m.content} />
                  </div>
                ))}
                {events.map((e, i) => (
                  <div key={`ev-${i}`} className="events">{e}</div>
                ))}
                {streaming && (
                  <div className="msg assistant">
                    <MarkdownMessage content={streaming} />
                  </div>
                )}
                {busy && !streaming && events.length === 0 && (
                  <div className="msg system">claude is thinking…</div>
                )}
              </div>
            ) : activeSubagent ? (
              <div className="messages">
                <div className="subagent-meta">
                  <span className={`status-pill status-${activeSubagent.status}`}>
                    {activeSubagent.status}
                  </span>
                  {activeSubagent.subagent_type && (
                    <span className="subagent-type">
                      type: {activeSubagent.subagent_type}
                    </span>
                  )}
                </div>
                <div className="msg user">
                  <MarkdownMessage content={activeSubagent.prompt} />
                </div>
                {(() => {
                  const stream = subagentStreams[activeSubagent.id];
                  const liveEvents = stream?.events ?? [];
                  const liveText = stream?.text ?? "";
                  return (
                    <>
                      {liveEvents.map((e, i) => (
                        <div key={`sev-${i}`} className="events">{e}</div>
                      ))}
                      {liveText && (
                        <div className="msg assistant">
                          <MarkdownMessage content={liveText} />
                        </div>
                      )}
                      {activeSubagent.status === "running" && !liveText && liveEvents.length === 0 && (
                        <div className="msg system">subagent running…</div>
                      )}
                      {activeSubagent.status !== "running" && activeSubagent.result && (
                        <div className="msg assistant">
                          <MarkdownMessage content={activeSubagent.result} />
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            ) : (
              <div className="empty">subagent not found</div>
            )}
            <div className="composer">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  !onParentTab
                    ? "subagents are read-only"
                    : wsState === "connecting"
                    ? "connecting…"
                    : wsState === "closed"
                    ? "disconnected — reopen the session"
                    : "Message claude…"
                }
                disabled={!onParentTab || wsState !== "open"}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    if (canSend) onSend();
                  }
                }}
              />
              <button className="btn" onClick={onSend} disabled={sendDisabled}>
                {busy ? "…" : "Send"}
              </button>
            </div>
          </>
        )}
      </main>
      {intercept && (
        <div className="intercept-overlay">
          <div className="intercept-modal">
            <div className="intercept-header">
              <span className="intercept-badge">🤖 subagent intercept</span>
              <span className="intercept-tool">{intercept.tool_name}</span>
            </div>
            <p className="intercept-label">Prompt sent to subagent — edit before launching:</p>
            <textarea
              className="intercept-textarea"
              value={interceptPrompt}
              onChange={(e) => setInterceptPrompt(e.target.value)}
              rows={10}
            />
            <div className="intercept-actions">
              <button className="btn" onClick={onApproveIntercept}>
                Launch
              </button>
              <button
                className="btn"
                style={{ background: "transparent", color: "#f87171", border: "1px solid #7f1d1d" }}
                onClick={onRejectIntercept}
              >
                Block
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

