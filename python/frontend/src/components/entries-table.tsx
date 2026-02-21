import { useState } from "react";
import { cn } from "@/lib/cn";
import { useEntries } from "@/hooks/use-entries";
import type { EntrySummary } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  SUCCESS: "bg-green-100 text-green-800",
  FAILED: "bg-red-100 text-red-800",
  PENDING: "bg-gray-100 text-gray-800",
  IN_PROGRESS: "bg-blue-100 text-blue-800",
  RETRY_PENDING: "bg-purple-100 text-purple-800",
};

const STATUS_OPTIONS = ["All", "PENDING", "IN_PROGRESS", "SUCCESS", "FAILED", "RETRY_PENDING"];

interface EntriesTableProps {
  onSelect?: (entry: EntrySummary) => void;
}

export function EntriesTable({ onSelect }: EntriesTableProps) {
  const [filter, setFilter] = useState<string | undefined>();
  const { data, isLoading, error } = useEntries(filter);

  if (isLoading) {
    return <div className="py-8 text-center text-gray-500">Loading entries...</div>;
  }

  if (error) {
    return <div className="py-8 text-center text-red-500">Failed to load entries</div>;
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
        <h3 className="text-sm font-semibold text-gray-900">
          File Entries ({data?.total ?? 0})
        </h3>
        <div className="flex gap-1">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s === "All" ? undefined : s)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                (s === "All" && !filter) || filter === s
                  ? "bg-gray-900 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200",
              )}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 text-left text-xs font-medium text-gray-500">
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
                className="cursor-pointer border-b border-gray-50 transition-colors hover:bg-gray-50"
              >
                <td className="px-5 py-3 font-medium text-gray-900">{entry.name}</td>
                <td className="px-5 py-3">
                  <span
                    className={cn(
                      "inline-block rounded-full px-2 py-0.5 text-xs font-medium",
                      STATUS_COLORS[entry.status] ?? "bg-gray-100 text-gray-800",
                    )}
                  >
                    {entry.status}
                  </span>
                </td>
                <td className="px-5 py-3 text-gray-600">{entry.protocol}</td>
                <td className="px-5 py-3 text-gray-600">{entry.retry_count}</td>
                <td className="max-w-xs truncate px-5 py-3 text-gray-500">
                  {entry.last_error ?? "—"}
                </td>
                <td className="px-5 py-3 text-gray-500">
                  {new Date(entry.updated_at).toLocaleString()}
                </td>
              </tr>
            ))}
            {data?.entries.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-gray-400">
                  No entries found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
