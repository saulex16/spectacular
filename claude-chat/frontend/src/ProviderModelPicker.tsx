import { useEffect, useState } from "react";
import { getProviderSettings, listModels } from "./api";
import type { ModelOption, ProviderId } from "./types";

const PROVIDER_OPTIONS: { id: ProviderId; label: string }[] = [
  { id: "claude_cli", label: "Claude CLI (local)" },
  { id: "anthropic", label: "Anthropic API" },
  { id: "openai", label: "OpenAI API" },
  { id: "google", label: "Google Gemini API" },
];

type Props = {
  provider: ProviderId;
  model: string;
  onChange: (provider: ProviderId, model: string) => void;
};

export function ProviderModelPicker({ provider, model, onChange }: Props) {
  const [configured, setConfigured] = useState<Record<string, boolean>>({});
  const [models, setModels] = useState<ModelOption[]>([]);

  useEffect(() => {
    void getProviderSettings().then((s) => {
      const map: Record<string, boolean> = {};
      for (const p of s.providers) {
        map[p.id] = p.configured;
      }
      setConfigured(map);
    });
  }, []);

  useEffect(() => {
    if (provider === "claude_cli") {
      setModels([]);
      return;
    }
    void listModels(provider)
      .then(setModels)
      .catch(() => setModels([]));
  }, [provider]);

  function onProviderChange(next: ProviderId) {
    onChange(next, "");
  }

  return (
    <div className="provider-picker">
      <label className="picker-field">
        <span>Provider</span>
        <select
          value={provider}
          onChange={(e) => onProviderChange(e.target.value as ProviderId)}
        >
          {PROVIDER_OPTIONS.map((o) => {
            const needsKey = o.id !== "claude_cli";
            const disabled = needsKey && !configured[o.id];
            return (
              <option key={o.id} value={o.id} disabled={disabled}>
                {o.label}
                {disabled ? " (set API key in settings)" : ""}
              </option>
            );
          })}
        </select>
      </label>
      {provider !== "claude_cli" && (
        <label className="picker-field">
          <span>Model</span>
          <select
            value={model}
            onChange={(e) => onChange(provider, e.target.value)}
          >
            <option value="">Default</option>
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}
