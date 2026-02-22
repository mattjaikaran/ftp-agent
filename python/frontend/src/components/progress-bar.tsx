import { cn } from "@/lib/cn";

interface ProgressBarProps {
  successRate: number;
  total: number;
  succeeded: number;
}

export function ProgressBar({ successRate, total, succeeded }: ProgressBarProps) {
  const percentage = total > 0 ? Math.round((succeeded / total) * 100) : 0;

  return (
    <div className="rounded-xl border border-border bg-bg-card p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-text-muted">Overall Progress</h3>
        <span className="text-sm font-semibold text-text">
          {succeeded} / {total} files ({successRate.toFixed(1)}%)
        </span>
      </div>
      <div className="h-3 w-full overflow-hidden rounded-full bg-bg-inset">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            percentage === 100
              ? "bg-success"
              : percentage > 75
                ? "bg-info"
                : percentage > 25
                  ? "bg-warning"
                  : "bg-danger",
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}
