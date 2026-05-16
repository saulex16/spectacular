import type { AuthStatus, Intercept, LoginSession, Message, Session, Subagent } from "./types";

const BASE = "/api";

export async function listSessions(): Promise<Session[]> {
  const r = await fetch(`${BASE}/sessions`);
  if (!r.ok) throw new Error("failed to list sessions");
  return r.json();
}

export async function createSession(cwd?: string): Promise<Session> {
  const r = await fetch(`${BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cwd: cwd ?? "" }),
  });
  if (!r.ok) throw new Error("failed to create session");
  return r.json();
}

export async function deleteSession(id: string): Promise<void> {
  const r = await fetch(`${BASE}/sessions/${id}`, { method: "DELETE" });
  if (!r.ok && r.status !== 204) throw new Error("failed to delete session");
}

export async function listMessages(id: string): Promise<Message[]> {
  const r = await fetch(`${BASE}/sessions/${id}/messages`);
  if (!r.ok) throw new Error("failed to list messages");
  return r.json();
}

export async function listSubagents(id: string): Promise<Subagent[]> {
  const r = await fetch(`${BASE}/sessions/${id}/subagents`);
  if (!r.ok) throw new Error("failed to list subagents");
  return r.json();
}

export async function fetchPendingIntercept(sessionId: string): Promise<Intercept | null> {
  try {
    const r = await fetch(`${BASE}/sessions/${sessionId}/intercept/pending`);
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

export async function resolveIntercept(
  id: string,
  status: "approved" | "rejected",
  prompt?: string,
): Promise<void> {
  await fetch(`${BASE}/intercept/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, ...(prompt !== undefined ? { prompt } : {}) }),
  });
}

export function openSocket(id: string): WebSocket {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return new WebSocket(`${proto}://${location.host}/ws/sessions/${id}`);
}

export async function fetchAuthStatus(): Promise<AuthStatus> {
  const r = await fetch(`${BASE}/auth/status`);
  if (!r.ok) throw new Error("failed to fetch auth status");
  return r.json();
}

export async function startLogin(): Promise<LoginSession> {
  const r = await fetch(`${BASE}/auth/login/start`, { method: "POST" });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? "failed to start login");
  }
  return r.json();
}

export async function pollLogin(loginId: string): Promise<LoginSession> {
  const r = await fetch(`${BASE}/auth/login/${loginId}`);
  if (!r.ok) throw new Error("login session not found");
  return r.json();
}

export async function submitLoginCode(loginId: string, code: string): Promise<LoginSession> {
  const r = await fetch(`${BASE}/auth/login/${loginId}/code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? "failed to submit code");
  }
  return r.json();
}

export async function cancelLogin(loginId: string): Promise<void> {
  await fetch(`${BASE}/auth/login/${loginId}`, { method: "DELETE" });
}
