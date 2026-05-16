import { useEffect, useState } from "react";
import { deleteCredential, getProviderSettings, saveCredential } from "./api";
import type { ProviderId, ProviderInfo } from "./types";

const API_PROVIDERS: ProviderId[] = ["anthropic", "openai", "google"];

type Props = {
  open: boolean;
  onClose: () => void;
};

export function SettingsPanel({ open, onClose }: Props) {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const data = await getProviderSettings();
    setProviders(data.providers.filter((p) => API_PROVIDERS.includes(p.id as ProviderId)));
  }

  useEffect(() => {
    if (open) {
      void refresh().catch((e) => setError(String(e)));
    }
  }, [open]);

  if (!open) return null;

  async function onSave(provider: ProviderId) {
    const key = keys[provider]?.trim();
    if (!key) return;
    setSaving(provider);
    setError(null);
    try {
      await saveCredential(provider, key);
      setKeys((k) => ({ ...k, [provider]: "" }));
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(null);
    }
  }

  async function onRemove(provider: ProviderId) {
    setSaving(provider);
    setError(null);
    try {
      await deleteCredential(provider);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="intercept-overlay" onClick={onClose}>
      <div className="intercept-modal settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="intercept-header">
          <span className="intercept-badge">API credentials</span>
          <button type="button" className="btn" onClick={onClose}>
            Close
          </button>
        </div>
        <p className="intercept-label">
          Keys are encrypted at rest on the server. Claude CLI mode uses your local{" "}
          <code>claude</code> login instead.
        </p>
        {error && <p className="settings-error">{error}</p>}
        {providers.map((p) => (
          <div key={p.id} className="settings-provider">
            <div className="settings-provider-head">
              <strong>{p.label}</strong>
              {p.configured ? (
                <span className="settings-hint">configured {p.hint}</span>
              ) : (
                <span className="settings-hint">not configured</span>
              )}
            </div>
            <input
              type="password"
              className="settings-input"
              placeholder="API key"
              value={keys[p.id] ?? ""}
              onChange={(e) => setKeys((k) => ({ ...k, [p.id]: e.target.value }))}
            />
            <div className="intercept-actions">
              <button
                type="button"
                className="btn"
                disabled={saving === p.id || !(keys[p.id]?.trim())}
                onClick={() => void onSave(p.id as ProviderId)}
              >
                Save
              </button>
              {p.configured && (
                <button
                  type="button"
                  className="btn danger"
                  disabled={saving === p.id}
                  onClick={() => void onRemove(p.id as ProviderId)}
                >
                  Remove
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
