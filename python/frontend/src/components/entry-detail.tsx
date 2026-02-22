import { useEntry } from "@/hooks/use-entries";
import { cn } from "@/lib/cn";
import { ArrowLeft } from "lucide-react";

interface EntryDetailProps {
  entryId: string;
  onBack: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  SUCCESS: "bg-success-soft text-success",
  FAILED: "bg-danger-soft text-danger",
  PENDING: "bg-bg-inset text-text-secondary",
  IN_PROGRESS: "bg-info-soft text-info",
  RETRY_PENDING: "bg-purple-50 text-purple-700 dark:bg-purple-950/40 dark:text-purple-400",
};

export function EntryDetail({ entryId, onBack }: EntryDetailProps) {
  const { data: entry, isLoading, error } = useEntry(entryId);

  if (isLoading) {
    return <div className="py-8 text-center text-text-muted">Loading entry...</div>;
  }

  if (error || !entry) {
    return <div className="py-8 text-center text-danger">Entry not found</div>;
  }

  return (
    <div className="space-y-4">
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-sm text-text-muted transition-colors hover:text-text-secondary"
      >
        <ArrowLeft className="h-4 w-4" />
        Back
      </button>

      <div className="rounded-xl border border-border bg-bg-card p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-text">{entry.name}</h2>
          <span
            className={cn(
              "rounded-full px-3 py-1 text-xs font-medium",
              STATUS_COLORS[entry.status] ?? "bg-bg-inset text-text-secondary",
            )}
          >
            {entry.status}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <Field label="ID" value={entry.id} />
          <Field label="Protocol" value={entry.protocol} />
          <Field label="Retries" value={String(entry.retry_count)} />
          <Field label="Commit" value={entry.commit_hash ?? "\u2014"} mono />
          <Field label="Deployment" value={entry.deployment_id ?? "\u2014"} mono />
          <Field label="Source Path" value={entry.source_path ?? "\u2014"} />
          <Field label="Destination Path" value={entry.destination_path ?? "\u2014"} />
          <Field label="Created" value={new Date(entry.created_at).toLocaleString()} />
          <Field label="Updated" value={new Date(entry.updated_at).toLocaleString()} />
        </div>

        {entry.last_error && (
          <div className="mt-4">
            <p className="mb-1 text-xs font-medium text-text-muted">Last Error</p>
            <pre className="rounded-lg bg-danger-soft p-3 text-xs text-danger">{entry.last_error}</pre>
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
      <p className="text-xs font-medium text-text-muted">{label}</p>
      <p className={cn("mt-0.5 text-text", mono && "font-mono text-xs")}>{value}</p>
    </div>
  );
}

function ConfigPanel({ title, content }: { title: string; content: string }) {
  return (
    <div className="rounded-xl border border-border bg-bg-card shadow-sm">
      <div className="border-b border-border-subtle px-4 py-2.5">
        <h3 className="text-sm font-semibold text-text">{title}</h3>
      </div>
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap p-4 font-mono text-xs text-text-secondary">
        {content}
      </pre>
    </div>
  );
}
