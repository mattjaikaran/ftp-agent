import { useState } from "react";
import { LlmStatus } from "@/components/llm-status";
import { StatsCards } from "@/components/stats-cards";
import { ProgressBar } from "@/components/progress-bar";
import { EntriesTable } from "@/components/entries-table";
import { LogStream } from "@/components/log-stream";
import { EntryDetail } from "@/components/entry-detail";
import { ThemeToggle } from "@/components/theme-toggle";
import { useStatus } from "@/hooks/use-status";
import { useHealth } from "@/hooks/use-health";
import { triggerRun, stopRun } from "@/lib/api";
import type { EntrySummary } from "@/lib/types";
import { Play, Square, Activity } from "lucide-react";

type Page = "dashboard" | "entries" | "entry-detail";

export function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const { data: status, isLoading: statusLoading } = useStatus();
  const { data: health } = useHealth();

  const handleSelectEntry = (entry: EntrySummary) => {
    setSelectedEntryId(entry.id);
    setPage("entry-detail");
  };

  const handleBack = () => {
    setSelectedEntryId(null);
    setPage("dashboard");
  };

  return (
    <div className="min-h-screen bg-bg">
      {/* Header */}
      <header className="border-b border-border bg-bg-card">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <Activity className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-bold text-text">FTP Agent</h1>
            {health && (
              <span className="rounded-md bg-bg-inset px-2 py-0.5 text-xs text-text-muted">
                v{health.version}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <LlmStatus />
            <button
              onClick={() => triggerRun(true)}
              className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover"
            >
              <Play className="h-4 w-4" />
              Run (Dry)
            </button>
            <button
              onClick={() => stopRun()}
              className="flex items-center gap-1.5 rounded-lg border border-border bg-bg-card px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-bg-inset"
            >
              <Square className="h-4 w-4" />
              Stop
            </button>
          </div>
        </div>
        {/* Nav */}
        <div className="mx-auto max-w-7xl px-6">
          <nav className="flex gap-6 text-sm">
            <button
              onClick={() => { setPage("dashboard"); setSelectedEntryId(null); }}
              className={`border-b-2 pb-2 font-medium transition-colors ${
                page === "dashboard"
                  ? "border-primary text-primary"
                  : "border-transparent text-text-muted hover:text-text-secondary"
              }`}
            >
              Dashboard
            </button>
            <button
              onClick={() => { setPage("entries"); setSelectedEntryId(null); }}
              className={`border-b-2 pb-2 font-medium transition-colors ${
                page === "entries" || page === "entry-detail"
                  ? "border-primary text-primary"
                  : "border-transparent text-text-muted hover:text-text-secondary"
              }`}
            >
              Entries
            </button>
          </nav>
        </div>
      </header>

      {/* Main content */}
      <main className="mx-auto max-w-7xl space-y-6 p-6">
        {page === "dashboard" && (
          <>
            {statusLoading || !status ? (
              <div className="py-12 text-center text-text-muted">Loading dashboard...</div>
            ) : (
              <>
                <StatsCards status={status} />
                <ProgressBar
                  successRate={status.success_rate}
                  total={status.total_files}
                  succeeded={status.succeeded}
                />
              </>
            )}
            <LogStream />
          </>
        )}

        {page === "entries" && (
          <EntriesTable onSelect={handleSelectEntry} />
        )}

        {page === "entry-detail" && selectedEntryId && (
          <EntryDetail entryId={selectedEntryId} onBack={handleBack} />
        )}
      </main>
    </div>
  );
}
