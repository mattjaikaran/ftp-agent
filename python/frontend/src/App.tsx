import { useState } from "react";
import { LlmStatus } from "@/components/llm-status";
import { StatsCards } from "@/components/stats-cards";
import { ProgressBar } from "@/components/progress-bar";
import { EntriesTable } from "@/components/entries-table";
import { LogStream } from "@/components/log-stream";
import { EntryDetail } from "@/components/entry-detail";
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
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <Activity className="h-6 w-6 text-blue-600" />
            <h1 className="text-xl font-bold text-gray-900">FTP Agent</h1>
            {health && (
              <span className="rounded-md bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                v{health.version}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <LlmStatus />
            <button
              onClick={() => triggerRun(true)}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
            >
              <Play className="h-4 w-4" />
              Run (Dry)
            </button>
            <button
              onClick={() => stopRun()}
              className="flex items-center gap-1.5 rounded-lg bg-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-300"
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
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              Dashboard
            </button>
            <button
              onClick={() => { setPage("entries"); setSelectedEntryId(null); }}
              className={`border-b-2 pb-2 font-medium transition-colors ${
                page === "entries" || page === "entry-detail"
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
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
              <div className="py-12 text-center text-gray-400">Loading dashboard...</div>
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
