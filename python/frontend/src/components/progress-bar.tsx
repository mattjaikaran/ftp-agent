import { cn } from "@/lib/cn";

interface ProgressBarProps {
  successRate: number;
  total: number;
  succeeded: number;
}

export function ProgressBar({ successRate, total, succeeded }: ProgressBarProps) {
  const percentage = total > 0 ? Math.round((succeeded / total) * 100) : 0;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-500">Overall Progress</h3>
        <span className="text-sm font-semibold text-gray-900">
          {succeeded} / {total} files ({successRate.toFixed(1)}%)
        </span>
      </div>
      <div className="h-3 w-full overflow-hidden rounded-full bg-gray-100">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            percentage === 100
              ? "bg-green-500"
              : percentage > 75
                ? "bg-blue-500"
                : percentage > 25
                  ? "bg-amber-500"
                  : "bg-red-500",
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}
