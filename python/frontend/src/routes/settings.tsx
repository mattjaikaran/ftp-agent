import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchConfig } from "@/lib/api";
import { Settings, Key } from "lucide-react";

const API_KEY_STORAGE = "ftp-agent-api-key";

export function SettingsPage() {
  const { data: config, isLoading } = useQuery({
    queryKey: ["config"],
    queryFn: fetchConfig,
  });

  const [apiKey, setApiKey] = useState(() =>
    localStorage.getItem(API_KEY_STORAGE) ?? ""
  );

  const handleSaveKey = () => {
    if (apiKey) {
      localStorage.setItem(API_KEY_STORAGE, apiKey);
    } else {
      localStorage.removeItem(API_KEY_STORAGE);
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="flex items-center gap-2 text-lg font-bold text-text">
        <Settings className="h-5 w-5" />
        Settings
      </h2>

      {/* API Key */}
      <div className="rounded-xl border border-border bg-bg-card p-5 shadow-sm">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-text">
          <Key className="h-4 w-4" />
          API Authentication
        </h3>
        <div className="flex gap-3">
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="Enter API key (leave empty for no auth)"
            className="flex-1 rounded-lg border border-border bg-bg-inset px-3 py-2 text-sm text-text placeholder:text-text-muted focus:border-primary focus:outline-none"
          />
          <button
            onClick={handleSaveKey}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover"
          >
            Save
          </button>
        </div>
        <p className="mt-2 text-xs text-text-muted">
          Set the API key to authenticate requests. Stored locally in your browser.
        </p>
      </div>

      {/* Config viewer */}
      <div className="rounded-xl border border-border bg-bg-card shadow-sm">
        <div className="border-b border-border-subtle px-5 py-3">
          <h3 className="text-sm font-semibold text-text">Server Configuration</h3>
        </div>
        <div className="p-5">
          {isLoading ? (
            <p className="text-sm text-text-muted">Loading configuration...</p>
          ) : config ? (
            <div className="grid gap-6 md:grid-cols-2">
              <ConfigSection title="Agent" items={config.agent} />
              <ConfigSection title="LLM" items={config.llm} />
              <ConfigSection title="Deployment" items={config.deployment} />
              <ConfigSection title="Monitoring" items={config.monitoring} />
            </div>
          ) : (
            <p className="text-sm text-danger">Failed to load configuration</p>
          )}
        </div>
      </div>
    </div>
  );
}

function ConfigSection({ title, items }: { title: string; items: Record<string, unknown> }) {
  return (
    <div>
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
        {title}
      </h4>
      <div className="space-y-1.5">
        {Object.entries(items).map(([key, value]) => (
          <div key={key} className="flex items-baseline justify-between gap-2 text-sm">
            <span className="text-text-secondary">{key}</span>
            <span className="font-mono text-xs text-text">{String(value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
