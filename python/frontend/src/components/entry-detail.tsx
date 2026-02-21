import { useEntry } from "@/hooks/use-entries";
import { cn } from "@/lib/cn";
import { ArrowLeft } from "lucide-react";

interface EntryDetailProps {
  entryId: string;
  onBack: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  SUCCESS: "bg-green-100 text-green-800",
  FAILED: "bg-red-100 text-red-800",
  PENDING: "bg-gray-100 text-gray-800",
  IN_PROGRESS: "bg-blue-100 text-blue-800",
  RETRY_PENDING: "bg-purple-100 text-purple-800",
};

export function EntryDetail({ entryId, onBack }: EntryDetailProps) {
  const { data: entry, isLoading, error } = useEntry(entryId);

  if (isLoading) {
    return <div className="py-8 text-center text-gray-500">Loading entry...</div>;
  }

  if (error || !entry) {
    return <div className="py-8 text-center text-red-500">Entry not found</div>;
  }

  return (
    <div className="space-y-4">
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-sm text-gray-500 transition-colors hover:text-gray-700"
      >
        <ArrowLeft className="h-4 w-4" />
        Back
      </button>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-gray-900">{entry.name}</h2>
          <span
            className={cn(
              "rounded-full px-3 py-1 text-xs font-medium",
              STATUS_COLORS[entry.status] ?? "bg-gray-100 text-gray-800",
            )}
          >
            {entry.status}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <Field label="ID" value={entry.id} />
          <Field label="Protocol" value={entry.protocol} />
          <Field label="Retries" value={String(entry.retry_count)} />
          <Field label="Commit" value={entry.commit_hash ?? "—"} mono />
          <Field label="Deployment" value={entry.deployment_id ?? "—"} mono />
          <Field label="Source Path" value={entry.source_path ?? "—"} />
          <Field label="Destination Path" value={entry.destination_path ?? "—"} />
          <Field label="Created" value={new Date(entry.created_at).toLocaleString()} />
          <Field label="Updated" value={new Date(entry.updated_at).toLocaleString()} />
        </div>

        {entry.last_error && (
          <div className="mt-4">
            <p className="mb-1 text-xs font-medium text-gray-500">Last Error</p>
            <pre className="rounded-lg bg-red-50 p-3 text-xs text-red-700">{entry.last_error}</pre>
          </div>
        )}
      </div>

      {/* Config panels */}
      <div className="grid gap-4 lg:grid-cols-2">
        <ConfigPanel title="Legacy Config" content={entry.legacy_config} />
        <ConfigPanel title="New Config" content={entry.new_config ?? "Not yet translated"} />
      </div>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-xs font-medium text-gray-500">{label}</p>
      <p className={cn("mt-0.5 text-gray-900", mono && "font-mono text-xs")}>{value}</p>
    </div>
  );
}

function ConfigPanel({ title, content }: { title: string; content: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
      <div className="border-b border-gray-100 px-4 py-2.5">
        <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
      </div>
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap p-4 font-mono text-xs text-gray-700">
        {content}
      </pre>
    </div>
  );
}
