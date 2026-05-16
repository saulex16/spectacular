import type {
  Intercept,
  Message,
  ModelOption,
  ProviderId,
  ProviderSettings,
  Session,
  Subagent,
} from "./types";

const BASE = "/api";

export async function listSessions(): Promise<Session[]> {
  const r = await fetch(`${BASE}/sessions`);
  if (!r.ok) throw new Error("failed to list sessions");
  return r.json();
}

export type CreateSessionOptions = {
  cwd?: string;
  provider?: ProviderId;
  model?: string;
};

export async function createSession(opts: CreateSessionOptions = {}): Promise<Session> {
  const r = await fetch(`${BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      cwd: opts.cwd ?? "",
      provider: opts.provider ?? "claude_cli",
      model: opts.model ?? "",
    }),
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

export async function getProviderSettings(): Promise<ProviderSettings> {
  const r = await fetch(`${BASE}/settings/providers`);
  if (!r.ok) throw new Error("failed to load provider settings");
  return r.json();
}

export async function saveCredential(provider: ProviderId, apiKey: string): Promise<void> {
  const r = await fetch(`${BASE}/settings/credentials/${provider}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!r.ok) throw new Error("failed to save credential");
}

export async function deleteCredential(provider: ProviderId): Promise<void> {
  const r = await fetch(`${BASE}/settings/credentials/${provider}`, { method: "DELETE" });
  if (!r.ok && r.status !== 204) throw new Error("failed to delete credential");
}

export async function listModels(provider: ProviderId): Promise<ModelOption[]> {
  const r = await fetch(`${BASE}/settings/models?provider=${encodeURIComponent(provider)}`);
  if (!r.ok) throw new Error("failed to list models");
  const data = await r.json();
  return data.models as ModelOption[];
}
