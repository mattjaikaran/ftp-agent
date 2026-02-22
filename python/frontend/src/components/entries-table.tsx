import { useState, useDeferredValue } from "react";
import { cn } from "@/lib/cn";
import { useEntries } from "@/hooks/use-entries";
import type { EntrySummary } from "@/lib/types";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";

const STATUS_COLORS: Record<string, string> = {
  SUCCESS: "bg-success-soft text-success",
  FAILED: "bg-danger-soft text-danger",
  PENDING: "bg-bg-inset text-text-secondary",
  IN_PROGRESS: "bg-info-soft text-info",
  RETRY_PENDING: "bg-purple-50 text-purple-700 dark:bg-purple-950/40 dark:text-purple-400",
};

const STATUS_OPTIONS = ["All", "PENDING", "IN_PROGRESS", "SUCCESS", "FAILED", "RETRY_PENDING"];
const PAGE_SIZES = [25, 50, 100];

interface EntriesTableProps {
  onSelect?: (entry: EntrySummary) => void;
}

export function EntriesTable({ onSelect }: EntriesTableProps) {
  const [filter, setFilter] = useState<string | undefined>();
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  const deferredSearch = useDeferredValue(searchInput);
  const offset = page * pageSize;

  const { data, isLoading, error } = useEntries(filter, pageSize, offset, deferredSearch || undefined);

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;

  if (isLoading) {
    return <div className="py-8 text-center text-text-muted">Loading entries...</div>;
  }

  if (error) {
    return <div className="py-8 text-center text-danger">Failed to load entries</div>;
  }

  return (
    <div className="rounded-xl border border-border bg-bg-card shadow-sm">
      <div className="flex flex-col gap-3 border-b border-border px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="text-sm font-semibold text-text">
          File Entries ({data?.total ?? 0})
        </h3>
        <div className="flex items-center gap-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => { setSearchInput(e.target.value); setPage(0); }}
              placeholder="Search by name..."
              className="rounded-lg border border-border bg-bg-inset py-1.5 pl-8 pr-3 text-xs text-text placeholder:text-text-muted focus:border-primary focus:outline-none"
            />
          </div>
          {/* Status filters */}
          <div className="flex gap-1">
            {STATUS_OPTIONS.map((s) => (
              <button
                key={s}
                onClick={() => { setFilter(s === "All" ? undefined : s); setPage(0); }}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                  (s === "All" && !filter) || filter === s
                    ? "bg-text text-bg-card"
                    : "bg-bg-inset text-text-secondary hover:bg-border",
                )}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-subtle text-left text-xs font-medium text-text-muted">
              <th className="px-5 py-3">Name</th>
              <th className="px-5 py-3">Status</th>
              <th className="px-5 py-3">Protocol</th>
              <th className="px-5 py-3">Retries</th>
              <th className="px-5 py-3">Last Error</th>
              <th className="px-5 py-3">Updated</th>
            </tr>
          </thead>
          <tbody>
            {data?.entries.map((entry) => (
              <tr
                key={entry.id}
                onClick={() => onSelect?.(entry)}
                className="cursor-pointer border-b border-border-subtle transition-colors hover:bg-bg-inset"
              >
                <td className="px-5 py-3 font-medium text-text">{entry.name}</td>
                <td className="px-5 py-3">
                  <span
                    className={cn(
                      "inline-block rounded-full px-2 py-0.5 text-xs font-medium",
                      STATUS_COLORS[entry.status] ?? "bg-bg-inset text-text-secondary",
                    )}
                  >
                    {entry.status}
                  </span>
                </td>
                <td className="px-5 py-3 text-text-secondary">{entry.protocol}</td>
                <td className="px-5 py-3 text-text-secondary">{entry.retry_count}</td>
                <td className="max-w-xs truncate px-5 py-3 text-text-muted">
                  {entry.last_error ?? "\u2014"}
                </td>
                <td className="px-5 py-3 text-text-muted">
                  {new Date(entry.updated_at).toLocaleString()}
                </td>
              </tr>
            ))}
            {data?.entries.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-text-muted">
                  No entries found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <span>Rows per page:</span>
            <select
              value={pageSize}
              onChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }}
              className="rounded border border-border bg-bg-inset px-1.5 py-0.5 text-xs text-text"
            >
              {PAGE_SIZES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted">
              Page {page + 1} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded p-1 text-text-muted transition-colors hover:bg-bg-inset disabled:opacity-30"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="rounded p-1 text-text-muted transition-colors hover:bg-bg-inset disabled:opacity-30"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
